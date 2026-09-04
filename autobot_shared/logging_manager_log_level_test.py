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
    """Stand-in holding a NESTED config, with both accessors as the real one has them.

    The first version of this fake answered ``get("logging.log_level")`` directly.
    That is not a contract ``ConfigManager`` has: its ``get`` is a FLAT top-level
    lookup and only ``get_nested`` walks a dotted path. So the fake agreed with
    code that could never work against the real object, and #15575 shipped a fix
    that changed the key name while the read still fell through (#15586).

    Holding a nested dict and implementing both methods with the real semantics
    is what makes this test able to fail: a caller using ``get`` on a dotted key
    now gets the fallback here exactly as it would in production.
    """

    def __init__(self, log_level: str) -> None:
        self._config = {"logging": {"log_level": log_level}}

    def get(self, key: str, default=None):  # noqa: ANN001, ANN201
        """Flat top-level lookup — a dotted key MISSES, as in ConfigManager."""
        return self._config.get(key, default)

    def get_nested(self, path: str, default=None):  # noqa: ANN001, ANN201
        """Dotted-path walk, as in ConfigManager.get_nested."""
        node = self._config
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


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
