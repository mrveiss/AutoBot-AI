# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the admin break-glass resource-grant repair API (#15779).

Covers:
- POST /admin/resource-grants/repair — admin-only, emits an audit record
- Non-admin access is rejected (401/403)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.admin_resource_grants import router
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user


def _make_app(db_session) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: db_session
    return app


@pytest.fixture
def db_session():
    """A ready-to-use AsyncSession over a fresh in-memory sqlite DB.

    Built with one `asyncio.run()` (table creation + session-maker binding
    share the engine's connection pool), then handed to a synchronous
    TestClient test: the route handler awaits it later inside TestClient's
    own request-handling loop.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from models.resource_grant import ResourceGrant

    async def _build():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(ResourceGrant.__table__.create)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        return engine, maker()

    engine, session = asyncio.run(_build())
    yield session

    async def _teardown():
        await session.close()
        await engine.dispose()

    asyncio.run(_teardown())


def test_repair_grant_admin_succeeds_and_audits(db_session):
    admin = {"username": "admin", "role": "admin", "user_id": "admin-1"}
    mock_auth = MagicMock()
    mock_auth.get_user_from_request.return_value = admin

    app = _make_app(db_session)
    app.dependency_overrides[get_current_user] = lambda: admin

    with (
        patch("auth_rbac.get_auth_middleware", return_value=mock_auth),
        patch("services.resource_visibility.audit_log", new=AsyncMock(return_value=True)) as audit,
    ):
        with TestClient(app) as client:
            resp = client.post(
                "/admin/resource-grants/repair",
                json={
                    "resource_type": "knowledge_fact",
                    "resource_id": "orphan-1",
                    "grantee_type": "user",
                    "grantee_id": "u1",
                    "permission": "use",
                },
            )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["resource_type"] == "knowledge_fact"
    assert data["grantee_id"] == "u1"
    audit.assert_awaited_once()
    assert audit.call_args.kwargs["operation"] == "resource.repair_grant"
    assert audit.call_args.kwargs["user_id"] == "admin-1"


def test_repair_grant_non_admin_rejected(db_session):
    non_admin = {"username": "u2", "role": "user", "user_id": "u2"}
    mock_auth = MagicMock()
    mock_auth.get_user_from_request.return_value = non_admin

    app = _make_app(db_session)
    app.dependency_overrides[get_current_user] = lambda: non_admin

    with patch("auth_rbac.get_auth_middleware", return_value=mock_auth):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/admin/resource-grants/repair",
                json={
                    "resource_type": "knowledge_fact",
                    "resource_id": "orphan-1",
                    "grantee_type": "user",
                    "grantee_id": "u1",
                },
            )
    assert resp.status_code in (401, 403)


def test_repair_grant_rejects_invalid_grantee_type(db_session):
    admin = {"username": "admin", "role": "admin", "user_id": "admin-1"}
    mock_auth = MagicMock()
    mock_auth.get_user_from_request.return_value = admin

    app = _make_app(db_session)
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch("auth_rbac.get_auth_middleware", return_value=mock_auth):
        with TestClient(app) as client:
            resp = client.post(
                "/admin/resource-grants/repair",
                json={
                    "resource_type": "knowledge_fact",
                    "resource_id": "orphan-1",
                    "grantee_type": "not-a-real-type",
                    "grantee_id": "u1",
                },
            )
    assert resp.status_code == 422
