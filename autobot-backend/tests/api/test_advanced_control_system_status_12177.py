# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #12177.

``GET /api/advanced-control/system/status`` previously set both ``timestamp``
and ``uptime_seconds`` to ``psutil.boot_time()`` — an absolute boot epoch
(~1.7e9), so frontends rendering ``uptime_seconds`` as a duration showed a
meaningless ~1.7 billion. ``timestamp`` must be the snapshot time (now) and
``uptime_seconds`` a real duration (now - boot).
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import psutil
import pytest


@pytest.mark.asyncio
async def test_system_status_uptime_is_duration_not_boot_epoch():
    from api.advanced_control import get_system_status

    streaming = MagicMock()
    streaming.vnc_manager.list_active_sessions.return_value = []
    streaming.get_system_capabilities.return_value = {}

    takeover = MagicMock()
    takeover.get_pending_requests = AsyncMock(return_value=[])
    takeover.get_active_sessions = AsyncMock(return_value=[])

    with (
        patch("api.advanced_control.get_desktop_streaming", return_value=streaming),
        patch("api.advanced_control.get_takeover_manager", return_value=takeover),
    ):
        resp = await get_system_status(admin_check=True)

    status = resp.system_status
    boot = psutil.boot_time()
    now = time.time()

    # uptime_seconds is a duration (now - boot), NOT the absolute boot epoch (#12177).
    assert 0 <= status["uptime_seconds"] < boot
    assert status["uptime_seconds"] == pytest.approx(now - boot, abs=5)

    # timestamp is the snapshot time (now), NOT the boot epoch.
    assert status["timestamp"] == pytest.approx(now, abs=5)
    assert status["timestamp"] > status["uptime_seconds"]
