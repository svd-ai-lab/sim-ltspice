# Changelog

## [Unreleased]

### Added
- `RawRead` — full binary `.raw` waveform parser. Decodes the three LTspice
  body layouts (`real` default: float64 axis + float32 traces; `double`: all
  float64; `complex`: all complex128) into NumPy arrays. Applies the
  compressed-point sign convention on transient time axes. Fixture-backed
  tests cover transient, `.op`, `.ac`, `.step`, and `.noise` files.
- ASCII `.raw` (``Values:`` sentinel) bodies — UTF-16 LE tab-separated text
  with comma-separated real,imag complex values. Verified against
  binary-twin fixtures.
- Cursor helpers on `RawRead`:
  - `.max(name)` / `.min(name)` — peak / minimum (magnitude for complex).
  - `.mean(name)` / `.rms(name)` — arithmetic mean and RMS
    (`sqrt(mean(|x|²))` on complex).
  - `.sample_at(name, x)` — linear-interpolated value at axis position
    `x`; raises on stepped sweeps and out-of-range requests.
- `RawRead.eval(expr)` — evaluate an arithmetic expression over the
  loaded traces. Accepts ``V(node)``/``I(device)`` references, numeric
  literals, and ``+ - * / ** %`` operators. Disallowed constructs
  (calls, attribute, subscript, comparisons) raise `InvalidExpression`.
- `RawRead.to_csv(path)` — write every trace to CSV. Complex traces
  expand into `<name>.re` / `<name>.im` column pairs.
- `RawRead.to_dataframe()` — requires the new ``[dataframe]`` extra
  (``pip install 'sim-ltspice[dataframe]'``); returns a ``pandas.DataFrame``
  with the axis as index and one column per non-axis trace.
- `sim_ltspice.raw` now exports `RawRead`, `Variable`, and
  `UnsupportedRawFormat` alongside the original `trace_names` helper, which
  stays available for callers that only need names.
- `numpy>=1.24` is now a runtime dependency.

### Changed
- `run_net` now enforces a default 300-second subprocess timeout
  (`sim_ltspice.runner.DEFAULT_TIMEOUT_S`). On timeout the child is
  terminated and the returned `RunResult` has `exit_code=124` and a
  `stderr` explaining the hang — no `TimeoutExpired` propagates. This
  fails fast on the Windows SSH session-0 hazard where LTspice never
  produces output. Pass `timeout=None` to restore the pre-0.2
  unbounded behaviour, or any positive float to tighten the bound.

### Known gaps (tracked for v0.2+)
- `fastaccess` transposed layout — deferred; currently raises
  `UnsupportedRawFormat`.
- Run-diff helpers (`diff(a, b, traces=..., tolerance=...)`) — PR 4 of
  Stage 2f.

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
