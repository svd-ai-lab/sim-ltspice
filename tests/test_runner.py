"""Runner tests — unit coverage without LTspice invocation."""
from __future__ import annotations

from pathlib import Path

import pytest

from sim_ltspice import NETLIST_SUFFIXES, LtspiceNotInstalled, UnsupportedInput, run_net


FIXTURES = Path(__file__).parent / "fixtures"


def test_known_suffixes_accepted():
    assert set(NETLIST_SUFFIXES) == {".net", ".cir", ".sp"}


def test_raises_on_wrong_suffix(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("not a netlist")
    with pytest.raises(UnsupportedInput):
        run_net(p)


def test_raises_when_not_installed(monkeypatch):
    monkeypatch.setattr("sim_ltspice.runner.find_ltspice", lambda: [])
    with pytest.raises(LtspiceNotInstalled):
        run_net(FIXTURES / "ltspice_good.net")


@pytest.mark.integration
def test_rc_transient_runs_end_to_end(tmp_path):
    """Real LTspice batch. Skipped if no install is visible."""
    import shutil

    from sim_ltspice import find_ltspice

    if not find_ltspice():
        pytest.skip("LTspice not installed on this host")

    net = tmp_path / "rc.net"
    shutil.copyfile(FIXTURES / "ltspice_good.net", net)

    result = run_net(net)
    assert result.exit_code == 0, f"stderr: {result.stderr}"
    assert result.ok, f"log errors: {result.log.errors}"
    assert "vout_pk" in result.log.measures
    assert result.log.measures["vout_pk"].value == pytest.approx(1.0, rel=5e-3)
    assert "V(out)" in result.raw_traces
    assert result.log_path and result.log_path.is_file()
    assert result.raw_path and result.raw_path.is_file()
