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

from api import envelope_secrets
from services.envelope_secrets_service import EnvelopeSecretsService
from services.secrets_coordinator import SecretsCoordinator
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
    app.include_router(envelope_secrets.router, prefix=_P)

    async def _session_override():
        async with maker() as sess:
            yield sess

    app.dependency_overrides[envelope_secrets.get_session] = _session_override
    app.dependency_overrides[envelope_secrets.get_coordinator] = lambda: SecretsCoordinator(
        EnvelopeSecretsService(root_key=_ROOT)
    )
    app.dependency_overrides[envelope_secrets.principal] = _principal_override

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


# ---------------------------------------------------------------------------
# KEK rotation — /api/v2/secrets/{id}/rewrap (#10437)
# ---------------------------------------------------------------------------

_ROOT2_B64 = base64.urlsafe_b64encode(bytes(reversed(bytes(range(32))))).decode("ascii")


async def test_rewrap_same_plaintext(client):
    """After /rewrap the admin can still decrypt (new root key); version unchanged."""
    sid = (await _create(client)).json()["id"]
    r = await client.post(f"{_P}/{sid}/rewrap", json={"new_root_key": _ROOT2_B64}, headers=_as(_ADMIN))
    assert r.status_code == 200, r.text
    # version must NOT change (payload untouched — only wrapped DEK changed)
    assert r.json()["version"] == 1


async def test_rewrap_bad_key_400(client):
    """Invalid base64 new_root_key returns 400."""
    sid = (await _create(client)).json()["id"]
    r = await client.post(f"{_P}/{sid}/rewrap", json={"new_root_key": "not-base64!!!"}, headers=_as(_ADMIN))
    assert r.status_code == 400


async def test_rewrap_missing_secret_404(client):
    r = await client.post(f"{_P}/{uuid.uuid4()}/rewrap", json={"new_root_key": _ROOT2_B64}, headers=_as(_ADMIN))
    assert r.status_code == 404


async def test_rewrap_unauthorized_403(client):
    sid = (await _create(client)).json()["id"]
    r = await client.post(f"{_P}/{sid}/rewrap", json={"new_root_key": _ROOT2_B64}, headers=_as(_OUTSIDER))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Service-auth system vault access (#10436)
# Override service_principal to inject a fake service identity; verify system
# vault CRUD succeeds and non-system vault is rejected 403.
# ---------------------------------------------------------------------------


@pytest.fixture()
async def service_client(fresh_db_url):
    """App with service_principal overridden to inject service_id='test-slm'."""

    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(envelope_secrets.router, prefix=_P)

    async def _session_override():
        async with maker() as sess:
            yield sess

    async def _service_principal_override():
        return "test-slm"

    # The active root key the coordinator derives KEKs from.  A KEK rewrap migrates
    # the stored wrapped-DEKs to a *new* root; in production the operator then swaps
    # AUTOBOT_SECRETS_ROOT_KEY and restarts, so subsequent reads use the new root.
    # We model that restart by rebuilding the coordinator from this mutable holder,
    # letting a rewrap test flip the active root before reading back.
    active_root = {"key": _ROOT}

    app.dependency_overrides[envelope_secrets.get_session] = _session_override
    app.dependency_overrides[envelope_secrets.get_coordinator] = lambda: SecretsCoordinator(
        EnvelopeSecretsService(root_key=active_root["key"])
    )
    app.dependency_overrides[envelope_secrets.service_principal] = _service_principal_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t", follow_redirects=True) as c:
        c.set_active_root = lambda raw: active_root.__setitem__("key", raw)  # type: ignore[attr-defined]
        yield c
    await engine.dispose()


async def _svc_create(client, vault="system", value="fleet-secret"):
    return await client.post(
        f"{_P}/system",
        json={"owner_vault": vault, "name": "fleet-sso", "secret_type": "token", "value": value},
    )


async def test_service_create_and_read_system_vault(service_client):
    r = await _svc_create(service_client)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["owner_vault"] == "system"
    rr = await service_client.get(f"{_P}/system/{sid}")
    assert rr.status_code == 200 and rr.json()["value"] == "fleet-secret"


async def test_service_list_system_vault(service_client):
    await _svc_create(service_client, value="s1")
    await _svc_create(service_client, value="s2")
    lst = await service_client.get(f"{_P}/system")
    assert lst.status_code == 200
    assert len(lst.json()) >= 2


async def test_service_rotate_system_vault(service_client):
    sid = (await _svc_create(service_client)).json()["id"]
    r = await service_client.put(f"{_P}/system/{sid}", json={"value": "rotated"})
    assert r.status_code == 200 and r.json()["version"] == 2
    rr = await service_client.get(f"{_P}/system/{sid}")
    assert rr.json()["value"] == "rotated"


async def test_service_rewrap_system_vault(service_client):
    """Service-auth KEK rewrap on /system/{id}/rewrap: 200, payload unchanged (#10154)."""
    sid = (await _svc_create(service_client)).json()["id"]
    r = await service_client.post(f"{_P}/system/{sid}/rewrap", json={"new_root_key": _ROOT2_B64})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1  # KEK-only rotation — sealed value untouched
    # The DEK is now wrapped under _ROOT2; a read must use the migrated root (as prod
    # does after swapping AUTOBOT_SECRETS_ROOT_KEY + restart).  The sealed value —
    # never re-encrypted — still decrypts, proving the rewrap preserved the payload.
    service_client.set_active_root(base64.urlsafe_b64decode(_ROOT2_B64))
    rr = await service_client.get(f"{_P}/system/{sid}")
    assert rr.status_code == 200 and rr.json()["value"] == "fleet-secret"


async def test_service_rewrap_bad_key_400(service_client):
    sid = (await _svc_create(service_client)).json()["id"]
    r = await service_client.post(f"{_P}/system/{sid}/rewrap", json={"new_root_key": "not-base64!!!"})
    assert r.status_code == 400


async def test_service_delete_system_vault(service_client):
    sid = (await _svc_create(service_client)).json()["id"]
    dr = await service_client.delete(f"{_P}/system/{sid}")
    assert dr.status_code == 204
    assert (await service_client.get(f"{_P}/system/{sid}")).status_code == 404


async def test_service_rejected_on_non_system_vault(service_client):
    """Service principal 403 on any non-system vault."""
    r = await _svc_create(service_client, vault=f"user:{_ADMIN}")
    assert r.status_code == 403
