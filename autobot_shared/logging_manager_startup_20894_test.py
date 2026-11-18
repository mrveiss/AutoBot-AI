# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""File logging starts at service startup, never at import (#20894, maintainer decision 2026-11-09).

Before ``setup_logging()`` a logger has console handlers only, so a module that logs at import
writes no file. ``setup_logging()`` gives every logger made so far, and every later one, the shared
file handler; calling it again changes nothing.
"""

import logging
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from autobot_shared import logging_manager
from autobot_shared.log_dir import FirstWriteFileHandler
from autobot_shared.logging_manager import LoggingManager, setup_logging
from autobot_shared.logging_once import reset_log_once


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("AUTOBOT_LOGS_DIR", str(tmp_path / "logs"))
    reset_log_once()
    monkeypatch.setattr(LoggingManager, "_loggers", {})
    monkeypatch.setattr(LoggingManager, "_managed", {})
    monkeypatch.setattr(LoggingManager, "_file_handlers", {})
    monkeypatch.setattr(LoggingManager, "_file_logging_enabled", False)
    monkeypatch.setattr(LoggingManager, "_file_logging_disabled", False)
    # Defaults only: a backend config imported by an earlier test may name its own log files.
    monkeypatch.setattr(logging_manager, "_get_config_manager", logging_manager._ConfigManagerFallback)
    yield
    for handler in LoggingManager._file_handlers.values():
        handler.close()
    for logger, _ in LoggingManager._managed.values():
        for handler in list(logger.handlers):
            logger.removeHandler(handler)


def _logger() -> logging.Logger:
    """Through the class: autobot-backend/conftest.py stubs the module-level ``get_logger`` (#7766)."""
    return LoggingManager.get_logger(f"startup_20894.{uuid.uuid4().hex}")


def _file_handlers(logger: logging.Logger) -> list[FirstWriteFileHandler]:
    return [h for h in logger.handlers if isinstance(h, FirstWriteFileHandler)]


def _log_text() -> str:
    for handler in LoggingManager._file_handlers.values():
        handler.flush()
    log_file = Path(os.environ["AUTOBOT_LOGS_DIR"]) / "backend.log"
    return log_file.read_text(encoding="utf-8") if log_file.exists() else ""


def test_before_startup_a_logger_writes_no_file() -> None:
    logger = _logger()
    logger.error("logged at import")
    assert not _file_handlers(logger), "a file handler before startup would write at import"
    assert not Path(os.environ["AUTOBOT_LOGS_DIR"]).exists()


def test_startup_gives_an_existing_logger_the_file() -> None:
    early = _logger()
    early.error("before startup")
    setup_logging()
    early.error("after startup")
    text = _log_text()
    assert "after startup" in text
    assert "before startup" not in text, "pre-startup records go to the console, not replayed"


def test_a_logger_made_after_startup_gets_the_file() -> None:
    setup_logging()
    late = _logger()
    late.error("late logger")
    assert len(_file_handlers(late)) == 1
    assert "late logger" in _log_text()


def test_startup_is_idempotent() -> None:
    early = _logger()
    setup_logging()
    setup_logging()
    assert len(_file_handlers(early)) == 1
    assert len(_file_handlers(_logger())) == 1
    assert len(LoggingManager._file_handlers) == 1, "one shared handler per file (#20139)"
