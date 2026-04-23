# Changelog

## [Unreleased]

### Added
- Scaffold: package layout, `pyproject.toml`, CI stub, placeholder test.

### Planned for v0.1.0
- `.asc` read/write (text I/O for Version 3/4/1003).
- `SymbolCatalog` — lazy `.asy` parser indexing the shipped LTspice symbol library.
- `Schematic` in-memory model (symbols, wires, flags, text directives).
- `.net` parser + `schematic_to_netlist` emitter for flat schematics.
- `.log` and `.raw` parsers ported from sim-cli's in-tree driver.
- `run_net` / `run_asc` subprocess wrappers with cross-platform install discovery.
- Layout engine: flow-axis grid placer + Manhattan router. Supports linear / cascaded passives, single-feedback op-amps, common-emitter with degeneration, 2-stage active filters, differential pairs. Up to ~20 elements.
