"""Subprocess wrapper to run LTspice on a netlist.

Produces a typed `RunResult` that folds together: the subprocess
outcome, the structured `.log` (via `sim_ltspice.log.parse_log`), and
the `.raw` trace names (via `sim_ltspice.raw.trace_names`).

`.asc` input handling is planned for a follow-up commit that adds the
`Schematic` model + `schematic_to_netlist` flattener (macOS native) or
shells to `LTspice -netlist` (Windows/wine).
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sim_ltspice.install import Install, find_ltspice
from sim_ltspice.log import LogResult, parse_log
from sim_ltspice.raw import trace_names


NETLIST_SUFFIXES = (".net", ".cir", ".sp")


class LtspiceError(Exception):
    """Base class for sim_ltspice errors."""


class LtspiceNotInstalled(LtspiceError):
    """Raised when no LTspice install is discoverable on this host."""


class UnsupportedInput(LtspiceError):
    """Raised when the input file is not a netlist this runner accepts."""


@dataclass
class RunResult:
    """Outcome of a single LTspice batch invocation."""

    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    script: Path
    started_at: str
    log: LogResult
    log_path: Path | None
    raw_path: Path | None
    raw_traces: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when LTspice exited cleanly AND no errors were logged."""
        return self.exit_code == 0 and not self.log.errors


def run_net(
    script: Path | str,
    *,
    install: Install | None = None,
    timeout: float | None = None,
) -> RunResult:
    """Run an LTspice batch simulation on a `.net` / `.cir` / `.sp` netlist.

    Returns a `RunResult` with parsed `.log` and `.raw` trace names.
    Does not raise on convergence errors — inspect `result.ok` or
    `result.log.errors` for those. Raises `LtspiceNotInstalled` if no
    install is discoverable and none was passed explicitly, and
    `UnsupportedInput` for non-netlist suffixes.
    """
    script = Path(script).resolve()
    if script.suffix.lower() not in NETLIST_SUFFIXES:
        raise UnsupportedInput(
            f"run_net accepts {NETLIST_SUFFIXES} (got {script.suffix}). "
            f"For .asc schematics use run_asc() once available."
        )

    if install is None:
        installs = find_ltspice()
        if not installs:
            raise LtspiceNotInstalled(
                "LTspice not found. Set $SIM_LTSPICE_EXE or install LTspice "
                "from analog.com."
            )
        install = installs[0]

    # Native macOS LTspice accepts only '-b <netlist>'. Windows / wine
    # additionally accept '-Run' (same effect).
    if sys.platform == "darwin":
        cmd = [str(install.exe), "-b", script.as_posix()]
    else:
        cmd = [str(install.exe), "-Run", "-b", script.as_posix()]

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    duration = time.monotonic() - t0

    log_path = script.with_suffix(".log")
    raw_path = script.with_suffix(".raw")
    log_result = parse_log(log_path) if log_path.is_file() else LogResult()
    traces = trace_names(raw_path) if raw_path.is_file() else []

    return RunResult(
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        duration_s=round(duration, 3),
        script=script,
        started_at=started,
        log=log_result,
        log_path=log_path if log_path.is_file() else None,
        raw_path=raw_path if raw_path.is_file() else None,
        raw_traces=traces,
    )
