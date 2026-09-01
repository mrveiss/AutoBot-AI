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


def test_a_sentinel_zero_default_does_not_fail_a_real_port(guard, tmp_path, monkeypatch):
    """`default=0` means "not configured", not "port zero".

    `AUTOBOT_SMTP_PORT` and `AUTOBOT_POSTGRES_PORT` were the examples this was
    written against; both have since had their pre-#7437 values restored under
    #13264 (587 and 5432). `REDIS_PORT` still carries `default=0` in the live
    SSOT, so the clause is not hypothetical — and comparing
    `${AUTOBOT_POSTGRES_PORT:-5432}` against 0 would fail correct code, which
    is the shape this guard exists to permit rather than block.
    """
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text(
        'postgres_port: int = Field(default=0, alias="AUTOBOT_POSTGRES_PORT")\n'
        'browser: int = Field(default=9001, alias="AUTOBOT_BROWSER_SERVICE_PORT")\n',
        encoding="utf-8",
    )
    (tmp_path / "pg.sh").write_text('psql -p "${AUTOBOT_POSTGRES_PORT:-5432}"\n', encoding="utf-8")

    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard, "_shell_files", lambda root: ["pg.sh"])

    assert guard.main([]) == 0


def test_the_real_ssot_sentinels_are_excluded(guard):
    """Pins the sentinel against the actual SSOT, so this stops being an
    assumption if it gains a real default later.

    `AUTOBOT_SMTP_PORT` is what that clause was written for: it was a sentinel
    until #13264 restored its pre-#7437 default of 587, and this test is what
    caught the change rather than letting it pass silently. It is now asserted
    as a real, comparable port.

    `AUTOBOT_POSTGRES_PORT` followed the same path in #13264 batch 3 — it was a
    sentinel only because the #7437 migration had replaced its shipped 5432
    with 0, and this test caught that restoration too. Both are now real ports;
    the sentinel-exclusion clause itself is still exercised by
    `test_an_all_sentinel_ssot_is_fatal_not_clean` below."""
    root = guard._repo_root()
    ports = guard._ssot_ports(root)

    assert ports.get("AUTOBOT_POSTGRES_PORT") == "5432", "restored by #13264 batch 3; no longer a sentinel"
    assert ports.get("AUTOBOT_SMTP_PORT") == "587", "restored by #13264; no longer a sentinel"
    assert ports.get("AUTOBOT_BROWSER_SERVICE_PORT") == "9001", "the real port this guard exists for"
    assert ports.get("AUTOBOT_GRAFANA_PORT") == "3000", "3000 belongs to Grafana — the whole point of #14198"


def test_an_all_sentinel_ssot_is_fatal_not_clean(guard, tmp_path, monkeypatch):
    """The fatal check must run on the map actually used for comparison.

    Review finding: the emptiness check ran on the *pre-filter* dict, so an
    SSOT where every real port had been turned into `default=0` left it
    non-empty while the comparison map was empty. Every fallback then read as
    "no SSOT entry" and the guard printed a clean verdict. Reproduced against
    the real code: a diverging `${AUTOBOT_BROWSER_SERVICE_PORT:-3000}` exited 0.
    """
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text(
        'browser: int = Field(default=0, alias="AUTOBOT_BROWSER_SERVICE_PORT")\n'
        'backend: int = Field(default=0, alias="AUTOBOT_BACKEND_PORT")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        guard._ssot_ports(tmp_path)

    assert "refusing to report clean" in str(excinfo.value)


def test_the_diverging_fallback_still_fails_when_some_ports_are_sentinels(guard, tmp_path, monkeypatch):
    """A mixed SSOT — some sentinels, some real — must still catch divergence.

    Pins that the fatal check above did not over-correct into rejecting the
    ordinary case the sentinel handling exists to support.
    """
    (tmp_path / "autobot_shared").mkdir()
    (tmp_path / "autobot_shared" / "ssot_config.py").write_text(
        'postgres_port: int = Field(default=0, alias="AUTOBOT_POSTGRES_PORT")\n'
        'browser: int = Field(default=9001, alias="AUTOBOT_BROWSER_SERVICE_PORT")\n',
        encoding="utf-8",
    )
    (tmp_path / "bad.sh").write_text(
        'psql -p "${AUTOBOT_POSTGRES_PORT:-5432}"\n'
        'curl "http://h:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/health"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard, "_shell_files", lambda root: ["bad.sh"])

    assert guard.main([]) == 1
