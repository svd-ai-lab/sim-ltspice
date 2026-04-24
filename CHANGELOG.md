# Changelog

## [0.2.1] — 2026-04-24

### Fixed
- `log.parse_log` now parses AC-analysis `.meas` output. The previous
  regex only matched plain scalar RHS + `FROM/TO`, so the macOS LTspice
  17.2.4 log for an AC sweep came back with `measures == {}` even when
  every directive was evaluated correctly. The rewrite handles:
  - Complex RHS `(-0.0123613dB,0°)` — magnitude lands in `Measure.value`,
    phase in `Measure.phase_deg`.
  - `AT <freq>` / lowercase `at` suffix — axis point lands in `Measure.at`.
  - WHEN-style measures where the RHS is an expression like
    `peakmag*0.7071` — `Measure.value` is the AT axis point.
  - CRLF line endings in the `.meas` block (LTspice 17 macOS mixes CRLF
    meas lines with LF preamble; an anchored `$` under `re.MULTILINE`
    quietly missed every one).

### Added
- `Measure.at` — axis point (frequency for AC, time for TRAN) for
  `AT`-suffixed measurements.
- `Measure.phase_deg` — phase in degrees for AC complex results.
- `Measure.rhs_value` — the raw scalar right-hand side. Lets callers
  disambiguate TRAN `FIND … AT` (measured value in RHS) from TRAN
  `WHEN` (target value in RHS) even though the two forms are
  identical in the log. See `Measure` docstring for the contract.

All three fields default to `None` so existing callers keep working.

## [0.2.0] — 2026-04-24

Closes Stage 2f: `.raw` waveform data access is now a first-class API.
A run, a cursor query, a CSV export, and a two-run regression diff are
all reachable without ever opening the LTspice waveform viewer.

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
- `sim_ltspice.diff.diff(a, b)` — two-run comparison helper for
  regression testing. Accepts paths or pre-loaded `RawRead` objects.
  Uses `numpy.allclose`-style tolerance (``|a-b| <= atol + rtol*|b|``).
  Returns a frozen `DiffResult` with per-trace `TraceDiff` records
  (max_abs / max_rel / within_tol), plus set-difference reporting
  (`only_in_a` / `only_in_b`) and axis-mismatch diagnostics. Works on
  real and complex traces.
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

### Known gaps (tracked for v0.3+)
- `fastaccess` transposed layout — deferred; currently raises
  `UnsupportedRawFormat`.

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
