# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-level wiring for ``POST /system/emergency-stop`` (#16843).

Branch coverage for what the report actually distinguishes lives in
``services/emergency_stop_test.py`` -- this only asserts the route still
delegates to that service and returns what it reports, since the route
body itself no longer has any branching logic of its own.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.advanced_control import emergency_system_stop
from api.schemas_emergency_stop import EmergencyStopReportResponse

pytestmark = pytest.mark.asyncio


async def test_route_returns_what_the_service_reports():
    report = {
        "success": True,
        "message": "Emergency stop activated: paused 1 active task(s)",
        "takeover_request_id": "takeover-123",
        "tasks_paused": ["task-1"],
        "durable": True,
    }
    with patch("api.advanced_control.execute_emergency_stop", AsyncMock(return_value=report)) as mocked:
        result = await emergency_system_stop(admin_check=True)

    mocked.assert_awaited_once_with()
    assert result == report


async def test_response_model_accepts_all_three_reported_states():
    for tasks_paused, durable in (([], True), (["task-1"], True), (["task-1"], False)):
        EmergencyStopReportResponse(
            success=True,
            message="m",
            takeover_request_id="r",
            tasks_paused=tasks_paused,
            durable=durable,
        )
