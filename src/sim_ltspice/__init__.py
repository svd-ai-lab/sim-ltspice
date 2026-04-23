"""Python API for LTspice.

v0.1 exposes the runtime layer (installs, batch runner, .log/.raw
parsers). The authoring layer (Schematic model, .asc read/write,
symbol catalog, layout engine) lands in subsequent commits.
"""
from __future__ import annotations

__version__ = "0.1.0.dev0"

from sim_ltspice.install import Install, find_ltspice
from sim_ltspice.log import LogResult, Measure, parse_log, read_log
from sim_ltspice.raw import trace_names
from sim_ltspice.runner import (
    LtspiceError,
    LtspiceNotInstalled,
    NETLIST_SUFFIXES,
    RunResult,
    UnsupportedInput,
    run_net,
)

__all__ = [
    "__version__",
    "Install",
    "find_ltspice",
    "LogResult",
    "Measure",
    "parse_log",
    "read_log",
    "trace_names",
    "LtspiceError",
    "LtspiceNotInstalled",
    "NETLIST_SUFFIXES",
    "RunResult",
    "UnsupportedInput",
    "run_net",
]
