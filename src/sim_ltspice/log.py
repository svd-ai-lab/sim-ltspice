"""LTspice .log reader + .MEAS parser.

Encoding varies by version. LTspice 17.x (macOS native) writes UTF-16
LE with no BOM; LTspice 26.x (Windows) writes UTF-8. The reader sniffs
via BOM first, then the "0x00 at every odd byte" pattern (ASCII under
UTF-16 LE), else falls back to UTF-8 and finally Latin-1. A naive chain
that tries utf-16-le first produces silent garbage on UTF-8 logs —
UTF-16 LE decoding never raises on arbitrary bytes.

Measures live in lines like:

    vout_pk: MAX(v(out))=0.999955 FROM 0 TO 0.005

Windows 26 additionally emits a ``Files loaded:`` block with an
absolute path (``C:\\Users\\...\\design.net``); the expression capture
excludes newlines so a drive letter can't masquerade as a measure
name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Measure:
    """A single `.MEAS` result."""

    expr: str
    value: float
    window_from: float | None = None
    window_to: float | None = None


@dataclass
class LogResult:
    """Structured view of an LTspice `.log` file."""

    measures: dict[str, Measure] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    elapsed_s: float | None = None


_MEAS_RE = re.compile(
    r"^(?P<name>[A-Za-z_][\w]*)\s*:\s*"
    r"(?P<expr>[^=\n\r]+?)=(?P<value>[-+0-9.eE]+(?:[a-zA-Z]*)?)"
    r"(?:\s+FROM\s+(?P<from>[-+0-9.eE]+))?"
    r"(?:\s+TO\s+(?P<to>[-+0-9.eE]+))?\s*$",
    re.MULTILINE,
)

_ERROR_RE = re.compile(
    r"^(?:Error[:\s]|Fatal[:\s]|Convergence failed|Singular matrix|"
    r"Cannot find|Unknown (?:parameter|device))",
    re.MULTILINE | re.IGNORECASE,
)

_WARN_RE = re.compile(r"^WARNING[:\s].*$", re.MULTILINE | re.IGNORECASE)

_ELAPSED_RE = re.compile(
    r"Total elapsed time:\s*([0-9.]+)\s*seconds",
    re.IGNORECASE,
)

_TRAILING_UNIT_RE = re.compile(r"[a-zA-Z]+$")


def read_log(path: Path | str) -> str:
    """Read an LTspice `.log` file as text, auto-detecting encoding."""
    path = Path(path)
    if not path.is_file():
        return ""
    data = path.read_bytes()
    if not data:
        return ""
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if len(data) >= 4 and data[1] == 0 and data[3] == 0:
        return data.decode("utf-16-le", errors="replace")
    return data.decode("utf-8", errors="replace")


def parse_log(text_or_path: str | Path) -> LogResult:
    """Parse an LTspice log body (or a path to one) into a `LogResult`."""
    if isinstance(text_or_path, Path) or (
        isinstance(text_or_path, str) and len(text_or_path) < 4096
        and Path(text_or_path).is_file()
    ):
        text = read_log(text_or_path)
    else:
        text = text_or_path  # type: ignore[assignment]

    measures: dict[str, Measure] = {}
    for m in _MEAS_RE.finditer(text):
        raw_value = _TRAILING_UNIT_RE.sub("", m.group("value"))
        try:
            value = float(raw_value)
        except ValueError:
            continue
        window_from: float | None = None
        if m.group("from"):
            try:
                window_from = float(m.group("from"))
            except ValueError:
                window_from = None
        window_to: float | None = None
        if m.group("to"):
            try:
                window_to = float(m.group("to"))
            except ValueError:
                window_to = None
        measures[m.group("name")] = Measure(
            expr=m.group("expr").strip(),
            value=value,
            window_from=window_from,
            window_to=window_to,
        )

    errors = [m.group(0).strip() for m in _ERROR_RE.finditer(text)]
    warnings = [m.group(0).strip() for m in _WARN_RE.finditer(text)]

    elapsed_s: float | None = None
    em = _ELAPSED_RE.search(text)
    if em:
        try:
            elapsed_s = float(em.group(1))
        except ValueError:
            elapsed_s = None

    return LogResult(
        measures=measures,
        errors=errors,
        warnings=warnings,
        elapsed_s=elapsed_s,
    )
