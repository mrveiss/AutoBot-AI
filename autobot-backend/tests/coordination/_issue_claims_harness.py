# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-claims routes behind the REAL canonical gate and the REAL secrets manager (#18811).

Every credential is resolved by production code: the real ``AuthenticationMiddleware`` JWT
extraction (a real signed JWT), the real ``auth_middleware.get_current_user`` with its real
internal-key branch, and the auth-disabled branch -- via ``tests.security._credential_harness``,
the same harness the #17042 human-decider tests use. The claims credential is minted, verified and
revoked by the real ``SecretsCoordinator`` over the real ``EnvelopeSecretsService`` on an in-memory
SQLite copy of the secrets tables. Only storage is stood in for: Redis (fakeredis), the database
engine, and the password-epoch check. Audit events are captured where the bus schedules them.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from api import coordination, coordination_issue_claims
from api import coordination_issue_claims_credential as cred
from api import coordination_issue_claims_throttle as claims_throttle
from api import envelope_secrets
from autobot_shared.coordination import work_claims
from llc.deps import get_session
from services.envelope_secrets_service import EnvelopeSecretsService
from services.secrets_coordinator import SecretsCoordinator
from tests.security._credential_harness import CALLER, LOGIN, OTHER, bearer, credentials, install_real_resolution

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]

BASE = "/api/coordination/issue-claims"
CREDENTIALS = f"{BASE}/credentials"
_ROOT = bytes(range(32))
_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
BOB_LOGIN = {**LOGIN, "username": "bob", "email": "bob@example.test", "user_id": str(OTHER)}


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


def _tables():
    from llc.models.membership import LLCCompanyMembership
    from models.secret import Secret
    from models.secret_dependency import SecretDependency
    from models.secret_grant import SecretGrant
    from user_management.models.role import Role, UserRole
    from user_management.models.team import TeamMembership
    from user_management.models.user import User

    models = (User, Role, UserRole, TeamMembership, LLCCompanyMembership, Secret, SecretGrant, SecretDependency)
    return [m.__table__ for m in models], User


@pytest_asyncio.fixture
async def secrets_db():
    """An in-memory secrets store with alice (``CALLER``) and bob (``OTHER``) as active users."""
    from user_management.models.base import Base

    tables, user = _tables()
    engine = create_async_engine(_SQLITE_URL)  # canonical: ignore py-adhoc-db-engine (in-memory test store)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine (test)
    async with maker() as session:
        for uid, name in ((CALLER, "alice"), (OTHER, "bob")):
            session.add(
                user(
                    id=uid,
                    email=f"{name}@example.test",
                    username=name,
                    password_hash=None,
                    display_name=name,
                    org_id=None,
                    is_platform_admin=False,
                    is_active=True,
                    is_verified=False,
                    mfa_enabled=False,
                    preferences={},
                )
            )
            await session.commit()  # one row per flush: a two-row batched insert failed UUID processing on SQLite
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def claims_redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    import autobot_shared.rate_limiter as rate_limiter
    from api import coordination_issue_claims_throttle as throttle

    for module in (work_claims, rate_limiter, throttle):
        monkeypatch.setattr(module, "get_async_redis_client", _client)
    yield client
    await client.flushall()


def _wire_gate(monkeypatch, real) -> SimpleNamespace:
    """Production credential resolution for every gate these routes reach."""
    import security.human_admin as human_admin

    resolution = install_real_resolution(real, monkeypatch)
    monkeypatch.setattr(cred, "auth_middleware", real)
    monkeypatch.setattr(human_admin, "auth_middleware", real)
    return resolution


def _capture_audit(monkeypatch) -> list:
    """Every audit event the bus is handed, in order."""
    from services.audit import audit

    events: list = []
    monkeypatch.setattr(audit, "emit", lambda event: events.append(event) or True)
    return events


async def _password_epoch_ok(claims: dict) -> None:
    return None


@pytest.fixture
def harness(real_auth_middleware, monkeypatch, claims_redis, secrets_db):
    """``client``, ``audit`` events, ``resolution.configure(kind)``, ``db`` session maker, ``creds``."""
    resolution = _wire_gate(monkeypatch, real_auth_middleware)
    coordinator = SecretsCoordinator(EnvelopeSecretsService(root_key=_ROOT))
    monkeypatch.setattr(envelope_secrets, "_coordinator", coordinator)
    epoch = SimpleNamespace(check=_password_epoch_ok)
    monkeypatch.setattr(cred, "reject_if_revoked_by_password_change", lambda claims: epoch.check(claims))
    app = FastAPI()
    app.include_router(cred.router, prefix="/api/coordination")  # the same order core_routers registers
    app.include_router(coordination_issue_claims.router, prefix="/api/coordination")
    app.include_router(coordination.router, prefix="/api/coordination")

    async def _session():
        async with secrets_db() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    monkeypatch.setattr(cred.THROTTLE.tally, "_local", {})  # the in-process fallback tally starts empty
    monkeypatch.setattr(cred.THROTTLE, "local", claims_throttle.LocalFailureWindow())  # so does the in-process window
    return SimpleNamespace(
        app=app,
        client=TestClient(app, raise_server_exceptions=False),
        audit=_capture_audit(monkeypatch),
        resolution=resolution,
        db=secrets_db,
        creds=credentials(),
        epoch=epoch,
        bob=bearer(BOB_LOGIN),
    )


def mint(h) -> str:
    """Mint alice's credential with her real login JWT; the credential string."""
    response = h.client.post(CREDENTIALS, headers=h.creds["login_jwt"])
    assert response.status_code == 201, response.text
    return response.json()["credential"]


def with_credential(credential: str) -> dict:
    return {cred.CREDENTIAL_HEADER: credential}


def secret_id_of(credential: str) -> uuid.UUID:
    return uuid.UUID(credential.partition(".")[0])
