"""LTspice `.raw` waveform file parser.

LTspice stores simulation results in a mixed-format ``.raw`` file:

* **Header** — UTF-16 LE text (no BOM is emitted by modern LTspice, but some
  tools prepend one). Key fields are ``Title``, ``Date``, ``Plotname``,
  ``Flags`` (a space-separated set), ``No. Variables``, ``No. Points``,
  ``Offset``, ``Command``, optionally ``Output`` (``.noise`` only), the
  ``Variables:`` table and the body sentinel — ``Binary:`` for the native
  format or ``Values:`` for the rarely-seen ASCII export.
* **Body** — binary per-point record, written in point-major order
  (all values for point 0, then all for point 1, ...). The per-point
  layout is decided by ``Flags``:

  ``complex``
      Every variable (including the axis) is stored as a
      ``complex128`` — real and imaginary ``float64`` interleaved.
  ``double``
      All variables are ``float64``.
  default (``real``)
      The axis (first variable) is a ``float64``; the remaining
      variables are ``float32``.

The ``fastaccess`` flag transposes the body to variable-major ordering.
We recognise it but do not decode it yet — ``UnsupportedRawFormat`` is
raised.

For transient analyses LTspice signals compressed/keepalive points by
storing the time axis as a negative value; the absolute value is the
real timestamp. ``RawRead`` applies ``np.abs`` to the axis for
``Transient Analysis`` plots.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = [
    "RawRead",
    "Variable",
    "UnsupportedRawFormat",
    "trace_names",
]


class UnsupportedRawFormat(ValueError):
    """Raised when a `.raw` file uses a variant we do not yet decode."""


@dataclass(frozen=True)
class Variable:
    """A single signal declared in the `.raw` Variables table."""

    index: int
    name: str
    type: str  # 'time', 'frequency', 'voltage', 'device_current', ...


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

_BINARY_SENTINEL = "Binary:\n"
_VALUES_SENTINEL = "Values:\n"


def _decode_header(raw: bytes) -> tuple[str, int]:
    """Decode the UTF-16 LE header and return ``(text, body_offset)``.

    ``body_offset`` is the byte index in ``raw`` at which the binary (or
    ASCII) body starts — i.e. right after the sentinel line that closes
    the header.
    """
    # Strip a BOM if present — some LTspice forks write one.
    start = 2 if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else 0
    # Scan until we find one of the sentinels. The header is small
    # (<10 kB for sane designs) so slicing a generous chunk is fine.
    head = raw[start : start + 65536].decode("utf-16-le", errors="replace")
    for sentinel in (_BINARY_SENTINEL, _VALUES_SENTINEL):
        i = head.find(sentinel)
        if i >= 0:
            end = i + len(sentinel)
            # Convert char count back to byte offset.
            body_offset = start + end * 2
            return head[:end], body_offset
    raise UnsupportedRawFormat(
        "missing 'Binary:' or 'Values:' sentinel — not a recognisable .raw file"
    )


def _parse_metadata(header: str) -> dict[str, str]:
    """Extract the ``Key: value`` lines above the Variables table."""
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if line in ("Variables:", "Binary:", "Values:"):
            break
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def _parse_variables(header: str) -> list[Variable]:
    if "Variables:" not in header:
        return []
    body = header.split("Variables:", 1)[1]
    out: list[Variable] = []
    for line in body.splitlines():
        if line.strip() in ("", "Binary:", "Values:"):
            continue
        parts = line.strip().split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        out.append(Variable(index=int(parts[0]), name=parts[1], type=parts[2]))
    return out


# ---------------------------------------------------------------------------
# Public reader
# ---------------------------------------------------------------------------


class RawRead:
    """Parsed `.raw` file with per-trace NumPy arrays.

    Usage::

        rr = RawRead("sim.raw")
        rr.axis            # np.ndarray — time, frequency, or step index
        rr.trace("V(out)") # np.ndarray aligned with rr.axis
        rr.variables       # list[Variable]
        rr.flags           # set[str] — 'real', 'complex', 'forward', 'stepped', ...

    Complex analyses (``.ac``, ``.tf``, ``.noise`` with complex flag) return
    ``complex128`` arrays; real analyses return ``float64``.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        raw = self.path.read_bytes()
        header, body_offset = _decode_header(raw)
        meta = _parse_metadata(header)

        self.title = meta.get("Title", "")
        self.date = meta.get("Date", "")
        self.plotname = meta.get("Plotname", "")
        self.command = meta.get("Command", "")
        self.output = meta.get("Output", "")  # `.noise` only
        try:
            self.offset = float(meta.get("Offset", "0"))
        except ValueError:
            self.offset = 0.0
        self.flags: set[str] = set(meta.get("Flags", "").split())

        self.variables: list[Variable] = _parse_variables(header)
        if not self.variables:
            raise UnsupportedRawFormat("no variables found in header")
        try:
            n_points = int(meta.get("No. Points", "0"))
            n_vars_declared = int(meta.get("No. Variables", "0"))
        except ValueError as exc:
            raise UnsupportedRawFormat(f"invalid point/variable count: {exc}") from exc
        if n_vars_declared != len(self.variables):
            raise UnsupportedRawFormat(
                f"header declares {n_vars_declared} variables but Variables: "
                f"table has {len(self.variables)}"
            )
        self.n_points = n_points
        self.n_variables = len(self.variables)

        # We don't support the transposed ASCII/fastaccess variants yet.
        if "fastaccess" in self.flags:
            raise UnsupportedRawFormat(
                "`fastaccess` .raw files are not yet supported; re-run without "
                "the fastaccess option or wait for a later sim-ltspice release"
            )
        if header.endswith(_VALUES_SENTINEL):
            raise UnsupportedRawFormat(
                "ASCII `.raw` files are not yet supported (PR2); save in "
                "binary format or wait for a later sim-ltspice release"
            )

        self._data = self._decode_body(raw[body_offset:])

        # Transient axis: compressed points are flagged by a negative sign.
        if self.plotname.startswith("Transient"):
            self._data[:, 0] = np.abs(self._data[:, 0])

    # -- decoding ----------------------------------------------------------

    def _decode_body(self, body: bytes) -> np.ndarray:
        """Return an ``(n_points, n_variables)`` array.

        Respects ``complex`` / ``double`` / default (real-float32-trace)
        layouts. Raises ``UnsupportedRawFormat`` on size mismatch.
        """
        nvars = self.n_variables
        npts = self.n_points
        is_complex = "complex" in self.flags
        is_double = "double" in self.flags

        if is_complex:
            # Every variable: 16 bytes (re+im float64). Output dtype complex128.
            expected = npts * nvars * 16
            if len(body) != expected:
                raise UnsupportedRawFormat(
                    f"body size {len(body)} != expected {expected} for "
                    f"complex layout ({npts} points × {nvars} complex128)"
                )
            flat = np.frombuffer(body, dtype="<c16", count=npts * nvars)
            return flat.reshape(npts, nvars).astype(np.complex128, copy=False)

        if is_double:
            # All vars: float64.
            expected = npts * nvars * 8
            if len(body) != expected:
                raise UnsupportedRawFormat(
                    f"body size {len(body)} != expected {expected} for "
                    f"double layout ({npts} × {nvars} float64)"
                )
            flat = np.frombuffer(body, dtype="<f8", count=npts * nvars)
            return flat.reshape(npts, nvars).astype(np.float64, copy=False)

        # Default real layout: axis=float64, rest=float32.
        # Per-point record: 8 + (nvars-1)*4 bytes.
        record_bytes = 8 + (nvars - 1) * 4
        expected = npts * record_bytes
        if len(body) != expected:
            raise UnsupportedRawFormat(
                f"body size {len(body)} != expected {expected} for default "
                f"real layout ({npts} points × [float64 axis + {nvars - 1}× float32])"
            )
        # Interpret each record with a structured dtype, then split into
        # a single float64 matrix.
        record_dtype = np.dtype(
            [("axis", "<f8"), ("rest", "<f4", nvars - 1)],
            align=False,
        )
        rec = np.frombuffer(body, dtype=record_dtype, count=npts)
        out = np.empty((npts, nvars), dtype=np.float64)
        out[:, 0] = rec["axis"]
        if nvars > 1:
            out[:, 1:] = rec["rest"].astype(np.float64, copy=False)
        return out

    # -- public surface ---------------------------------------------------

    @property
    def axis(self) -> np.ndarray:
        """First variable (time / frequency / step index)."""
        return self._data[:, 0]

    @property
    def is_complex(self) -> bool:
        return "complex" in self.flags

    @property
    def is_stepped(self) -> bool:
        return "stepped" in self.flags

    def trace_names(self) -> list[str]:
        """All declared variable names, in declaration order."""
        return [v.name for v in self.variables]

    def _index_of(self, name: str) -> int:
        for v in self.variables:
            if v.name == name:
                return v.index
        # Fall back to case-insensitive match — LTspice is inconsistent.
        low = name.lower()
        for v in self.variables:
            if v.name.lower() == low:
                return v.index
        raise KeyError(f"trace {name!r} not found; available: {self.trace_names()}")

    def trace(self, name: str) -> np.ndarray:
        """Return the array for one trace by name."""
        return self._data[:, self._index_of(name)]

    def __repr__(self) -> str:
        return (
            f"RawRead({self.path.name}, plot={self.plotname!r}, "
            f"points={self.n_points}, vars={self.n_variables}, "
            f"flags={sorted(self.flags)})"
        )


# ---------------------------------------------------------------------------
# Back-compat shim: the v0.1 module exported only `trace_names(path)`.
# ---------------------------------------------------------------------------


def trace_names(path: str | Path) -> list[str]:
    """Return trace names from a `.raw` file without loading the body.

    Retained for back-compat with callers that only need the header. For
    numeric access, use ``RawRead(path).trace(name)``.
    """
    p = Path(path)
    if not p.is_file():
        return []
    head = p.read_bytes()[:65536]
    try:
        text = head.decode("utf-16-le", errors="replace")
    except Exception:
        return []
    for sentinel in ("Binary:", "Values:"):
        if sentinel in text:
            text = text.split(sentinel, 1)[0]
            break
    if "Variables:" not in text:
        return []
    body = text.split("Variables:", 1)[1]
    names: list[str] = []
    for line in body.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].isdigit():
            names.append(parts[1])
    return names
