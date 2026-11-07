# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Logs never land in the source tree (#20894)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from autobot_shared import log_dir
from autobot_shared.log_dir import resolve_logs_dir

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (log_dir.LOGS_DIR_ENV, log_dir.DEPRECATED_LOGS_DIR_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(log_dir, "_warned_alias", False)


def test_unset_resolves_outside_the_repo_and_the_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = resolve_logs_dir()
    assert resolved.is_absolute()
    assert not resolved.is_relative_to(REPO_ROOT)
    assert not resolved.is_relative_to(tmp_path)


def test_unset_outside_pytest_is_the_xdg_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_dir, "_under_pytest", lambda: False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert resolve_logs_dir() == tmp_path / "state" / "autobot" / "logs"
    monkeypatch.setenv("XDG_STATE_HOME", "relative/state")  # the spec: a relative value is ignored
    assert resolve_logs_dir() == Path.home() / ".local" / "state" / "autobot" / "logs"


def test_the_env_var_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(log_dir.LOGS_DIR_ENV, str(tmp_path / "configured"))
    assert resolve_logs_dir() == tmp_path / "configured"


def test_a_relative_value_is_anchored_at_the_install_base_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, elsewhere = tmp_path / "base", tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("AUTOBOT_BASE_DIR", str(base))
    monkeypatch.setenv(log_dir.LOGS_DIR_ENV, "var/logs")
    monkeypatch.chdir(elsewhere)
    assert resolve_logs_dir() == base / "var" / "logs"


def test_the_deprecated_alias_is_read_and_warns_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(log_dir.DEPRECATED_LOGS_DIR_ENV, str(tmp_path / "legacy"))
    with caplog.at_level(logging.WARNING, logger=log_dir.__name__):
        assert resolve_logs_dir() == tmp_path / "legacy"
        assert resolve_logs_dir() == tmp_path / "legacy"
    warnings = [r for r in caplog.records if "deprecated" in r.getMessage()]
    assert len(warnings) == 1


def test_the_one_name_wins_over_the_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(log_dir.LOGS_DIR_ENV, str(tmp_path / "new"))
    monkeypatch.setenv(log_dir.DEPRECATED_LOGS_DIR_ENV, str(tmp_path / "old"))
    assert resolve_logs_dir() == tmp_path / "new"


_WRITER = (
    "from autobot_shared.logging_manager import get_logger\n"
    "get_logger('probe', 'backend').error('written by #20894 test')\n"
)


def test_a_logger_write_leaves_no_logs_dir_in_the_cwd_or_the_repo_root(tmp_path: Path) -> None:
    """A fresh process, cwd a scratch dir, nothing configured: the write lands outside both trees."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    state = tmp_path / "state"
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT), "XDG_STATE_HOME": str(state), "HOME": str(tmp_path)}
    repo_logs_before = (REPO_ROOT / "logs").exists()
    result = subprocess.run(  # noqa: S603  # nosec B603  # fixed interpreter and inline script
        [sys.executable, "-c", _WRITER],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert not (cwd / "logs").exists()
    assert (REPO_ROOT / "logs").exists() == repo_logs_before
    assert list((state / "autobot" / "logs").glob("*.log")), "the write went somewhere else"
