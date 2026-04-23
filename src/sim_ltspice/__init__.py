"""Python API for LTspice.

v0.1 exposes the runtime layer (installs, batch runner, .log/.raw
parsers). The authoring layer (Schematic model, .asc read/write,
symbol catalog, layout engine) lands in subsequent commits.
"""
from __future__ import annotations

__version__ = "0.1.0.dev0"

from sim_ltspice.asc import read_asc, write_asc
from sim_ltspice.install import Install, find_ltspice
from sim_ltspice.log import LogResult, Measure, parse_log, read_log
from sim_ltspice.layout import UnsupportedTopology, netlist_to_schematic
from sim_ltspice.netlist import (
    Directive,
    Element,
    FlattenError,
    Netlist,
    parse_net,
    schematic_to_netlist,
    write_net,
)
from sim_ltspice.raw import trace_names
from sim_ltspice.runner import (
    LtspiceError,
    LtspiceNotInstalled,
    NETLIST_SUFFIXES,
    RunResult,
    UnsupportedInput,
    run_net,
)
from sim_ltspice.schematic import (
    Flag,
    Placement,
    Rotation,
    Schematic,
    TextDirective,
    TextKind,
    Window,
    Wire,
)
from sim_ltspice.symbols import Pin, SymbolCatalog, SymbolDef, parse_asy

__all__ = [
    "__version__",
    # Install discovery + runner
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
    # Schematic authoring
    "Schematic",
    "Placement",
    "Wire",
    "Flag",
    "TextDirective",
    "TextKind",
    "Window",
    "Rotation",
    "read_asc",
    "write_asc",
    # Symbol catalog
    "SymbolCatalog",
    "SymbolDef",
    "Pin",
    "parse_asy",
    # Netlist
    "Directive",
    "Element",
    "FlattenError",
    "Netlist",
    "parse_net",
    "schematic_to_netlist",
    "write_net",
    # Layout (netlist → schematic)
    "UnsupportedTopology",
    "netlist_to_schematic",
]
