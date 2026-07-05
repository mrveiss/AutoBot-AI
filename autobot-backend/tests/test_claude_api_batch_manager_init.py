# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression test for #10930: GracefulDegradationManager was called with {} instead of
a str/PathLike cache_dir, causing Path({}) to raise TypeError on every startup.
"""

from unittest.mock import patch

import pytest

from utils.claude_api_integration import ClaudeAPIBatchManager, ClaudeAPIConfig


@pytest.mark.parametrize(
    "config",
    [
        None,
        ClaudeAPIConfig(enable_graceful_degradation=True),
        ClaudeAPIConfig(enable_graceful_degradation=False),
    ],
    ids=["default_config", "degradation_on", "degradation_off"],
)
def test_batch_manager_init_does_not_raise(config, tmp_path):
    """ClaudeAPIBatchManager.__init__ must not raise TypeError for any ClaudeAPIConfig.

    Regression: GracefulDegradationManager({}) caused Path(dict) TypeError (#10930).
    The empty-dict argument has been removed; the manager now uses the default cache_dir.
    We patch mkdir so no real directories are created during testing.
    """
    with patch("utils.graceful_degradation.Path.mkdir"):
        manager = ClaudeAPIBatchManager(config)

    # If degradation is enabled, the manager should be a GracefulDegradationManager instance
    if config is None or getattr(config, "enable_graceful_degradation", True):
        from utils.graceful_degradation import GracefulDegradationManager

        assert isinstance(manager.degradation_manager, GracefulDegradationManager)
    else:
        assert manager.degradation_manager is None
