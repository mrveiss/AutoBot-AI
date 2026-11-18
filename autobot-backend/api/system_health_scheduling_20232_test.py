# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``GET /api/health`` says whether Company OS scheduling runs, without touching ``status`` (#20232)."""

import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api import system
from api import system_startup_state as state
from api.system_health import SystemHealth


def _healthy_aggregate():
    return SystemHealth(status="ok", components=[], timestamp="2026-10-31T00:00:00+00:00")


async def _health(app_state: dict | None = None):
    lifespan = SimpleNamespace(app_state=app_state or {})
    with (
        patch.dict(sys.modules, {"initialization.lifespan": lifespan}),
        patch("api.system_health.collect_system_health", AsyncMock(return_value=_healthy_aggregate())),
        patch.object(state, "STARTUP_ERROR_FILE", SimpleNamespace(exists=lambda: False)),
    ):
        return await system.get_system_health(request=None)


def _error_file(tmp_path, content: str):
    path = tmp_path / "startup-error.json"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_scheduler_not_running_is_a_distinct_field_and_status_stays_ok():
    with patch("llc.health.probe.heartbeat_scheduler_running", return_value=False):
        body = await _health()
    assert body["company_os_scheduling"] == {"heartbeat_scheduler_running": False}
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_scheduler_running_reads_true():
    with patch("llc.health.probe.heartbeat_scheduler_running", return_value=True):
        body = await _health()
    assert body["company_os_scheduling"] == {"heartbeat_scheduler_running": True}


@pytest.mark.asyncio
async def test_unreadable_scheduler_state_is_none_logged_and_does_not_fail_health(caplog):
    with (
        patch("llc.health.probe.heartbeat_scheduler_running", side_effect=RuntimeError("boom")),
        caplog.at_level(logging.WARNING),
    ):
        body = await _health()
    assert body["company_os_scheduling"] == {"heartbeat_scheduler_running": None}
    assert body["status"] == "ok"
    assert "RuntimeError" in caplog.text


def test_the_field_reads_the_probe_source():
    from llc.health import probe

    scheduler = SimpleNamespace(is_running=True)
    with patch("llc.scheduler.heartbeat_scheduler.get_heartbeat_scheduler", return_value=scheduler):
        assert probe.heartbeat_scheduler_running() is True
        scheduler.is_running = False
        assert probe.heartbeat_scheduler_running() is False


@pytest.mark.asyncio
async def test_startup_error_in_memory_is_type_name_only():
    result = await state.resolve_startup_error({"startup_error": "RuntimeError: the message must not be reported"})
    assert result == "RuntimeError"


@pytest.mark.asyncio
async def test_startup_error_falls_back_to_the_disk_file(tmp_path):
    path = _error_file(tmp_path, '{"error_type": "ConnectionRefusedError"}')
    with patch.object(state, "STARTUP_ERROR_FILE", path):
        assert await state.resolve_startup_error({}) == "ConnectionRefusedError"


@pytest.mark.asyncio
async def test_corrupt_startup_error_file_is_logged_not_raised(tmp_path, caplog):
    path = _error_file(tmp_path, "{not json")
    with patch.object(state, "STARTUP_ERROR_FILE", path), caplog.at_level(logging.WARNING):
        assert await state.resolve_startup_error({}) is None
    assert "unreadable" in caplog.text
