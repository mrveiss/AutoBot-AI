# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #12208.

``request_takeover`` used two hand-maintained dicts to map request strings to
``TakeoverTrigger`` / ``TaskPriority`` enums. Each dict was a manual mirror of
its enum, so any member the dict forgot was silently unusable (a valid trigger
rejected with 400; a valid priority defaulted to HIGH). The endpoint now uses
direct ``Enum[name]`` lookups so the enum is the single source of truth.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.advanced_control import request_takeover
from api.schemas_system import TakeoverRequest
from memory import TaskPriority
from takeover_manager import TakeoverTrigger


def _req(trigger: str, priority: str = "HIGH") -> TakeoverRequest:
    return TakeoverRequest(trigger=trigger, reason="r", priority=priority, affected_tasks=[])


async def _call(req: TakeoverRequest):
    manager = MagicMock()
    manager.request_takeover = AsyncMock(return_value="req-123")
    with patch("api.advanced_control.get_takeover_manager", return_value=manager):
        result = await request_takeover(req, admin_check=True)
    return result, manager.request_takeover


@pytest.mark.asyncio
async def test_valid_trigger_and_priority_map_to_enums():
    result, called = await _call(_req("MANUAL_REQUEST", "CRITICAL"))
    assert result["success"] is True
    kwargs = called.call_args.kwargs
    assert kwargs["trigger"] is TakeoverTrigger.MANUAL_REQUEST
    assert kwargs["priority"] is TaskPriority.CRITICAL


@pytest.mark.asyncio
async def test_trigger_lookup_is_case_insensitive():
    _result, called = await _call(_req("security_concern", "low"))
    assert called.call_args.kwargs["trigger"] is TakeoverTrigger.SECURITY_CONCERN
    assert called.call_args.kwargs["priority"] is TaskPriority.LOW


@pytest.mark.asyncio
async def test_invalid_trigger_raises_400():
    with pytest.raises(HTTPException) as exc:
        await _call(_req("NOT_A_TRIGGER"))
    assert exc.value.status_code == 400
    assert "NOT_A_TRIGGER" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_unknown_priority_defaults_to_high():
    _result, called = await _call(_req("MANUAL_REQUEST", "BOGUS"))
    assert called.call_args.kwargs["priority"] is TaskPriority.HIGH


@pytest.mark.asyncio
async def test_priority_member_absent_from_old_map_now_resolves():
    # NORMAL is a real TaskPriority member the old hand-map omitted -> it used to
    # silently default to HIGH; the direct lookup now resolves it correctly.
    _result, called = await _call(_req("MANUAL_REQUEST", "NORMAL"))
    assert called.call_args.kwargs["priority"] is TaskPriority.NORMAL


@pytest.mark.asyncio
async def test_every_trigger_member_is_accepted():
    # The whole point of #12208: the enum is the source of truth, so *every*
    # member resolves without a hand-maintained map to keep in sync.
    for member in TakeoverTrigger:
        _result, called = await _call(_req(member.name))
        assert called.call_args.kwargs["trigger"] is member
