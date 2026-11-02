# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: the SLM may delete a stored SSH password only under an approval that this backend still accepts.

The real claim route and the real claim logic run here; only the database session is faked. A valid
approval is accepted once; every other shape of approval is refused and spends nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from api import internal_slm_credential_proposals as proposals
from autobot_shared.slm_credential_deletion import ACTION, claim_path
from models.approval import ApprovalStatus
from services import slm_ssh_password_claim as claim

_KEY = "k" * 40  # pragma: allowlist secret
_ID = uuid.uuid4()


def _approval(**overrides) -> SimpleNamespace:
    fields = {
        "id": _ID,
        "company_id": None,
        "status": ApprovalStatus.APPROVED.value,
        "decided_by_user": "alice",
        "decided_at": datetime.now(timezone.utc),
        "context": {"action": ACTION, "node_id": "node-a", "credential_kind": "ssh_password"},
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _session(approval, rowcount: int = 1) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=approval)
    session.execute = AsyncMock(return_value=SimpleNamespace(rowcount=rowcount))
    session.commit = AsyncMock()
    return session


def _client(session: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(proposals.router, prefix="/api")
    app.dependency_overrides[proposals.get_db_session] = lambda: session
    return TestClient(app)


def _claim(client: TestClient, node_id: str = "node-a", headers: dict | None = None):
    headers = {"X-Internal-API-Key": _KEY} if headers is None else headers
    return client.post(claim_path(str(_ID)), json={"node_id": node_id}, headers=headers)


@pytest.fixture(autouse=True)
def _key(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)


def test_a_valid_approval_is_accepted_and_spent() -> None:
    session = _session(_approval())
    response = _claim(_client(session))
    assert response.status_code == 200 and response.json() == {"approval_id": str(_ID), "node_id": "node-a"}
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("approval", "node_id"),
    [
        (None, "node-a"),
        (_approval(), "node-b"),
        (
            _approval(context={"action": "other_action", "node_id": "node-a", "credential_kind": "ssh_password"}),
            "node-a",
        ),
        (_approval(context={"action": ACTION, "node_id": "node-a", "credential_kind": "api_key"}), "node-a"),
        (_approval(status=ApprovalStatus.PENDING.value), "node-a"),
        (_approval(status=ApprovalStatus.REJECTED.value), "node-a"),
        (_approval(decided_by_user=None), "node-a"),
        (_approval(decided_by_user="service:slm"), "node-a"),
        (_approval(decided_by_user="unknown"), "node-a"),
        (_approval(decided_at=None), "node-a"),
        (_approval(company_id=uuid.uuid4()), "node-a"),
        (
            _approval(
                context={
                    "action": ACTION,
                    "node_id": "node-a",
                    "credential_kind": "ssh_password",
                    "consumed_at": "2026-11-02T00:00:00+00:00",
                }
            ),
            "node-a",
        ),
    ],
    ids=[
        "no-approval",
        "wrong-node",
        "wrong-action",
        "wrong-credential",
        "unapproved-pending",
        "rejected",
        "no-decider",
        "service-decider",
        "fallback-decider",
        "no-decision-time",
        "company-scoped",
        "already-consumed",
    ],
)
def test_every_other_approval_is_refused_and_spends_nothing(approval, node_id) -> None:
    session = _session(approval)
    response = _claim(_client(session), node_id)
    assert response.status_code == 403
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_a_lost_race_is_refused_and_not_committed() -> None:
    """Two claims read an unspent approval; the atomic update spends it once, so the second changes no row."""
    session = _session(_approval(), rowcount=0)
    assert _claim(_client(session)).status_code == 403
    session.commit.assert_not_awaited()


def test_the_claim_needs_the_key() -> None:
    session = _session(_approval())
    client = _client(session)
    assert _claim(client, headers={}).status_code == 403
    assert _claim(client, headers={"X-Internal-API-Key": "wrong"}).status_code == 403
    session.get.assert_not_awaited()


async def test_the_spending_update_names_the_unspent_state() -> None:
    session = _session(_approval())
    await claim.claim_deletion_approval(session, _ID, "node-a")
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "UPDATE approvals" in sql and "->> " in sql and "IS NULL" in sql and "||" in sql
    assert "consumed_at" in str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()).params)
