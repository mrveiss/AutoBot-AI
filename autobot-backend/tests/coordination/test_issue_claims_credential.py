# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-claims client credential, end to end through the secrets manager (#18811).

Minted by a human with a real login JWT, stored by the real ``SecretsCoordinator`` in the minter's
own vault, verified on every request (no cache), audited per use with its accessor, refused outside
the issue-claims routes, and revoked so the next request is 401. See ``_issue_claims_harness``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from api import coordination_issue_claims_credential as cred
from autobot_shared.time_utils import now_utc
from models.secret import Secret
from models.secret_dependency import SecretDependency
from services.audit.taxonomy import AuditAction
from tests.coordination._issue_claims_harness import BASE, CREDENTIALS, mint, secret_id_of, with_credential
from tests.security._credential_harness import CALLER


def _claim(h, headers: dict, number: int = 7):
    return h.client.post(f"{BASE}/{number}", json={"owner": "s1"}, headers=headers)


def _row(h, model, **where):
    async def _load():
        async with h.db() as session:
            clauses = [getattr(model, k) == v for k, v in where.items()]
            return (await session.execute(select(model).where(*clauses))).scalars().first()

    return asyncio.run(_load())


def _update_secret(h, secret_id, **values) -> None:
    async def _apply():
        async with h.db() as session:
            secret = await session.get(Secret, secret_id)
            for key, value in values.items():
                setattr(secret, key, value)
            await session.commit()

    asyncio.run(_apply())


def _accesses(h) -> list:
    return [e for e in h.audit if e.action == AuditAction.SECRET_ACCESS.value]


def test_a_minted_credential_is_a_secret_in_the_minters_own_vault(harness):
    credential = mint(harness)
    secret_id, _, verifier = credential.partition(".")
    secret = _row(harness, Secret, id=secret_id_of(credential))
    assert secret.type == cred.CLAIMS_SECRET_TYPE and secret.owner_vault == f"user:{CALLER}"
    assert secret.extra_data["username"] == "alice" and secret.expires_at is not None
    edge = _row(harness, SecretDependency, secret_id=secret.id)
    assert (edge.dependent_kind, edge.dependent_id) == ("service", cred.CLAIMS_DEPENDENT_ID)
    assert len(verifier) >= 40 and secret_id == str(secret.id)
    assert any(e.action == AuditAction.CLAIMS_CREDENTIAL_MINT.value for e in harness.audit)


def test_a_valid_credential_claims_as_its_minter(harness):
    r = _claim(harness, with_credential(mint(harness)))
    assert r.status_code == 200 and r.json()["holder"]["agent_id"] == "alice/s1"


def test_every_use_is_audited_with_its_accessor(harness):
    credential = mint(harness)
    harness.audit.clear()
    assert _claim(harness, with_credential(credential)).status_code == 200
    (event,) = _accesses(harness)
    assert event.resource_id == str(secret_id_of(credential)) and event.actor_id == str(CALLER)
    assert event.metadata["accessor"] == f"{cred.CLAIMS_DEPENDENT_ID}:POST {BASE}/7" and event.outcome == "success"


def test_mint_use_revoke_use_is_200_200_401(harness):
    credential = mint(harness)
    assert _claim(harness, with_credential(credential)).status_code == 200
    revoked = harness.client.delete(CREDENTIALS, headers=with_credential(credential))
    assert revoked.status_code == 200 and revoked.json()["revoked"] is True
    assert _claim(harness, with_credential(credential), number=8).status_code == 401
    assert _row(harness, Secret, id=secret_id_of(credential)) is None
    assert any(e.action == AuditAction.CLAIMS_CREDENTIAL_REVOKE.value for e in harness.audit)


@pytest.mark.parametrize("path", ["/api/coordination/claims", "/api/coordination/claims?mine=1"])
def test_the_credential_is_refused_on_a_non_claims_route(harness, path):
    credential = mint(harness)
    assert harness.client.get(path, headers=with_credential(credential)).status_code == 401
    assert harness.client.get(path, headers={"Authorization": f"Bearer {credential}"}).status_code == 401


def test_the_credential_as_a_bearer_is_not_a_login_on_the_claims_routes(harness):
    credential = mint(harness)
    assert _claim(harness, {"Authorization": f"Bearer {credential}"}).status_code == 401


def test_the_credential_cannot_mint_another(harness):
    credential = mint(harness)
    assert harness.client.post(CREDENTIALS, headers=with_credential(credential)).status_code == 401


@pytest.mark.parametrize("tamper", ["verifier", "reference", "shape"])
def test_a_forged_credential_is_401_and_the_attempt_is_audited_in_aggregate(harness, tamper):
    credential = mint(harness)
    ref, _, verifier = credential.partition(".")
    forged = {
        "verifier": f"{ref}.{'x' * len(verifier)}",
        "reference": f"00000000-0000-0000-0000-000000000001.{verifier}",
        "shape": "not-a-credential",
    }[tamper]
    harness.audit.clear()
    assert _claim(harness, with_credential(forged)).status_code == 401
    assert _accesses(harness) == []  # a miss is not a row of its own: the throttle's window event counts it
    assert asyncio.run(cred.THROTTLE.tally.flush("testclient"))["failures"] == 1


def test_an_expired_credential_is_401(harness):
    credential = mint(harness)
    _update_secret(harness, secret_id_of(credential), expires_at=now_utc() - timedelta(seconds=1))
    assert _claim(harness, with_credential(credential)).status_code == 401


def test_a_deactivated_owner_is_401(harness):
    from user_management.models.user import User

    credential = mint(harness)

    async def _deactivate():
        async with harness.db() as session:
            await session.execute(update(User.__table__).where(User.__table__.c.id == CALLER).values(is_active=False))
            await session.commit()

    asyncio.run(_deactivate())
    assert _claim(harness, with_credential(credential)).status_code == 401


def test_a_password_change_since_minting_is_401(harness):
    credential = mint(harness)

    async def _revoked(claims: dict) -> None:
        assert claims["sub"] == "alice" and isinstance(claims["iat"], int)
        raise HTTPException(401, "password changed")

    harness.epoch.check = _revoked
    assert _claim(harness, with_credential(credential)).status_code == 401


@pytest.mark.parametrize("kind", ["internal_service_key", "auth_disabled", "session", "pre_17042_login_jwt"])
def test_only_a_human_with_a_login_token_mints(harness, kind):
    harness.resolution.configure(kind)
    headers = {} if kind == "auth_disabled" else harness.creds[kind]
    assert harness.client.post(CREDENTIALS, headers=headers).status_code in (401, 403)
    assert _row(harness, Secret, type=cred.CLAIMS_SECRET_TYPE) is None


def test_anonymous_mint_is_401(harness):
    assert harness.client.post(CREDENTIALS).status_code == 401


def test_any_human_mints_for_themselves_admin_not_required(harness):
    r = harness.client.post(CREDENTIALS, headers=harness.bob)
    assert r.status_code == 201 and r.json()["username"] == "bob"
    assert _claim(harness, with_credential(r.json()["credential"])).json()["holder"]["agent_id"] == "bob/s1"


def test_the_credential_value_is_never_logged(harness, caplog):
    caplog.set_level(logging.DEBUG)
    credential = mint(harness)
    _claim(harness, with_credential(credential))
    harness.client.delete(CREDENTIALS, headers=with_credential(credential))
    verifier = credential.partition(".")[2]
    assert verifier not in caplog.text
    assert all(verifier not in repr(e.to_dict()) for e in harness.audit)


def test_revoking_needs_the_credential_itself_not_a_login(harness):
    credential = mint(harness)
    assert harness.client.delete(CREDENTIALS, headers=harness.creds["login_jwt"]).status_code == 401
    assert _claim(harness, with_credential(credential)).status_code == 200


class _DialectSession:
    """Records the statements a mint issues, on a bind reporting dialect *name*."""

    def __init__(self, name: str):
        self.bind = type("Bind", (), {"dialect": type("Dialect", (), {"name": name})()})()
        self.executed: list[tuple[str, dict]] = []

    def get_bind(self):
        return self.bind

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params or {}))


def test_postgres_mints_take_a_per_user_transaction_lock():
    session, user_id = _DialectSession("postgresql"), CALLER
    asyncio.run(cred._lock_minting(session, user_id))
    ((statement, params),) = session.executed
    assert "pg_advisory_xact_lock" in statement
    assert params == {"lock_key": f"{cred.MINT_LOCK_NAMESPACE}:{user_id}"}


def test_a_store_without_advisory_locks_issues_no_lock_statement():
    session = _DialectSession("sqlite")
    asyncio.run(cred._lock_minting(session, CALLER))
    assert session.executed == []


def test_the_mint_lock_is_held_before_the_live_credentials_are_read(harness, monkeypatch):
    order: list[str] = []
    real_lock, real_revoke = cred._lock_minting, cred._revoke_previous

    async def lock(session, user_id):
        order.append("lock")
        await real_lock(session, user_id)

    async def revoke(session, coordinator, user_id):
        order.append("read-live")
        return await real_revoke(session, coordinator, user_id)

    monkeypatch.setattr(cred, "_lock_minting", lock)
    monkeypatch.setattr(cred, "_revoke_previous", revoke)
    mint(harness)
    assert order == ["lock", "read-live"]
