# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #12243.

``GET /api/advanced-control/system/status`` and ``/system/health`` previously
hardcoded ``status: "healthy"`` regardless of the real resource load or
capability state they report. The status must now be *derived*:

- ``system/status`` grades the reported cpu/memory/disk usage against the
  canonical thresholds (:data:`metrics.system_monitor.RESOURCE_THRESHOLDS`) and
  degrades when desktop streaming (the panel's core capability) is unavailable.
- ``system/health`` reports ``degraded`` when desktop streaming is unavailable.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _streaming_mock(vnc_available=True, novnc_available=True):
    streaming = MagicMock()
    streaming.vnc_manager.vnc_available = vnc_available
    streaming.vnc_manager.novnc_available = novnc_available
    streaming.vnc_manager.active_sessions = []
    streaming.vnc_manager.list_active_sessions.return_value = []
    streaming.get_system_capabilities.return_value = {}
    return streaming


def _takeover_mock():
    takeover = MagicMock()
    takeover.get_pending_requests = AsyncMock(return_value=[])
    takeover.get_active_sessions = AsyncMock(return_value=[])
    takeover._paused_count = AsyncMock(return_value=0)
    return takeover


def _patch_resources(cpu, mem, disk):
    """Force psutil resource sampling used by get_system_status to fixed values."""
    return (
        patch("psutil.cpu_percent", return_value=cpu),
        patch("psutil.virtual_memory", return_value=MagicMock(percent=mem)),
        patch("psutil.disk_usage", return_value=MagicMock(percent=disk)),
        patch("psutil.pids", return_value=[]),
        patch("psutil.boot_time", return_value=1_700_000_000.0),
    )


async def _call_system_status(cpu, mem, disk, vnc_available=True):
    from api.advanced_control import get_system_status

    streaming = _streaming_mock(vnc_available=vnc_available)
    takeover = _takeover_mock()
    cpu_p, vmem_p, disk_p, pids_p, boot_p = _patch_resources(cpu, mem, disk)
    with (
        cpu_p,
        vmem_p,
        disk_p,
        pids_p,
        boot_p,
        patch("api.advanced_control.get_desktop_streaming", return_value=streaming),
        patch("api.advanced_control.get_takeover_manager", return_value=takeover),
    ):
        resp = await get_system_status(admin_check=True)
    return resp.system_status


@pytest.mark.asyncio
async def test_system_status_healthy_when_all_nominal():
    status = await _call_system_status(cpu=5, mem=10, disk=15, vnc_available=True)
    assert status["status"] == "healthy"
    assert status["resource_alerts"] == []


@pytest.mark.asyncio
async def test_system_status_unhealthy_when_resource_over_threshold():
    # CPU 99% is over the 80% critical threshold -> unhealthy (NOT hardcoded healthy).
    status = await _call_system_status(cpu=99, mem=10, disk=15, vnc_available=True)
    assert status["status"] == "unhealthy"
    assert any("cpu_percent" in alert for alert in status["resource_alerts"])


@pytest.mark.asyncio
async def test_system_status_degraded_when_resource_approaching_threshold():
    # Memory 70% is above 85% * 0.8 == 68% warning band -> degraded.
    status = await _call_system_status(cpu=5, mem=70, disk=15, vnc_available=True)
    assert status["status"] == "degraded"


@pytest.mark.asyncio
async def test_system_status_degraded_when_streaming_unavailable():
    # Resources nominal but the core capability is down -> degraded, not healthy.
    status = await _call_system_status(cpu=5, mem=10, disk=15, vnc_available=False)
    assert status["status"] == "degraded"


@pytest.mark.asyncio
async def test_system_health_healthy_when_streaming_available():
    from api.advanced_control import get_system_health

    streaming = _streaming_mock(vnc_available=True)
    takeover = _takeover_mock()
    with (
        patch("api.advanced_control.get_desktop_streaming", return_value=streaming),
        patch("api.advanced_control.get_takeover_manager", return_value=takeover),
    ):
        health = await get_system_health(admin_check=True)
    assert health["status"] == "healthy"


@pytest.mark.asyncio
async def test_system_health_degraded_when_streaming_unavailable():
    from api.advanced_control import get_system_health

    streaming = _streaming_mock(vnc_available=False)
    takeover = _takeover_mock()
    with (
        patch("api.advanced_control.get_desktop_streaming", return_value=streaming),
        patch("api.advanced_control.get_takeover_manager", return_value=takeover),
    ):
        health = await get_system_health(admin_check=True)
    assert health["status"] == "degraded"
    assert health["desktop_streaming_available"] is False
