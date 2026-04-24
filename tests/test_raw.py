"""Tests for sim_ltspice.raw.RawRead — binary `.raw` waveform parser.

Fixtures in ``tests/fixtures/raw/`` were produced on macOS LTspice 17.2.4
from the netlists in ``tmp/`` of the sim-proj workspace; they cover
the five layouts RawRead must decode:

- ``tran_rc`` — ``Flags: real forward`` (default transient)
- ``op_rdiv`` — ``Flags: real`` (``.op``: axis-less single-point)
- ``ac_rlc`` — ``Flags: complex forward log`` (complex128 everywhere)
- ``step_rc`` — ``Flags: real forward stepped`` (param sweep concatenated)
- ``noise_rc`` — ``Flags: real forward log`` (``.noise`` with gain trace)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sim_ltspice import RawRead, UnsupportedRawFormat, trace_names

FIX = Path(__file__).parent / "fixtures" / "raw"


class TestTransientDefault:
    """Default LTspice layout: float64 time axis + float32 signal traces."""

    def setup_method(self):
        self.rr = RawRead(FIX / "tran_rc.raw")

    def test_metadata(self):
        assert self.rr.plotname == "Transient Analysis"
        assert self.rr.flags == {"real", "forward"}
        assert self.rr.n_points == 321
        assert self.rr.n_variables == 6

    def test_trace_names_match_header(self):
        assert self.rr.trace_names() == [
            "time", "V(in)", "V(out)", "I(C1)", "I(R1)", "I(V1)",
        ]

    def test_axis_is_monotone_non_decreasing(self):
        t = self.rr.axis
        assert t.dtype == np.float64
        assert t[0] == 0.0
        assert t[-1] == pytest.approx(0.005, rel=1e-6)
        # Transient time axis is monotonic (compressed points already
        # absolute-valued in __init__).
        assert np.all(np.diff(t) >= -1e-15)

    def test_trace_returns_float64(self):
        v_out = self.rr.trace("V(out)")
        assert v_out.dtype == np.float64
        assert v_out.shape == (321,)

    def test_pulse_ramps_high(self):
        """V(in) is a PULSE(0,1,...) — must cross 0.5 at least once."""
        v_in = self.rr.trace("V(in)")
        assert v_in.max() >= 0.99

    def test_rc_filter_attenuates_edge(self):
        """The RC filter smooths the pulse — V(out) peak <= V(in) peak."""
        assert self.rr.trace("V(out)").max() <= self.rr.trace("V(in)").max() + 1e-6

    def test_trace_missing_raises(self):
        with pytest.raises(KeyError, match="not found"):
            self.rr.trace("V(no_such_node)")

    def test_case_insensitive_fallback(self):
        """LTspice is inconsistent about case — make sure lookup copes."""
        low = self.rr.trace("v(out)")
        exact = self.rr.trace("V(out)")
        np.testing.assert_array_equal(low, exact)


class TestOperatingPoint:
    """``.op`` produces 1 point but still uses the real-default layout."""

    def setup_method(self):
        self.rr = RawRead(FIX / "op_rdiv.raw")

    def test_metadata(self):
        assert self.rr.plotname == "Operating Point"
        assert self.rr.flags == {"real"}
        assert self.rr.n_points == 1

    def test_divider_values(self):
        """V1 in 0 5 / R1 in mid 1k / R2 mid 0 2k → V(mid)=10/3 V."""
        assert self.rr.trace("V(in)")[0] == pytest.approx(5.0, rel=1e-6)
        assert self.rr.trace("V(mid)")[0] == pytest.approx(10.0 / 3.0, rel=1e-5)
        # Current through divider: 5 V / 3 kΩ = 1.6666... mA
        assert self.rr.trace("I(R1)")[0] == pytest.approx(5e-3 / 3.0, rel=1e-4)

    def test_not_complex(self):
        assert self.rr.is_complex is False


class TestACComplex:
    """``.ac`` stores complex128 for both axis and all traces."""

    def setup_method(self):
        self.rr = RawRead(FIX / "ac_rlc.raw")

    def test_metadata(self):
        assert self.rr.plotname == "AC Analysis"
        assert self.rr.flags == {"complex", "forward", "log"}
        assert self.rr.is_complex is True

    def test_axis_is_complex_but_real_valued(self):
        """Frequency is declared complex but imaginary parts must be zero."""
        f = self.rr.axis
        assert f.dtype == np.complex128
        assert np.allclose(f.imag, 0.0)
        assert f[0].real == pytest.approx(10.0)
        assert f[-1].real == pytest.approx(1e6)

    def test_source_amplitude_is_unity(self):
        """V1 in 0 AC 1 → V(in) ≡ 1+0j at every frequency."""
        v_in = self.rr.trace("V(in)")
        assert v_in.dtype == np.complex128
        assert np.allclose(v_in, 1 + 0j, atol=1e-9)

    def test_vout_has_phase_shift(self):
        """RLC band-pass must produce non-zero imaginary components."""
        v_out = self.rr.trace("V(out)")
        assert np.abs(v_out.imag).max() > 1e-3


class TestSteppedSweep:
    """``.step`` concatenates multiple sweeps into one body."""

    def setup_method(self):
        self.rr = RawRead(FIX / "step_rc.raw")

    def test_metadata(self):
        assert self.rr.plotname == "Transient Analysis"
        assert self.rr.is_stepped is True
        assert self.rr.n_points == 699

    def test_axis_resets_per_step(self):
        """Monotonicity breaks at step boundaries; at least 2 resets for 3 steps."""
        t = self.rr.axis
        # Points where the axis decreases signal a new sweep.
        decreases = np.sum(np.diff(t) < 0)
        assert decreases >= 2


class TestNoise:
    """``.noise`` is a real-forward log sweep with gain/V(onoise)/V(inoise)."""

    def setup_method(self):
        self.rr = RawRead(FIX / "noise_rc.raw")

    def test_metadata(self):
        assert self.rr.plotname.startswith("Noise Spectral Density")
        assert self.rr.flags == {"real", "forward", "log"}
        assert self.rr.output == "out"

    def test_gain_and_noise_traces(self):
        names = self.rr.trace_names()
        # frequency + gain + the noise contribution traces
        assert names[:2] == ["frequency", "gain"]
        # RC low-pass: gain near DC ≈ 1.
        assert self.rr.trace("gain")[0] == pytest.approx(1.0, abs=1e-3)


class TestUnsupported:
    def _forge_header(self, flags: str) -> bytes:
        """Build a minimal UTF-16 LE header with arbitrary Flags."""
        header = (
            f"Title: forged\n"
            f"Plotname: Operating Point\n"
            f"Flags: {flags}\n"
            f"No. Variables: 1\n"
            f"No. Points: 1\n"
            f"Offset: 0\n"
            f"Command: sim-ltspice test\n"
            f"Variables:\n"
            f"\t0\tV(x)\tvoltage\n"
            f"Binary:\n"
        )
        return header.encode("utf-16-le")

    def test_fastaccess_rejected(self, tmp_path):
        p = tmp_path / "fast.raw"
        # one float64 value so the size check doesn't fire first.
        p.write_bytes(self._forge_header("real fastaccess") + b"\x00" * 8)
        with pytest.raises(UnsupportedRawFormat, match="fastaccess"):
            RawRead(p)

    def test_missing_sentinel_rejected(self, tmp_path):
        p = tmp_path / "garbage.raw"
        p.write_bytes("Not an LTspice .raw file\n".encode("utf-16-le"))
        with pytest.raises(UnsupportedRawFormat, match="sentinel"):
            RawRead(p)

    def test_size_mismatch_rejected(self, tmp_path):
        p = tmp_path / "short.raw"
        # Header declares 1 point but body is empty.
        p.write_bytes(self._forge_header("real") + b"")
        with pytest.raises(UnsupportedRawFormat, match="body size"):
            RawRead(p)


class TestBackCompat:
    def test_trace_names_function_still_works(self):
        """The pre-v0.2 module-level ``trace_names`` helper must keep working."""
        names = trace_names(FIX / "tran_rc.raw")
        assert names == ["time", "V(in)", "V(out)", "I(C1)", "I(R1)", "I(V1)"]
