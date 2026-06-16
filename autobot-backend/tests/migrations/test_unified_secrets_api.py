# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HTTP tests for the /api/v2/secrets router (#10088 / Task 2.4 part 2).

Mounts just the router in a throwaway FastAPI app (no whole-app startup) with
the three dependencies overridden — principal (via test headers), session, and
coordinator — and drives it with httpx + ASGITransport against the migration-gate
Postgres. Covers the create/read/share/revoke/rotate/delete flow + HTTP error
mapping (403/404/400).
"""

import base64
import uuid

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api import unified_secrets
from services.secrets_coordinator import SecretsCoordinator
from services.unified_secrets_service import UnifiedSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_ADMIN = uuid.uuid4()
_OUTSIDER = uuid.uuid4()
_GRANTEE = uuid.uuid4()
_COMPANY = uuid.uuid4()
_COMPANY_VAULT = f"company:{_COMPANY}"
_P = "/api/v2/secrets"


async def _principal_override(request: Request):
    uid = uuid.UUID(request.headers["x-test-user"])
    perms = {p for p in request.headers.get("x-test-perms", "").split(",") if p}
    return uid, perms


@pytest.fixture()
async def client(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        from llc.models.membership import LLCCompanyMembership
        from user_management.models.user import User

        for uid, name in ((_ADMIN, "admin"), (_OUTSIDER, "outsider"), (_GRANTEE, "grantee")):
            s.add(User(id=uid, email=f"{name}@example.com", username=name))
        s.add(LLCCompanyMembership(company_id=_COMPANY, user_id=_ADMIN, role="admin"))
        await s.commit()

    app = FastAPI()
    app.include_router(unified_secrets.router, prefix=_P)

    async def _session_override():
        async with maker() as sess:
            yield sess

    app.dependency_overrides[unified_secrets.get_session] = _session_override
    app.dependency_overrides[unified_secrets.get_coordinator] = lambda: SecretsCoordinator(
        UnifiedSecretsService(root_key=_ROOT)
    )
    app.dependency_overrides[unified_secrets.principal] = _principal_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t", follow_redirects=True) as c:
        yield c
    await engine.dispose()


def _as(user_id, perms=""):
    return {"x-test-user": str(user_id), "x-test-perms": perms}


async def _create(client, user=_ADMIN, vault=_COMPANY_VAULT, value="hunter2"):
    return await client.post(
        _P, json={"owner_vault": vault, "name": "db", "secret_type": "password", "value": value}, headers=_as(user)
    )


async def test_create_and_read(client):
    r = await _create(client)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["owner_vault"] == _COMPANY_VAULT and r.json()["version"] == 1
    rr = await client.get(f"{_P}/{sid}", headers=_as(_ADMIN))
    assert rr.status_code == 200 and rr.json()["value"] == "hunter2"


async def test_outsider_create_forbidden(client):
    assert (await _create(client, user=_OUTSIDER)).status_code == 403


async def test_outsider_read_forbidden(client):
    sid = (await _create(client)).json()["id"]
    assert (await client.get(f"{_P}/{sid}", headers=_as(_OUTSIDER))).status_code == 403


async def test_share_then_grantee_reads_then_revoke(client):
    sid = (await _create(client)).json()["id"]
    sh = await client.post(f"{_P}/{sid}/share", json={"grantee": f"user:{_GRANTEE}"}, headers=_as(_ADMIN))
    assert sh.status_code == 201, sh.text
    assert (await client.get(f"{_P}/{sid}", headers=_as(_GRANTEE))).json()["value"] == "hunter2"
    rv = await client.delete(f"{_P}/{sid}/share/user:{_GRANTEE}", headers=_as(_ADMIN))
    assert rv.status_code == 204
    assert (await client.get(f"{_P}/{sid}", headers=_as(_GRANTEE))).status_code == 403


async def test_rotate_and_list(client):
    sid = (await _create(client)).json()["id"]
    pr = await client.put(f"{_P}/{sid}", json={"value": "rotated"}, headers=_as(_ADMIN))
    assert pr.status_code == 200 and pr.json()["version"] == 2
    assert (await client.get(f"{_P}/{sid}", headers=_as(_ADMIN))).json()["value"] == "rotated"
    lst = await client.get(_P, headers=_as(_ADMIN))
    assert [s["id"] for s in lst.json()] == [sid]
    assert (await client.get(_P, headers=_as(_OUTSIDER))).json() == []


async def test_delete_then_404(client):
    sid = (await _create(client)).json()["id"]
    assert (await client.delete(f"{_P}/{sid}", headers=_as(_ADMIN))).status_code == 204
    assert (await client.get(f"{_P}/{sid}", headers=_as(_ADMIN))).status_code == 404


async def test_read_missing_404(client):
    assert (await client.get(f"{_P}/{uuid.uuid4()}", headers=_as(_ADMIN))).status_code == 404


async def test_invalid_vault_ref_400(client):
    r = await client.post(
        _P,
        json={"owner_vault": "bad:has:colons", "name": "x", "secret_type": "password", "value": "x"},
        headers=_as(_ADMIN),
    )
    assert r.status_code == 400
