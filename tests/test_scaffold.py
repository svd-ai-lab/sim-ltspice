"""Scaffold test — proves the package imports and CI wiring works.

Gets replaced once real modules land.
"""
from __future__ import annotations

import sim_ltspice


def test_version_present():
    assert isinstance(sim_ltspice.__version__, str)
    assert sim_ltspice.__version__


def test_public_surface_placeholder():
    """Intentional marker: the v0.1 API surface listed in __init__.py is not
    implemented yet. This test passes today and is deleted once real modules
    (asc, schematic, layout, runner, …) land."""
    assert True
