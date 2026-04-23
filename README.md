# sim-ltspice

Python API for **LTspice**, the free SPICE3 circuit simulator from Analog Devices.

[LTspice](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html) ships no Python API of its own. This library fills that gap — think of it as the equivalent of `pyfluent` or `matlabengine`, but for LTspice. It parses and emits every LTspice file format, indexes the shipped symbol library, and exposes a layout engine that turns a netlist into a reviewable `.asc` schematic.

> **Status:** v0.1 is under construction. See `CHANGELOG.md` for what's landed.

## What you'll be able to do

```python
from sim_ltspice import Schematic, write_asc
from sim_ltspice.layout import net_to_schematic

# Turn a netlist into a schematic a human can open in LTspice
schem = net_to_schematic("""
V1 in 0 PULSE(0 1 0 1u 1u 1m 2m)
R1 in out 1k
C1 out 0 100n
.tran 5m
.meas TRAN vout_pk MAX V(out)
""")
write_asc(schem, "rc_lowpass.asc")     # open in LTspice GUI — real schematic view
```

```python
from sim_ltspice import run_net, parse_log

result = run_net("rc_lowpass.net")     # invokes local LTspice batch mode
log    = parse_log(result.log_path)    # structured .MEAS + errors + warnings
print(log.measures["vout_pk"].value)   # 0.9999...
```

## Why

EEs review designs as schematics, not netlists. The sim-cli project drives LTspice for agent-written designs, and without a schematic-writer, there was no way for a human to review what an agent produced. This library produces `.asc` files that LTspice renders as proper schematics, so reviews stay in the GUI people already use.

Useful standalone (no sim-cli dependency) for:
- Scripting LTspice from notebooks
- Monte-Carlo / parameter sweeps outside the GUI
- Reading `.raw` waveforms and `.log` measurements without LTspice's interactive plotter
- Building higher-level tooling (optimizers, auto-testers, CI gates for circuit designs)

## Install

```bash
uv pip install sim-ltspice
```

Requires Python ≥ 3.10. LTspice itself is needed only for simulation (`run_net` / `run_asc`); parsing and layout work without it.

## Platforms

| Platform | Parsing / layout / writing | Simulation |
|---|---|---|
| macOS (native LTspice 17.x) | ✅ | `.net` direct; `.asc` only for flat, library-local schematics |
| Windows (LTspice 26.x) | ✅ | `.net` and `.asc` (uses LTspice's own `-netlist`) |
| Linux (wine + LTspice 17.x) | ✅ | via wine |

## Relation to other projects

- **[sim-cli](https://github.com/svd-ai-lab/sim-cli)** — unified CLI that orchestrates CAE/EDA solvers for LLM agents. Its LTspice driver is a thin adapter over this library.
- **[spicelib](https://github.com/nunobrum/spicelib)** — a separate project with different scope; great for editing existing `.asc` files, but doesn't create schematics from netlists or generate layouts.
- **[PyLTSpice](https://github.com/nunobrum/PyLTSpice)** — wrapper on top of spicelib for running LTspice batches.

## License

Apache-2.0 — see [LICENSE](./LICENSE).
