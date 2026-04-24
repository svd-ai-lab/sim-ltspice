# Changelog

## [0.1.0] — 2026-04-24

First public release. Flat-schematic authoring loop closed end-to-end:
build a netlist in Python → lay out to `.asc` → open in LTspice GUI → run
batch → parse `.log` / `.raw`.

### Added
- `.asc` reader/writer. 100 % parse and 100 % structural round-trip
  across the 3999 `.asc` files shipped with LTspice (measured with
  `tests/corpus_roundtrip.py`). Byte-identical round-trip on
  `tests/fixtures/montecarlo.asc` is a regression gate.
- Only six statement kinds fall through to `raw_tail` and are preserved
  verbatim on write: `LINE`, `RECTANGLE`, `CIRCLE`, `ARC`, `DATAFLAG`,
  `IOPIN`. Authorable first-class support lands in v0.3.
- `Schematic` dataclass model: `Placement`, `Wire`, `Flag`,
  `TextDirective`, `Window`, `Rotation` (all eight LTspice rotations;
  empirically verified against shipped symbols).
- `.asy` parser + `SymbolCatalog`: lazy indexer over the shipped symbol
  library; honours `SpiceOrder` for pin-to-node mapping.
- `.net` parser + writer + `schematic_to_netlist` flattener — the only
  `.asc → .net` path that works on modern LTspice, since LTspice 26's
  `-netlist` hangs.
- `.log` and `.raw` parsers with the UTF-16-LE / BOM / UTF-8 / Latin-1
  fallback matrix.
- `run_net` subprocess runner + cross-platform `find_ltspice` install
  discovery (macOS `LTspice.app`, Windows `LTspice.exe`, env overrides).
- `layout.netlist_to_schematic` — v0.1 topology set: linear / cascaded
  passives (RC, RLC, multi-stage) and parallel shunts on a rail node.
  Unsupported topologies raise `UnsupportedTopology` with a clear reason.
- Python 3.10+; Apache-2.0; no runtime dependencies.

### Known gaps (tracked for v0.2+)
- `.raw` body parsing (only header trace-name extraction today).
- Hierarchical schematics (`.asy` + sibling `.asc`) are rejected on
  flattening — deferred to v0.3.
- Layout engine covers passives and parallel shunts only; active
  topologies (op-amp feedback, common-emitter, differential) are
  deferred.

## [Unreleased]
