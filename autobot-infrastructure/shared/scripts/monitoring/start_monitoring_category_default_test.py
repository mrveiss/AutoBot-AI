# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in
``PerformanceMonitoringManager._handle_performance_alert`` (#14047).

Loaded by explicit path (review of #14047): ``pytest.ini`` sets
``--import-mode=importlib``, which does NOT add a test's own directory to
``sys.path`` (documented at pytest.ini lines 10-13 for the same trap in
``pipeline-scripts``), so a bare ``from start_monitoring import ...`` fails
under real pytest invocation. ``autobot-infrastructure`` is also not in
``pytest.ini`` testpaths, so this file does not run in CI yet (tracking
issue: wiring gap, filed alongside #14047) -- explicit-path loading makes it
individually correct so it starts passing the moment that gap closes, with
no further changes needed here.
"""

import importlib.util
import logging
from pathlib import Path

import pytest

from constants.threshold_constants import CategoryDefaults

_MODULE_PATH = Path(__file__).parent / "start_monitoring.py"


def _load_start_monitoring():
    spec = importlib.util.spec_from_file_location("start_monitoring_under_test", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def PerformanceMonitoringManager():
    return _load_start_monitoring().PerformanceMonitoringManager


@pytest.mark.asyncio
async def test_missing_category_defaults_to_unknown(PerformanceMonitoringManager, caplog):
    manager = PerformanceMonitoringManager()

    with caplog.at_level(logging.WARNING):
        await manager._handle_performance_alert([{"severity": "warning", "message": "high load"}])

    assert f"[WARNING] {CategoryDefaults.UNKNOWN}: high load" in caplog.text


@pytest.mark.asyncio
async def test_explicit_category_overrides_default(PerformanceMonitoringManager, caplog):
    manager = PerformanceMonitoringManager()

    with caplog.at_level(logging.WARNING):
        await manager._handle_performance_alert([{"severity": "warning", "category": "cpu", "message": "high load"}])

    assert "[WARNING] cpu: high load" in caplog.text
