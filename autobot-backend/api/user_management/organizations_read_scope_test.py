# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Organization read routes serve the caller's own organisation, or a platform admin (#15738).

The real tenant-context chain runs; only the identity, the database session
and the organization service (which, like the real one, does not filter by
caller) are replaced.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import (
    get_current_user,
    get_db_session,
    get_organization_service,
)
from api.user_management.router import router as user_management_router

_CALLER = uuid.UUID("00000000-0000-0000-0000-000000000001")
_OWN_ORG = uuid.UUID("00000000-0000-0000-0000-000000000005")
_OTHER_ORG = uuid.UUID("00000000-0000-0000-0000-000000000006")

_MEMBER = {"role": "user", "user_id": str(_CALLER), "org_id": str(_OWN_ORG)}
_ADMIN = {"role": "admin", "is_platform_admin": True, "user_id": str(_CALLER)}


async def _no_session():
    yield object()


def _org(org_id: uuid.UUID) -> MagicMock:
    org = MagicMock()
    org.id = org_id
    org.name = "Org"
    org.slug = f"slug-{org_id.int}"
    org.description = None
    org.settings = {}
    org.max_users = 5
    org.is_active = True
    org.created_at = None
    org.updated_at = None
    return org


def _service() -> MagicMock:
    service = MagicMock()
    service.get_organization = AsyncMock(side_effect=lambda org_id: _org(org_id))
    service.get_organization_by_slug = AsyncMock(
        side_effect=lambda slug: _org(_OWN_ORG if slug == "own" else _OTHER_ORG)
    )
    service.get_organization_stats = AsyncMock(
        side_effect=lambda org_id: {
            "organization_id": str(org_id),
            "name": "Org",
            "slug": "org",
            "users": {},
            "teams": {},
            "is_active": True,
            "created_at": None,
        }
    )
    return service


def _client(current_user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(user_management_router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db_session] = _no_session
    service = _service()
    app.dependency_overrides[get_organization_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def _paths(org_id: uuid.UUID, slug: str) -> dict[str, str]:
    base = "/user-management/organizations"
    return {"by_id": f"{base}/{org_id}", "stats": f"{base}/{org_id}/stats", "by_slug": f"{base}/slug/{slug}"}


@pytest.mark.parametrize("route", ["by_id", "stats", "by_slug"])
def test_own_organization_is_allowed(route):
    response = _client(_MEMBER).get(_paths(_OWN_ORG, "own")[route])
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(("route", "refusal"), [("by_id", 403), ("stats", 403), ("by_slug", 404)])
def test_another_organization_is_refused(route, refusal):
    response = _client(_MEMBER).get(_paths(_OTHER_ORG, "other")[route])
    assert response.status_code == refusal, response.text


@pytest.mark.parametrize("route", ["by_id", "stats", "by_slug"])
def test_platform_admin_is_allowed(route):
    response = _client(_ADMIN).get(_paths(_OTHER_ORG, "other")[route])
    assert response.status_code == 200, response.text
