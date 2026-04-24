"""Runner tests — unit coverage without LTspice invocation."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sim_ltspice import NETLIST_SUFFIXES, LtspiceNotInstalled, UnsupportedInput, run_net
from sim_ltspice.runner import DEFAULT_TIMEOUT_S


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


class TestTimeout:
    """Default 300-second timeout must survive into the subprocess call."""

    def _stub_install(self, monkeypatch, tmp_path):
        """Return a fake LTspice install so find_ltspice() is short-circuited."""
        from sim_ltspice.install import Install

        fake_exe = tmp_path / "LTspice"
        fake_exe.write_text("#!/bin/sh\nexit 0\n")
        fake_exe.chmod(0o755)
        fake = Install(
            exe=fake_exe, version="test", path=str(tmp_path), source="test"
        )
        monkeypatch.setattr("sim_ltspice.runner.find_ltspice", lambda: [fake])

    def test_default_timeout_is_300s(self, monkeypatch, tmp_path):
        """The default timeout is exposed as a module-level constant."""
        assert DEFAULT_TIMEOUT_S == 300.0

    def test_default_timeout_propagates_to_subprocess(self, monkeypatch, tmp_path):
        """If caller doesn't pass ``timeout=``, subprocess.run sees 300s."""
        self._stub_install(monkeypatch, tmp_path)
        captured: dict[str, object] = {}

        def fake_run(*_args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr("sim_ltspice.runner.subprocess.run", fake_run)
        script = tmp_path / "rc.net"
        script.write_text("* empty\n.end\n")
        run_net(script)
        assert captured["timeout"] == DEFAULT_TIMEOUT_S

    def test_explicit_none_disables_timeout(self, monkeypatch, tmp_path):
        """Passing ``timeout=None`` restores pre-0.2 unbounded behaviour."""
        self._stub_install(monkeypatch, tmp_path)
        captured: dict[str, object] = {}

        def fake_run(*_args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr("sim_ltspice.runner.subprocess.run", fake_run)
        script = tmp_path / "rc.net"
        script.write_text("* empty\n.end\n")
        run_net(script, timeout=None)
        assert captured["timeout"] is None

    def test_custom_timeout_wins(self, monkeypatch, tmp_path):
        self._stub_install(monkeypatch, tmp_path)
        captured: dict[str, object] = {}

        def fake_run(*_args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr("sim_ltspice.runner.subprocess.run", fake_run)
        script = tmp_path / "rc.net"
        script.write_text("* empty\n.end\n")
        run_net(script, timeout=5.0)
        assert captured["timeout"] == 5.0

    def test_timeout_yields_failure_result_not_exception(self, monkeypatch, tmp_path):
        """A TimeoutExpired from subprocess translates to exit_code=124."""
        self._stub_install(monkeypatch, tmp_path)

        def fake_run(*_args, **kwargs):
            raise subprocess.TimeoutExpired(
                cmd="LTspice", timeout=kwargs.get("timeout", 0), output="", stderr=""
            )

        monkeypatch.setattr("sim_ltspice.runner.subprocess.run", fake_run)
        script = tmp_path / "rc.net"
        script.write_text("* empty\n.end\n")
        result = run_net(script, timeout=0.1)
        assert result.exit_code == 124
        assert "timed out" in result.stderr
        assert "session-0" in result.stderr  # keep the Windows-SSH hint


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
