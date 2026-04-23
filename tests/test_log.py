"""Unit tests for sim_ltspice.log."""
from __future__ import annotations

import pytest

from sim_ltspice.log import parse_log, read_log


class TestReadLogEncoding:
    def test_utf16_le_no_bom(self, tmp_path):
        p = tmp_path / "mac.log"
        p.write_bytes("vout_pk: MAX(v(out))=0.999 FROM 0 TO 0.005\n".encode("utf-16-le"))
        assert "vout_pk" in read_log(p)

    def test_utf8_plain(self, tmp_path):
        p = tmp_path / "win.log"
        p.write_text(
            "LTspice 26.0.1 for Windows\n"
            "vout_pk: MAX(V(out))=0.999 FROM 0 TO 0.005\n",
            encoding="utf-8",
        )
        assert "vout_pk" in read_log(p)

    def test_utf8_with_bom(self, tmp_path):
        p = tmp_path / "bom.log"
        p.write_bytes("\ufeffvout_pk: MAX(v(out))=1.0\n".encode("utf-8"))
        assert read_log(p).startswith("vout_pk")

    def test_missing_file(self, tmp_path):
        assert read_log(tmp_path / "does-not-exist.log") == ""


class TestParseLog:
    def test_measure_with_from_to(self):
        text = (
            "solver = Normal\n"
            "vout_pk: MAX(v(out))=0.999955 FROM 0 TO 0.005\n"
            "Total elapsed time: 0.003 seconds.\n"
        )
        out = parse_log(text)
        m = out.measures["vout_pk"]
        assert m.value == pytest.approx(0.999955)
        assert m.window_from == 0.0
        assert m.window_to == 0.005
        assert m.expr == "MAX(v(out))"
        assert out.elapsed_s == pytest.approx(0.003)
        assert out.errors == []
        assert out.warnings == []

    def test_measure_with_unit_suffix(self):
        text = "gain: V(out)/V(in)=2.5V\n"
        assert parse_log(text).measures["gain"].value == pytest.approx(2.5)

    def test_errors_flagged(self):
        text = (
            "Error: convergence failed at step 1\n"
            "Singular matrix\n"
            "Total elapsed time: 0.001 seconds.\n"
        )
        out = parse_log(text)
        assert len(out.errors) >= 1

    def test_warnings_flagged(self):
        out = parse_log("WARNING: node N001 floating\nOK\n")
        assert len(out.warnings) == 1
        assert "floating" in out.warnings[0]

    def test_windows_drive_letter_is_not_a_measure(self):
        text = (
            "LTspice 26.0.1 for Windows\n"
            "Files loaded:\n"
            "C:\\Users\\jiwei\\tmp\\rc.net\n"
            "\n"
            "vout_pk: MAX(V(out))=0.999954938889 FROM 0 TO 0.005\n"
            "Total elapsed time: 0.061 seconds.\n"
        )
        out = parse_log(text)
        assert list(out.measures.keys()) == ["vout_pk"]
        assert out.measures["vout_pk"].value == pytest.approx(0.999955, rel=1e-4)
        assert out.measures["vout_pk"].expr == "MAX(V(out))"
