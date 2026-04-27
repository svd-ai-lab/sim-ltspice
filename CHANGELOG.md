# Changelog

## [0.2.3] — 2026-04-27

### Added
- `run_net(..., ini=Path|None, sym_paths=Sequence[Path])` and
  `run_asc(..., ini=, sym_paths=)` — surface two LTspice CLI flags
  that previously had no Python knob:
  - `-ini <path>`: override the per-user settings file
    (`%APPDATA%\LTspice.ini` on Windows). Lets CI runs use a clean
    fixture ini so host state (window positions, recent files,
    persisted search paths) doesn't bleed into results.
  - `-I<path>`: inject extra symbol/library search paths for one run
    without modifying the user-data `lib/`. LTspice docs require
    `-I<path>` to be the *last* argument with *no* space after `-I`;
    `run_net` constructs argv accordingly.
- `sim_ltspice.cmp` — new module that parses LTspice's bundled
  `lib/cmp/standard.{bjt,mos,dio,jft,cap,ind,res,bead}` files (the
  closed enum of generic SPICE models). All eight files are UTF-16,
  with a mix of BOM-prefixed and bare files; `_read_utf16` handles
  both. Public API:
  - `parse_cmp(path, *, kind=None) -> list[ModelDef]` — single-file parser.
  - `ComponentModelCatalog` — auto-discovers `lib/cmp/` from the
    `LTSPICE_CMP_PATH` env var or the platform user-data dir
    (`%LOCALAPPDATA%\LTspice\lib\cmp\` on Windows,
    `~/Library/Application Support/LTspice/lib/cmp/` on macOS).
    Methods: `find(name)`, `models(kind)`, `names()`, `kinds()`,
    plus `__contains__`/`__iter__`/`__len__`. Construct with
    `search_paths=[...]` to override discovery.
  - `ModelDef(name, kind, type, source)` frozen dataclass.

### Why
Result of the LTspice 26 reverse-engineering work in
[svd-ai-lab/sim-proj#50](https://github.com/svd-ai-lab/sim-proj/issues/50).
The `-ini` knob unlocks reproducible CI runs that were previously
sensitive to the host's persisted GUI state. The cmp catalogue
unlocks offline `Value <model>` lint — flagging `Q1 c b e 2N9999` at
parse time rather than mid-simulation.

## [0.2.2] — 2026-04-26

### Added
- `run_asc(script, *, install=None, catalog=None, timeout=...)` — closes
  the GUI-free authoring loop. Reads the `.asc`, flattens via
  `schematic_to_netlist` (default `SymbolCatalog()` auto-discovers from
  `$LTSPICE_SYM_PATH` or the platform `lib/sym/` tree), writes a sibling
  `.net`, and delegates to `run_net`. No LTspice binary participates in
  the authoring path — only in the actual solve.

  Raises `UnsupportedInput` for non-`.asc` inputs, `FlattenError` for
  symbols the catalog can't resolve, and (from `run_net`)
  `LtspiceNotInstalled` if no install is discoverable.

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
