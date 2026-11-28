# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pause, resume and terminate take a non-UUID agent slug (#19587).

``ceo-<company uuid>`` is not a UUID; a ``uuid.UUID`` path type answered 422
before the handler ran. Each route is driven with that slug and the assertion is
that the handler ran and handed the slug, unchanged, to the controls service.

The service is stubbed, not run: its raw-SQL control writes bind ``company_id``
as a dashed string and the SQLite harness stores UUIDs undashed, so the real
service finds no row there for any agent. ``test_controls`` covers the SQL.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from llc.services.company_ceo import default_ceo_slug
from llc.tests import test_llc_org_chart as _org_chart_harness

# The SQLite harness fixtures, re-exported so pytest finds them in this module.
engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user
    from llc.api import controls
    from llc.deps import get_session

    app = FastAPI()
    app.include_router(controls.router, prefix="/api/llc")

    async def _session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _slug() -> tuple[uuid.UUID, str]:
    company_id = uuid.uuid4()
    return company_id, default_ceo_slug(company_id)


async def _post(client, company_id, slug: str, action: str, svc, body=None):  # noqa: ANN001, ANN202
    from llc.api import controls

    url = f"/api/llc/companies/{company_id}/controls/agents/{slug}/{action}"
    with (
        patch.object(controls, "require_board_role", new=AsyncMock(return_value="board-user")),
        patch.object(controls, "_controls_svc", return_value=svc),
    ):
        return await client.post(url, json=body or {})


def _svc() -> MagicMock:
    svc = MagicMock()
    for name in ("pause_agent", "resume_agent", "terminate_agent"):
        setattr(svc, name, AsyncMock(return_value={"agent_id": "stub"}))
    return svc


@pytest.mark.asyncio
async def test_pause_reaches_the_handler_for_a_ceo_slug(session_factory, client):  # noqa: ANN001
    company_id, slug = _slug()
    svc = _svc()

    resp = await _post(client, company_id, slug, "pause", svc, {"reason": "board"})

    assert resp.status_code == 200, resp.text
    svc.pause_agent.assert_awaited_once()
    assert svc.pause_agent.await_args.args[1:3] == (str(company_id), slug)


@pytest.mark.asyncio
async def test_resume_reaches_the_handler_for_a_ceo_slug(session_factory, client):  # noqa: ANN001
    company_id, slug = _slug()
    svc = _svc()

    resp = await _post(client, company_id, slug, "resume", svc)

    assert resp.status_code == 200, resp.text
    svc.resume_agent.assert_awaited_once()
    assert svc.resume_agent.await_args.args[1:3] == (str(company_id), slug)


@pytest.mark.asyncio
async def test_terminate_reaches_the_handler_for_a_ceo_slug(session_factory, client):  # noqa: ANN001
    company_id, slug = _slug()
    svc = _svc()

    resp = await _post(client, company_id, slug, "terminate", svc, {"reason": "board"})

    assert resp.status_code == 200, resp.text
    svc.terminate_agent.assert_awaited_once()
    assert svc.terminate_agent.await_args.args[1:3] == (str(company_id), slug)


@pytest.mark.asyncio
async def test_a_service_miss_is_the_handlers_404_not_a_422(session_factory, client):  # noqa: ANN001
    from llc.services.controls_service import AgentNotFoundError

    company_id, slug = _slug()
    for action in ("pause", "resume", "terminate"):
        svc = _svc()
        getattr(svc, f"{action}_agent").side_effect = AgentNotFoundError(slug)
        resp = await _post(client, company_id, slug, action, svc)
        assert resp.status_code == 404, (action, resp.status_code, resp.text)
