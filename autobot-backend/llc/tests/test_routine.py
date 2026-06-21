# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Routine pytest suite (GH#8229).

Tests required by the issue:
  1.  test_routine_create
  2.  test_routine_list
  3.  test_routine_update
  4.  test_routine_soft_delete
  5.  test_env_overlay_order
  6.  test_secret_ref_resolution
  7.  test_routine_run_record
  8.  test_routine_runs_list
  9.  test_api_create_routine
  10. test_api_trigger

Tests 1-8 use mocked sessions; tests 9-10 use FastAPI TestClient.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from llc.models.enums import RoutineProduces, RoutineStatus
from llc.models.routine import LLCRoutine, LLCRoutineRun
from llc.services.routine_service import RoutineService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPANY_ID = uuid.uuid4()
_AGENT_ID = uuid.uuid4()
_CRON = "*/5 * * * *"


def _routine(
    routine_id: Optional[uuid.UUID] = None,
    status: RoutineStatus = RoutineStatus.ACTIVE,
    cron: str = _CRON,
    env: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    row = MagicMock(spec=LLCRoutine)
    row.id = routine_id or uuid.uuid4()
    row.company_id = _COMPANY_ID
    row.name = "nightly-sync"
    row.cron_schedule = cron
    row.description = None
    row.env = env or {}
    row.status = status
    row.produces = RoutineProduces.NEW_WORK_ITEM
    row.work_item_template = {}
    row.assignee_agent_id = None
    row.recurring_work_item_id = None
    row.last_fired_at = None
    row.created_at = datetime.now(tz=timezone.utc)
    row.updated_at = datetime.now(tz=timezone.utc)
    return row


def _run(routine_id: Optional[uuid.UUID] = None) -> MagicMock:
    row = MagicMock(spec=LLCRoutineRun)
    row.id = uuid.uuid4()
    row.routine_id = routine_id or uuid.uuid4()
    row.status = "queued"
    row.created_at = datetime.now(tz=timezone.utc)
    row.heartbeat_run_id = None
    row.work_item_id = None
    return row


def _session(scalar=None, scalars: Optional[List[Any]] = None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    if scalars is not None:
        result.scalars.return_value.all.return_value = scalars
    session.execute.return_value = result
    session.get.return_value = scalar
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# 1. test_routine_create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_create() -> None:
    session = _session()
    svc = RoutineService()
    routine = await svc.create(
        session,
        _COMPANY_ID,
        "nightly-sync",
        _CRON,
        RoutineProduces.NEW_WORK_ITEM,
        {"title": "Nightly sync task"},
    )
    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert routine.company_id == _COMPANY_ID
    assert routine.cron_schedule == _CRON
    assert routine.status == RoutineStatus.ACTIVE


# ---------------------------------------------------------------------------
# 2. test_routine_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_list() -> None:
    active = _routine(status=RoutineStatus.ACTIVE)
    session = _session(scalars=[active])
    session.execute.return_value.scalars.return_value.all.return_value = [active]

    svc = RoutineService()
    results = await svc.list(session, company_id=_COMPANY_ID, status=RoutineStatus.ACTIVE)

    assert len(results) == 1
    assert results[0].status == RoutineStatus.ACTIVE


# ---------------------------------------------------------------------------
# 3. test_routine_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_update() -> None:
    routine_id = uuid.uuid4()
    row = _routine(routine_id=routine_id)
    session = _session(scalar=row)

    svc = RoutineService()
    updated = await svc.update(session, routine_id, cron_schedule="0 0 * * *")

    assert updated.cron_schedule == "0 0 * * *"
    session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4. test_routine_soft_delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_soft_delete() -> None:
    routine_id = uuid.uuid4()
    row = _routine(routine_id=routine_id)
    session = _session(scalar=row)

    svc = RoutineService()
    await svc.delete(session, routine_id)

    assert row.status == RoutineStatus.ARCHIVED
    session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. test_env_overlay_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_env_overlay_order() -> None:
    """routine_env must override project_env which overrides agent_env.

    System keys (ROUTINE_ID, COMPANY_ID, ROUTINE_NAME) are always injected last.
    """
    routine = _routine(env={"KEY": "routine_val", "ONLY_ROUTINE": "r"})
    session = _session()

    svc = RoutineService()
    merged = await svc.resolve_env(
        session,
        routine,
        agent_env={"KEY": "agent_val", "ONLY_AGENT": "a"},
        project_env={"KEY": "project_val", "ONLY_PROJECT": "p"},
    )

    assert merged["KEY"] == "routine_val"
    assert merged["ONLY_AGENT"] == "a"
    assert merged["ONLY_PROJECT"] == "p"
    assert merged["ONLY_ROUTINE"] == "r"
    # System keys always injected
    assert merged["ROUTINE_ID"] == str(routine.id)
    assert merged["COMPANY_ID"] == str(routine.company_id)
    assert merged["ROUTINE_NAME"] == routine.name


# ---------------------------------------------------------------------------
# 6. test_secret_ref_resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_secret_ref_resolution() -> None:
    """Values matching 'secret:<NAME>' must be resolved via SecretService."""
    routine = _routine(env={"DB_PASS": "secret:db_password"})
    session = _session()

    mock_secret_service = AsyncMock()
    mock_secret_service.get.return_value = "supersecret"

    svc = RoutineService()
    merged = await svc.resolve_env(session, routine, secret_service=mock_secret_service)

    mock_secret_service.get.assert_awaited_once_with(session, str(_COMPANY_ID), "db_password")
    assert merged["DB_PASS"] == "supersecret"


# ---------------------------------------------------------------------------
# 7. test_routine_run_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_run_record() -> None:
    routine_id = uuid.uuid4()
    session = _session()

    svc = RoutineService()
    run = await svc.record_run(session, routine_id, status="queued")

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert run.routine_id == routine_id
    assert run.status == "queued"


# ---------------------------------------------------------------------------
# 8. test_routine_runs_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_runs_list() -> None:
    routine_id = uuid.uuid4()
    runs = [_run(routine_id=routine_id) for _ in range(3)]
    session = _session()
    session.execute.return_value.scalars.return_value.all.return_value = runs

    svc = RoutineService()
    result = await svc.list_runs(session, routine_id, limit=10, offset=0)

    assert len(result) == 3
    assert all(r.routine_id == routine_id for r in result)


# ---------------------------------------------------------------------------
# 9. test_api_create_routine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_routine() -> None:
    from fastapi import FastAPI

    # GH#9995/GH#10140: llc.api.routines imports cleanly now; the old
    # spec_from_file_location + sys.modules.setdefault hack leaked a half-loaded
    # module into the global registry.
    import llc.api.routines as mod

    router = mod.router

    routine_row = _routine()
    mock_svc_create = MagicMock(create=AsyncMock(return_value=routine_row))
    mock_session = _session()
    mock_session.commit = AsyncMock()

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    async def _override_session():
        yield mock_session

    app.dependency_overrides[mod.get_session] = _override_session

    with patch.object(mod, "_service", lambda: mock_svc_create):
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            f"/api/llc/companies/{_COMPANY_ID}/routines",
            json={
                "name": "nightly-sync",
                "cron_schedule": _CRON,
                "produces": "new_work_item",
                "work_item_template": {},
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "nightly-sync"


# ---------------------------------------------------------------------------
# 10. test_api_trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_trigger() -> None:
    from fastapi import FastAPI

    import llc.api.routines as mod

    router = mod.router

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    routine_row = _routine()
    run_row = _run(routine_id=routine_row.id)
    mock_svc = MagicMock()
    mock_svc.get = AsyncMock(return_value=routine_row)
    mock_svc.record_run = AsyncMock(return_value=run_row)
    mock_session = _session()
    mock_session.commit = AsyncMock()

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    async def _override_session():
        yield mock_session

    app.dependency_overrides[mod.get_session] = _override_session

    with patch.object(mod, "_service", lambda: mock_svc):
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(f"/api/llc/routines/{routine_row.id}/trigger")

    # The trigger endpoint enqueues asynchronously → 202 Accepted.
    assert resp.status_code == 202
    data = resp.json()
    assert data["routine_id"] == str(routine_row.id)
    assert "message" in data


# ---------------------------------------------------------------------------
# Async session context helper for TestClient (sync → async bridge)
# ---------------------------------------------------------------------------


class _async_session_ctx:
    """Minimal async context manager that yields a mock session for DI override."""

    def __init__(self, _unused: Any = None) -> None:
        self._session = _session()
        self._session.commit = AsyncMock()

    def __call__(self) -> "_async_session_ctx":
        return self

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass
