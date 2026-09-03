# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests that the configured log level actually reaches LoggingManager (#15575).

Prior to this fix, ``LoggingManager.get_logger`` read
``_get_config_manager().get("logging.level", "INFO")`` — a key nothing in the
config tree ever published (the schema in ``config/defaults.py``,
``config.yaml``, the ``AUTOBOT_LOG_LEVEL`` env-var mapping, and
``config/validation.py`` all use ``logging.log_level``). The ``.get(key,
default)`` fallback fired on every call, so the logger always ran at INFO
regardless of what was configured (setting ``log_level: DEBUG`` produced no
error and no debug output).

These tests do NOT assert that ``.get()`` was called with the right key --
that would pass against a logger that read the value correctly and then
ignored it. They assert the actual behavioural consequence: whether a DEBUG
record is captured, driven by what the config manager returns for
``logging.log_level``.
"""

import logging

from autobot_shared import logging_manager


class _FakeConfigManager:
    """Stand-in for ``config_manager`` that answers only ``logging.log_level``.

    Every other key falls through to the caller's own default, matching the
    real ``ConfigManager.get(key, default)`` contract for unrelated keys.
    """

    def __init__(self, log_level: str) -> None:
        self._log_level = log_level

    def get(self, key: str, default=None):  # noqa: ANN001, ANN201
        if key == "logging.log_level":
            return self._log_level
        return default


def test_debug_configured_level_reaches_a_debug_record(monkeypatch, capsys):
    """Config saying DEBUG must make a debug record actually reach output."""
    monkeypatch.setattr(logging_manager, "_get_config_manager", lambda: _FakeConfigManager("DEBUG"))

    logger = logging_manager.LoggingManager.get_logger("logging_manager_test.debug_configured_15575", "debug")
    logger.propagate = False

    logger.debug("debug-record-15575-present")

    captured = capsys.readouterr()
    assert "debug-record-15575-present" in captured.out
    assert logger.level == logging.DEBUG


def test_info_configured_level_suppresses_a_debug_record(monkeypatch, capsys):
    """Contrast case: config saying INFO must NOT let a debug record through.

    Without this, a logger that always ran at DEBUG (regardless of config)
    would also pass the first test — this pins the other side of the
    behaviour.
    """
    monkeypatch.setattr(logging_manager, "_get_config_manager", lambda: _FakeConfigManager("INFO"))

    logger = logging_manager.LoggingManager.get_logger("logging_manager_test.info_configured_15575", "debug")
    logger.propagate = False

    logger.debug("debug-record-15575-absent")

    captured = capsys.readouterr()
    assert "debug-record-15575-absent" not in captured.out
    assert logger.level == logging.INFO
