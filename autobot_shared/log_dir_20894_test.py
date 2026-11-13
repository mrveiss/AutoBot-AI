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


def test_no_resolvable_home_falls_back_to_a_temp_dir_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    def _no_home() -> Path:
        raise RuntimeError("Could not determine home directory")

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))
    resolved = resolve_logs_dir()
    assert resolved.is_absolute() and resolved.parts[-2:] == ("autobot", "logs")
    assert not resolved.is_relative_to(REPO_ROOT)


def test_unset_is_the_xdg_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.parametrize("blank", ["", " ", "\t ", "\n"])
def test_a_blank_value_is_absent_not_a_relative_directory(
    blank: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(log_dir.LOGS_DIR_ENV, blank)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert resolve_logs_dir() == tmp_path / "autobot" / "logs"
    monkeypatch.setenv(log_dir.DEPRECATED_LOGS_DIR_ENV, blank)  # the alias is treated the same way
    assert resolve_logs_dir() == tmp_path / "autobot" / "logs"
    assert resolve_logs_dir(blank) == tmp_path / "autobot" / "logs"


def test_the_one_name_wins_over_the_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(log_dir.LOGS_DIR_ENV, str(tmp_path / "new"))
    monkeypatch.setenv(log_dir.DEPRECATED_LOGS_DIR_ENV, str(tmp_path / "old"))
    assert resolve_logs_dir() == tmp_path / "new"


def test_both_env_planes_declare_the_one_default() -> None:
    """The env registry and ``PathConfig`` take ``AUTOBOT_LOGS_DIR``'s default from one constant (#17419)."""
    from autobot_shared.env_registry import REGISTRY
    from autobot_shared.ssot_config import PathConfig

    assert REGISTRY[log_dir.LOGS_DIR_ENV].default == log_dir.LOGS_DIR_DEFAULT
    assert PathConfig.model_fields["logs_dir"].default == log_dir.LOGS_DIR_DEFAULT


def test_path_config_logs_path_is_the_resolver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from autobot_shared.ssot_config import PathConfig

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert PathConfig(_env_file=None).logs_path == resolve_logs_dir()
    monkeypatch.setenv(log_dir.LOGS_DIR_ENV, str(tmp_path / "set"))
    assert PathConfig(_env_file=None).logs_path == tmp_path / "set"


def test_the_handler_touches_nothing_until_the_first_record(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "logs" / "x.log"
    handler = log_dir.FirstWriteFileHandler(str(target))
    try:
        assert not target.parent.exists()
        handler.emit(logging.LogRecord("t", logging.ERROR, __file__, 1, "first", None, None))
        handler.flush()
        assert target.read_text(encoding="utf-8").strip() == "first"
    finally:
        handler.close()


def test_an_unwritable_directory_turns_the_handler_off_once(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")  # a file where the directory goes: mkdir fails
    seen: list[Path] = []
    handler = log_dir.FirstWriteFileHandler(str(blocker / "x.log"), on_unwritable=lambda p, e: seen.append(p))
    try:
        for _ in range(2):
            handler.emit(logging.LogRecord("t", logging.ERROR, __file__, 1, "dropped", None, None))
        assert seen == [blocker]
    finally:
        handler.close()


_WRITER = (  # a started service: setup_logging() turns file logging on
    "from autobot_shared.logging_manager import get_logger, setup_logging\n"
    "setup_logging()\n"
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
