# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``LoggingManager.set_level`` reaches loggers made before and after the call (#17530)."""

import logging

from autobot_shared import logging_manager


class _FakeConfigManager:
    def get_nested(self, path, default=None):  # noqa: ANN001, ANN201
        return "INFO" if path == "logging.log_level" else default


def test_set_level_covers_existing_and_future_loggers(monkeypatch):
    monkeypatch.setattr(logging_manager, "_get_config_manager", lambda: _FakeConfigManager())
    manager = logging_manager.LoggingManager
    before = manager.get_logger("logging_manager_test.set_level_before_17530", "debug")
    try:
        manager.set_level(logging.DEBUG)
        after = manager.get_logger("logging_manager_test.set_level_after_17530", "debug")
        assert before.level == after.level == logging.DEBUG
    finally:
        manager._level_override = None
