# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""get_logger validates every config value it reads (#19288).

Before the fix, ``RotatingFileHandler(log_file, maxBytes=..., backupCount=...)`` received the config
manager's values unchecked, so a harness that mocks config (every value a ``MagicMock``) or a
malformed real config made ``get_logger(__name__)`` raise at import time.
"""

import logging
import logging.handlers
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autobot_shared import logging_manager
from autobot_shared.logging_manager import LoggingManager


class _DictConfig:
    """A config manager answering ``get_nested`` from a flat dict of dotted keys."""

    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def get_nested(self, path: str, default: object = None) -> object:
        return self._values.get(path, default)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("AUTOBOT_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(logging_manager, "_warned_config_keys", set())
    yield


def _fresh_logger(config: object, log_type: str = "backend") -> logging.Logger:
    """Build a logger never cached before, under *config*, and detach it from the cache."""
    name = f"logging_manager_19288.{uuid.uuid4().hex}"
    with patch.object(logging_manager, "_get_config_manager", return_value=config):
        logger = LoggingManager.get_logger(name, log_type)
    LoggingManager._loggers.pop(f"{log_type}:{name}", None)
    return logger


def _file_handler(logger: logging.Logger) -> logging.handlers.RotatingFileHandler:
    handlers = [h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1
    return handlers[0]


def _close(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _assert_defaults(logger: logging.Logger, tmp_path: Path, log_type: str = "backend") -> None:
    handler = _file_handler(logger)
    assert handler.maxBytes == logging_manager._DEFAULT_MAX_BYTES
    assert handler.backupCount == logging_manager._DEFAULT_BACKUP_COUNT
    assert Path(handler.baseFilename) == (tmp_path / "logs" / f"{log_type}.log").resolve()
    assert handler.formatter is not None and handler.formatter._fmt == logging_manager._DEFAULT_FORMAT
    assert logger.level == logging.INFO


def test_get_logger_succeeds_when_every_config_value_is_a_magicmock(tmp_path: Path) -> None:
    """The SLM harness shape: ``config`` is a MagicMock, so every get_nested is one too."""
    logger = _fresh_logger(MagicMock())
    try:
        _assert_defaults(logger, tmp_path)
    finally:
        _close(logger)


@pytest.mark.parametrize(
    "bad",
    [
        {"logging.rotation.max_bytes": "10MB", "logging.rotation.backup_count": True},
        {"logging.rotation.max_bytes": -1, "logging.rotation.backup_count": 2.5},
        {"logging.file_handlers.backend": 42, "logging.format": 7, "logging.log_level": "LOUD"},
        {"logging.format": "%(unclosed", "logging.log_level": 7},
        {"logging.log_level": True},
    ],
)
def test_get_logger_uses_defaults_for_wrong_typed_values(tmp_path: Path, bad: dict[str, object]) -> None:
    logger = _fresh_logger(_DictConfig(bad))
    try:
        _assert_defaults(logger, tmp_path)
    finally:
        _close(logger)


def test_each_bad_key_warns_once_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    config = _DictConfig({"logging.rotation.max_bytes": "big"})
    first, second = _fresh_logger(config), _fresh_logger(config)
    _close(first)
    _close(second)
    err = capsys.readouterr().err
    assert err.count("'logging.rotation.max_bytes'") == 1
    assert "big" not in err, "only the value's type is reported, never the value"


def test_valid_config_still_drives_rotation_path_format_and_level(tmp_path: Path) -> None:
    log_file = tmp_path / "custom" / "llm-channel.log"
    config = _DictConfig(
        {
            "logging.file_handlers.llm": log_file,  # a Path is accepted as well as a str
            "logging.rotation.max_bytes": 2048,
            "logging.rotation.backup_count": 0,
            "logging.format": "%(levelname)s|%(message)s",
            "logging.log_level": "warning",
        }
    )
    logger = _fresh_logger(config, "llm")
    try:
        handler = _file_handler(logger)
        assert (handler.maxBytes, handler.backupCount) == (2048, 0)
        assert Path(handler.baseFilename) == log_file.resolve()
        assert handler.formatter is not None and handler.formatter._fmt == "%(levelname)s|%(message)s"
        assert logger.level == logging.WARNING
    finally:
        _close(logger)


@pytest.mark.parametrize(
    ("configured", "expected"), [(10, logging.DEBUG), (40, logging.ERROR), ("Error", logging.ERROR)]
)
def test_a_known_level_number_or_name_is_used(configured: object, expected: int) -> None:
    logger = _fresh_logger(_DictConfig({"logging.log_level": configured}))
    try:
        assert logger.level == expected
    finally:
        _close(logger)


def test_rotate_logs_ignores_an_unusable_configured_path() -> None:
    with patch.object(logging_manager, "_get_config_manager", return_value=MagicMock()):
        LoggingManager.rotate_logs("backend")
