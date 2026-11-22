# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Redis service routes answer 503 with the reason when the SLM cannot be asked (#22030, #16346)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import redis_service
from services.redis_service_manager import RedisNodeUnresolvedError, RedisSlmAccessError

ROUTES = [
    (redis_service.start_redis_service, "start_service", {"operator": {"username": "u"}}),
    (redis_service.stop_redis_service, "stop_service", {"admin_check": True, "current_user": {"username": "u"}}),
    (redis_service.restart_redis_service, "restart_service", {"operator": {"username": "u"}}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RedisSlmAccessError("refused"), RedisNodeUnresolvedError("no node")])
@pytest.mark.parametrize("route,method,extra", ROUTES)
async def test_an_operation_route_answers_503_with_the_reason(route, method, extra, error):
    manager = MagicMock()
    setattr(manager, method, AsyncMock(side_effect=error))
    with pytest.raises(HTTPException) as caught:
        await route(request=MagicMock(), manager=manager, **extra)
    assert caught.value.status_code == 503
    assert caught.value.detail == str(error)


@pytest.mark.asyncio
async def test_the_status_route_answers_503_with_the_reason():
    manager = MagicMock()
    manager.get_service_status = AsyncMock(side_effect=RedisSlmAccessError("refused"))
    with pytest.raises(HTTPException) as caught:
        await redis_service.get_redis_status(manager=manager, current_user={"username": "u"})
    assert (caught.value.status_code, caught.value.detail) == (503, "refused")
