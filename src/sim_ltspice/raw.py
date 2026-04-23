"""LTspice .raw file — waveform data container.

Only the header is parsed here (UTF-16 LE text). The binary value
section is large and only valuable with proper trace decoding;
full waveform access is out of scope for v0.1 and left to callers
who can use external tooling (e.g. `spicelib.RawRead`) when they
need numeric traces rather than just their names.
"""
from __future__ import annotations

from pathlib import Path


def trace_names(path: Path | str) -> list[str]:
    """Return trace (signal) names from a `.raw` file, header-only.

    Parses the UTF-16 LE header that every LTspice `.raw` (binary or
    ASCII) starts with. The ``Variables:`` section lists one name per
    line in the form ``<idx>\\t<name>\\t<type>``. The header ends at
    ``Binary:`` (binary raw) or ``Values:`` (ASCII raw).
    """
    path = Path(path)
    if not path.is_file():
        return []
    head = path.read_bytes()[:65536]
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
