# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`POST /routines/{id}/trigger` answers 202 only after the schedule write succeeded (#22003)."""

from __future__ import annotations

import ast
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import routines as routines_api
from llc.deps import get_session
from llc.models.enums import RoutineStatus
from llc.scheduler.routine_scheduler import _SCHEDULE_KEY
from testkit.fake_async_session import FakeAsyncSession
from user_management.services import TenantContext

_ORG, _USER, _ROUTINE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class _Schedule:
    """The one Redis command the trigger issues, recording the sorted set it writes."""

    def __init__(self, error: Exception | None = None) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self._error = error

    async def zadd(self, key: str, mapping: dict[str, float], nx: bool = False) -> int:
        if self._error is not None:
            raise self._error
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(routines_api.router)

    async def _session():  # noqa: ANN202
        yield FakeAsyncSession()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=_USER, is_platform_admin=False
    )
    routine = SimpleNamespace(id=_ROUTINE, company_id=_ORG, status=RoutineStatus.ACTIVE)
    with patch.object(routines_api, "_service", lambda: MagicMock(get=AsyncMock(return_value=routine))):
        yield TestClient(app)


def _trigger(client: TestClient, redis: object, log: MagicMock | None = None):  # noqa: ANN202
    with patch.object(routines_api, "get_async_redis_client", AsyncMock(return_value=redis)):
        if log is None:
            return client.post(f"/routines/{_ROUTINE}/trigger")
        with patch.object(routines_api, "logger", log):
            return client.post(f"/routines/{_ROUTINE}/trigger")


def test_a_failing_zadd_answers_503_and_is_logged(client: TestClient) -> None:
    log = MagicMock()
    resp = _trigger(client, _Schedule(error=ConnectionError("redis down")), log)
    assert resp.status_code == 503, resp.text
    log.error.assert_called_once()
    assert "ConnectionError" in log.error.call_args.args[2]


def test_a_missing_redis_client_answers_503_and_is_logged(client: TestClient) -> None:
    log = MagicMock()
    resp = _trigger(client, None, log)
    assert resp.status_code == 503, resp.text
    log.error.assert_called_once()


def test_a_working_client_answers_202_and_the_routine_is_on_the_schedule(client: TestClient) -> None:
    redis, before = _Schedule(), time.time()
    resp = _trigger(client, redis)
    assert resp.status_code == 202, resp.text
    assert resp.json()["routine_id"] == str(_ROUTINE)
    assert redis.zsets[_SCHEDULE_KEY][f"routine:{_ROUTINE}"] >= before


def test_trigger_routine_has_no_swallowing_except() -> None:
    tree = ast.parse(Path(routines_api.__file__).read_text(encoding="utf-8"))
    names = {"trigger_routine", "_schedule_now"}
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    assert {f.name for f in fns} == names
    handlers = [h for f in fns for h in ast.walk(f) if isinstance(h, ast.ExceptHandler)]
    assert handlers, "the scan must see the except it is checking"
    assert not [h for h in handlers if all(isinstance(b, ast.Pass) for b in h.body)]
