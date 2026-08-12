# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in
``PerformanceMonitoringManager._handle_performance_alert`` (#14047)."""

import logging

import pytest

from constants.threshold_constants import CategoryDefaults
from start_monitoring import PerformanceMonitoringManager


@pytest.mark.asyncio
async def test_missing_category_defaults_to_unknown(caplog):
    manager = PerformanceMonitoringManager()

    with caplog.at_level(logging.WARNING):
        await manager._handle_performance_alert([{"severity": "warning", "message": "high load"}])

    assert f"[WARNING] {CategoryDefaults.UNKNOWN}: high load" in caplog.text


@pytest.mark.asyncio
async def test_explicit_category_overrides_default(caplog):
    manager = PerformanceMonitoringManager()

    with caplog.at_level(logging.WARNING):
        await manager._handle_performance_alert(
            [{"severity": "warning", "category": "cpu", "message": "high load"}]
        )

    assert "[WARNING] cpu: high load" in caplog.text
