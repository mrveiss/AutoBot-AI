# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A missing company answers 404 "Not found", never "Internal server error" (#21943)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import companies
from llc.services.company import CompanyNotFoundError
from user_management.services import TenantContext

_USER_ID = uuid.uuid4()


def _app(svc: MagicMock, org_id: uuid.UUID) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID), "user_id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=org_id, user_id=_USER_ID, is_platform_admin=False
    )
    return app


@pytest.mark.asyncio
async def test_get_missing_company_is_404_not_found() -> None:
    missing = uuid.uuid4()
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.get = AsyncMock(side_effect=CompanyNotFoundError(str(missing)))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(svc, missing)), base_url="http://test"
    ) as client:
        resp = await client.get(f"/api/llc/companies/{missing}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Not found"
