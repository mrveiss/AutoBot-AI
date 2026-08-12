# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the port-fallback/SSOT agreement guard (#14198)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_port_fallbacks_match_ssot.py")


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location("check_port_fallbacks", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_fallback_pattern_reads_variable_and_literal(guard):
    match = guard._FALLBACK.search('URL="http://h:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/health"')
    assert match and match.group(1) == "AUTOBOT_BROWSER_SERVICE_PORT" and match.group(2) == "3000"


@pytest.mark.parametrize(
    "line",
    [
        '${AUTOBOT_BACKEND_PORT}',                 # no fallback at all
        '${AUTOBOT_BACKEND_PORT:-$OTHER}',         # non-numeric fallback
        '${SOME_OTHER_PORT:-8001}',                # not an AUTOBOT_* variable
        '${AUTOBOT_BASE_DIR:-/opt/autobot}',       # not a port
    ],
)
def test_shapes_that_are_not_a_numeric_port_fallback_are_ignored(guard, line):
    assert guard._FALLBACK.search(line) is None


def test_the_ssot_pattern_reads_a_real_field(guard):
    field = 'browser: int = Field(default=9001, alias="AUTOBOT_BROWSER_SERVICE_PORT")  # Issue #4052'
    match = guard._SSOT_FIELD.search(field)
    assert match and match.group(1) == "9001" and match.group(2) == "AUTOBOT_BROWSER_SERVICE_PORT"


def test_the_repository_currently_agrees_with_the_ssot(guard):
    """End-to-end against the real tree and the real SSOT.

    The unit assertions above only prove the regexes parse a hand-written
    string. This one runs the guard exactly as the hook does, so it fails if
    the SSOT moves, a new diverging fallback appears, or either pattern stops
    matching the shapes actually in the tree.
    """
    assert guard.main([]) == 0


def test_a_diverging_fallback_is_reported(guard, tmp_path, monkeypatch):
    """The invariant: a fallback that disagrees with the SSOT fails.

    Driven through the real `main()` against a synthetic repo, so the git
    plumbing, the SSOT parse and the scan all run — not a hand-called helper.
    """
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text(
        'browser: int = Field(default=9001, alias="AUTOBOT_BROWSER_SERVICE_PORT")\n', encoding="utf-8"
    )
    (tmp_path / "bad.sh").write_text('curl "http://h:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/health"\n', encoding="utf-8")

    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard, "_shell_files", lambda root: ["bad.sh"])

    assert guard.main([]) == 1


def test_an_agreeing_fallback_passes(guard, tmp_path, monkeypatch):
    """145 fallbacks in the tree agree with the SSOT; banning the shape would
    have meant churning all of them to fix one defect. Only divergence fails."""
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text(
        'browser: int = Field(default=9001, alias="AUTOBOT_BROWSER_SERVICE_PORT")\n', encoding="utf-8"
    )
    (tmp_path / "ok.sh").write_text('curl "http://h:${AUTOBOT_BROWSER_SERVICE_PORT:-9001}/health"\n', encoding="utf-8")

    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard, "_shell_files", lambda root: ["ok.sh"])

    assert guard.main([]) == 0


def test_a_variable_with_no_ssot_entry_does_not_fail_the_build(guard, tmp_path, monkeypatch):
    """Unverifiable is reported, not failed — those families are #14173's call."""
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text(
        'browser: int = Field(default=9001, alias="AUTOBOT_BROWSER_SERVICE_PORT")\n', encoding="utf-8"
    )
    (tmp_path / "vnc.sh").write_text('echo "${AUTOBOT_VNC_SERVER_PORT:-5902}"\n', encoding="utf-8")

    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard, "_shell_files", lambda root: ["vnc.sh"])

    assert guard.main([]) == 0


def test_an_unparseable_ssot_is_fatal_not_clean(guard, tmp_path, monkeypatch):
    """No SSOT fields parsed means the pattern drifted — every comparison would
    then be 'unverifiable' and the guard would report a clean tree it never
    actually checked."""
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text("# nothing parseable\n", encoding="utf-8")
    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        guard._ssot_ports(tmp_path)

    assert "pattern has drifted" in str(excinfo.value)


def test_an_empty_file_listing_is_fatal_not_clean(guard, monkeypatch):
    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: _Result())

    with pytest.raises(SystemExit) as excinfo:
        guard._shell_files(Path("."))

    assert "refusing to report clean" in str(excinfo.value)
