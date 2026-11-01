# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A malformed work item id is a 404 on every work item id route, not a 500 (#20120)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import router as llc_router
from llc.deps import get_session
from user_management.services import TenantContext

pytestmark = pytest.mark.asyncio

USER, COMPANY = uuid.uuid4(), uuid.uuid4()
BAD = "not-a-uuid"


class _Boom(Exception):
    pass


def _client() -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(llc_router, prefix="/api")

    async def _session():
        raise _Boom("a valid id must still reach the session")
        yield

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=COMPANY, user_id=USER, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=True), base_url="http://t")


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", f"/api/llc/work-items/{BAD}", None),
        ("PATCH", f"/api/llc/work-items/{BAD}", {"title": "x"}),
        ("DELETE", f"/api/llc/work-items/{BAD}", None),
        ("POST", f"/api/llc/work-items/{BAD}/claim", {}),
        ("GET", f"/api/llc/work-items/{BAD}/comments", None),
        ("POST", f"/api/llc/work-items/{BAD}/relations", {"target_id": str(uuid.uuid4()), "relation_type": "blocks"}),
        ("DELETE", f"/api/llc/work-items/{BAD}/relations/{uuid.uuid4()}", None),
        ("POST", f"/api/llc/companies/{COMPANY}/labels/work-items/{BAD}/labels", {"label_ids": []}),
    ],
)
async def test_malformed_work_item_id_is_404(method, path, body):
    async with _client() as c:
        resp = await c.request(method, path, json=body)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Work item not found"


async def test_a_well_formed_id_is_not_short_circuited():
    """The guard is on the id alone: a valid id reaches the handler (and so the session)."""
    async with _client() as c:
        with pytest.raises(_Boom):
            await c.get(f"/api/llc/work-items/{uuid.uuid4()}")
