# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""get_logger degrades to console-only when the logs directory is not writable (#19628).

The SLM agent runs under ``ProtectSystem=strict``; its working directory is read-only, so the
default ``./logs`` could not be created and ``get_logger(__name__)`` at import raised
``OSError: [Errno 30] Read-only file system``, crash-looping the unit after an update.
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
from autobot_shared.logging_manager import LoggingManager

_READ_ONLY = OSError(errno.EROFS, "Read-only file system")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("AUTOBOT_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(logging_manager, "_warned_config_keys", set())
    monkeypatch.setattr(LoggingManager, "_initialized", False)
    monkeypatch.setattr(LoggingManager, "_file_logging_disabled", False)
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


def test_a_read_only_logs_dir_yields_a_console_only_logger(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "mkdir", _read_only_logs_mkdir)
    logger = _fresh_logger()
    try:
        assert logger.handlers, "the console handlers are still attached"
        assert not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers)
        assert LoggingManager._file_logging_disabled
        assert "logging to console only" in capsys.readouterr().err
    finally:
        _close(logger)


def test_an_unopenable_log_file_yields_a_console_only_logger(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    LoggingManager._initialized = True  # the directory step passed; only the file open fails

    def _refuse(*args: object, **kwargs: object) -> None:
        raise _READ_ONLY

    monkeypatch.setattr(logging.handlers, "RotatingFileHandler", _refuse)
    logger = _fresh_logger()
    try:
        assert logger.handlers
        assert not LoggingManager._file_logging_disabled, "a per-file failure leaves other log types on"
        assert "logging to console only" in capsys.readouterr().err
    finally:
        _close(logger)


def test_a_writable_logs_dir_still_gets_a_file_handler() -> None:
    logger = _fresh_logger()
    try:
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers)
    finally:
        _close(logger)


def test_rotate_logs_is_a_no_op_when_file_logging_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LoggingManager, "_file_logging_disabled", True)
    monkeypatch.setattr(Path, "mkdir", _read_only_logs_mkdir)
    LoggingManager.rotate_logs()  # must not try to create the backup dir
