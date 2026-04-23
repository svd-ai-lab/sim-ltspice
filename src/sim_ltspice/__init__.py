"""Python API for LTspice.

This package is in early scaffolding. The v0.1 surface will expose:

    from sim_ltspice import (
        read_asc, write_asc,          # .asc text I/O
        parse_net, write_net,         # .net text I/O
        Schematic,                    # in-memory model
        SymbolCatalog,                # .asy symbol library index
        parse_log, trace_names,       # result parsers
        run_net, run_asc,             # subprocess runners
        find_ltspice,                 # install discovery
    )
    from sim_ltspice.layout import net_to_schematic

For now the package exports only its version string.
"""
from __future__ import annotations

__version__ = "0.1.0.dev0"
__all__ = ["__version__"]
