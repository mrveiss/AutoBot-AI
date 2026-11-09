# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""get_logger degrades to console-only when the logs directory is not writable (#19628).

The SLM agent runs under ``ProtectSystem=strict``; its working directory is read-only, so the
default ``./logs`` could not be created and ``get_logger(__name__)`` at import raised
``OSError: [Errno 30] Read-only file system``, crash-looping the unit after an update.

Since #20894 nothing is created at ``get_logger``: the file handler creates its directory and file
at the first record, so the degrade happens there -- and still never raises.
"""

import errno
import logging
import logging.handlers
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from autobot_shared import logging_manager
from autobot_shared.log_dir import FirstWriteFileHandler
from autobot_shared.logging_manager import LoggingManager

_READ_ONLY = OSError(errno.EROFS, "Read-only file system")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("AUTOBOT_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(logging_manager, "_warned_config_keys", set())
    monkeypatch.setattr(LoggingManager, "_initialized", False)
    monkeypatch.setattr(LoggingManager, "_file_logging_disabled", False)
    # The degrade is about a service after startup: file logging on (#20894, setup_logging()).
    monkeypatch.setattr(LoggingManager, "_file_logging_enabled", True)
    monkeypatch.setattr(LoggingManager, "_managed", {})
    yield


_real_mkdir = Path.mkdir


def _read_only_logs_mkdir(self: Path, *args: object, **kwargs: object) -> None:
    """Refuse only the configured logs tree; every other directory (config, caches) is created."""
    logs_dir = Path(os.environ["AUTOBOT_LOGS_DIR"])
    if self == logs_dir or logs_dir in self.parents:
        raise _READ_ONLY
    _real_mkdir(self, *args, **kwargs)


def _fresh_logger() -> logging.Logger:
    name = f"logging_manager_19628.{uuid.uuid4().hex}"
    logger = LoggingManager.get_logger(name)
    LoggingManager._loggers.pop(f"backend:{name}", None)
    return logger


def _close(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _file_handlers(logger: logging.Logger) -> list[FirstWriteFileHandler]:
    return [h for h in logger.handlers if isinstance(h, FirstWriteFileHandler)]


def test_get_logger_creates_nothing_on_disk() -> None:
    """Import-time loggers write nothing (#20894): no directory and no file until the first record."""
    logs_dir = Path(os.environ["AUTOBOT_LOGS_DIR"])
    logger = _fresh_logger()
    try:
        assert _file_handlers(logger), "the file handler is attached, deferred"
        assert not logs_dir.exists()
    finally:
        _close(logger)


def test_a_read_only_logs_dir_turns_file_logging_off_at_the_first_write(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "mkdir", _read_only_logs_mkdir)
    logger = _fresh_logger()
    try:
        logger.error("first record")  # must not raise
        logger.error("second record")
        assert LoggingManager._file_logging_disabled
        err = capsys.readouterr().err
        assert err.count("logging to console only") == 1
        assert "first record" in err and "second record" in err, "the console handlers still write"
    finally:
        _close(logger)


def test_two_loggers_on_an_unwritable_path_give_one_stderr_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One disabled marker per path (#20894): a later logger neither rebuilds the handler nor warns again."""
    monkeypatch.setattr(Path, "mkdir", _read_only_logs_mkdir)
    first = _fresh_logger()
    first.error("one")
    second = _fresh_logger()
    try:
        second.error("two")
        assert _file_handlers(first)[0] is _file_handlers(second)[0]
        err = capsys.readouterr().err
        assert err.count("autobot logging: cannot write logs") == 1
    finally:
        _close(first)
        _close(second)


def test_an_unopenable_log_file_turns_off_only_its_own_handler(capsys: pytest.CaptureFixture[str]) -> None:
    logs_dir = Path(os.environ["AUTOBOT_LOGS_DIR"])
    (logs_dir / "backend.log").mkdir(parents=True)  # a directory where the file goes: open() fails
    logger = _fresh_logger()
    try:
        logger.error("record")  # must not raise
        assert not LoggingManager._file_logging_disabled, "a per-file failure leaves other log types on"
        assert "logging to console only" in capsys.readouterr().err
    finally:
        _close(logger)


def test_a_writable_logs_dir_gets_the_file_at_the_first_write() -> None:
    logger = _fresh_logger()
    try:
        logger.error("written at #20894's first write")
        for handler in _file_handlers(logger):
            handler.flush()
        log_file = Path(os.environ["AUTOBOT_LOGS_DIR"]) / "backend.log"
        assert "first write" in log_file.read_text(encoding="utf-8")
    finally:
        _close(logger)


def test_rotate_logs_is_a_no_op_when_file_logging_is_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A log file exists to rotate, so only the early return keeps it in place (#19660)."""
    log_file = tmp_path / "backend.log"
    log_file.write_text("x", encoding="utf-8")
    renamed: list[tuple[object, object]] = []
    monkeypatch.setattr(logging_manager, "_configured_log_file", lambda log_type: str(log_file))
    monkeypatch.setattr(logging_manager.os, "rename", lambda src, dst: renamed.append((src, dst)))
    monkeypatch.setattr(LoggingManager, "_file_logging_disabled", True)
    monkeypatch.setattr(Path, "mkdir", _read_only_logs_mkdir)
    LoggingManager.rotate_logs()
    assert renamed == [], "file logging is off, so there is no backup dir to rotate into"
