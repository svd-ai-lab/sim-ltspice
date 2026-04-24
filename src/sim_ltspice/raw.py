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

        # Detect which body format we're about to decode.
        self._is_ascii = header.endswith(_VALUES_SENTINEL)

        # fastaccess (transposed variable-major layout) is not yet decoded.
        if "fastaccess" in self.flags:
            raise UnsupportedRawFormat(
                "`fastaccess` .raw files are not yet supported; re-run without "
                "the fastaccess option or wait for a later sim-ltspice release"
            )

        body_bytes = raw[body_offset:]
        if self._is_ascii:
            self._data = self._decode_ascii_body(body_bytes)
        else:
            self._data = self._decode_body(body_bytes)

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

    def _decode_ascii_body(self, body: bytes) -> np.ndarray:
        """Parse a ``Values:`` body written in UTF-16 LE tab-separated text.

        Each point produces ``n_variables`` lines:

        * Line 0: ``<point_idx>\\t<axis_value>``
        * Lines 1..N-1: ``\\t<value>`` (leading tab, value is the trace)

        Complex values are written as ``<real>,<imag>``. Blank lines are
        silently skipped, matching spicelib's parser.
        """
        nvars = self.n_variables
        npts = self.n_points
        dtype = np.complex128 if self.is_complex else np.float64
        out = np.empty((npts, nvars), dtype=dtype)

        text = body.decode("utf-16-le", errors="replace")
        # LTspice always writes `\n`; don't let a trailing BOM or stray
        # characters break the sequence. Strip lines, drop empties.
        lines = [line for line in (ln.strip() for ln in text.splitlines()) if line]
        expected = npts * nvars
        if len(lines) < expected:
            raise UnsupportedRawFormat(
                f"ASCII body has {len(lines)} non-blank lines, need "
                f"{expected} ({npts} points × {nvars} variables)"
            )

        i = 0
        for p in range(npts):
            for v in range(nvars):
                line = lines[i]
                i += 1
                if v == 0:
                    # Point index prefix. spicelib validates it strictly;
                    # we do the same so fixture drift is caught early.
                    idx_str, _, value_str = line.partition("\t")
                    try:
                        idx = int(idx_str)
                    except ValueError as exc:
                        raise UnsupportedRawFormat(
                            f"ASCII body: expected '<idx>\\t<axis>' at point "
                            f"{p}, got {line!r}"
                        ) from exc
                    if idx != p:
                        raise UnsupportedRawFormat(
                            f"ASCII body: point index {idx} out of order "
                            f"(expected {p})"
                        )
                else:
                    value_str = line

                if self.is_complex:
                    real_s, _, imag_s = value_str.partition(",")
                    if not imag_s:
                        raise UnsupportedRawFormat(
                            f"ASCII body: expected 'real,imag' at point {p} "
                            f"var {v}, got {value_str!r}"
                        )
                    out[p, v] = complex(float(real_s), float(imag_s))
                else:
                    out[p, v] = float(value_str)
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

    # -- cursor helpers ---------------------------------------------------

    def max(self, name: str) -> float:
        """Peak value of trace ``name`` (magnitude for complex)."""
        arr = self.trace(name)
        return float(np.abs(arr).max() if np.iscomplexobj(arr) else arr.max())

    def min(self, name: str) -> float:
        """Minimum value of trace ``name`` (magnitude for complex)."""
        arr = self.trace(name)
        return float(np.abs(arr).min() if np.iscomplexobj(arr) else arr.min())

    def mean(self, name: str) -> float | complex:
        """Arithmetic mean of trace ``name``.

        For complex traces this is the complex mean, not the magnitude
        mean — caller can take abs() / angle() themselves.
        """
        arr = self.trace(name)
        return complex(arr.mean()) if np.iscomplexobj(arr) else float(arr.mean())

    def rms(self, name: str) -> float:
        """Root-mean-square of trace ``name``.

        Uses ``sqrt(mean(|x|^2))`` so complex traces get their magnitude
        RMS — matching what LTspice's waveform viewer reports.
        """
        arr = self.trace(name)
        mag2 = np.abs(arr) ** 2 if np.iscomplexobj(arr) else arr ** 2
        return float(np.sqrt(mag2.mean()))

    def sample_at(self, name: str, x: float) -> float | complex:
        """Linear-interpolated value of trace ``name`` at axis position ``x``.

        The axis must be real (time or frequency). For AC analyses we
        index on the real part of the complex frequency axis, which
        LTspice always writes with a zero imaginary part.

        Raises ``ValueError`` for stepped sweeps (ambiguous — the axis
        isn't monotonic) and ``KeyError`` for unknown trace names.
        """
        if self.is_stepped:
            raise ValueError(
                "sample_at is ambiguous on stepped sweeps — split by step "
                "boundary first (planned for a later release)"
            )
        axis = self.axis
        if np.iscomplexobj(axis):
            axis = axis.real
        if axis.size < 2:
            raise ValueError(
                f"cannot interpolate on an axis with {axis.size} point(s)"
            )
        if not (axis[0] <= x <= axis[-1]):
            raise ValueError(
                f"axis position {x} outside range [{axis[0]}, {axis[-1]}]"
            )
        arr = self.trace(name)
        if np.iscomplexobj(arr):
            # numpy.interp is real-only; interpolate real and imaginary
            # independently.
            return complex(
                np.interp(x, axis, arr.real),
                np.interp(x, axis, arr.imag),
            )
        return float(np.interp(x, axis, arr))

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
