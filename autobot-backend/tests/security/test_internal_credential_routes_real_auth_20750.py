# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The internal credential-proposal routes admit the service key through the REAL auth gate (#20750, #16333).

The updater's propose, claim and outcome calls carry only ``X-Internal-API-Key``. ``get_current_user``
refuses that key unless the handler names its caller with ``service_opt_in``, so a route without it
answers 401/403 once auth is on. The real ``auth_middleware`` runs here (``load_real_auth_middleware``);
only the database, the approval service and the audit sinks are stood in.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import internal_slm_credential_proposals as routes
from auth_service_opt_in import SERVICE_OPT_IN_ATTR
from autobot_shared.slm_credential_actions import INTERNAL_KEY_REALIGN, PROPOSAL_PATH, claim_path, outcome_path
from tests.conftest import load_real_auth_middleware

_KEY = "k" * 40  # pragma: allowlist secret
_ID = uuid.uuid4()
_BODY = {"action": INTERNAL_KEY_REALIGN.name, "node_id": "node-b"}
_HANDLERS = (routes.propose_credential_change, routes.claim_credential_approval, routes.report_credential_outcome)


def _approval() -> SimpleNamespace:
    context = {"action": INTERNAL_KEY_REALIGN.name, "node_id": "node-b", "credential_kind": "internal_api_key"}
    return SimpleNamespace(
        id=_ID,
        status="approved",
        company_id=None,
        decided_by_user="alice",
        decided_at="2026-11-03T22:00:00+00:00",
        requested_by_agent="slm-update:node-b",
        context={**context, "consumed_at": "2026-11-03T22:01:00+00:00"},
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    real = load_real_auth_middleware()
    monkeypatch.setattr(real, "verify_internal_api_key", lambda provided: provided == _KEY)
    monkeypatch.setattr("auth_service_opt_in.verify_internal_api_key", lambda provided: provided == _KEY)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    session = MagicMock(commit=AsyncMock(), rollback=AsyncMock(), get=AsyncMock(return_value=_approval()))
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    app.dependency_overrides[routes.get_db_session] = lambda: session
    app.dependency_overrides[routes.get_current_user] = real.get_current_user  # the real gate, not a stub
    service = MagicMock()
    service.list_approvals = AsyncMock(return_value=[])
    service.create_approval = AsyncMock(
        side_effect=lambda **kw: SimpleNamespace(id=_ID, status="pending", decided_by_user=None, **kw)
    )
    with (
        patch.object(routes, "ApprovalGateService", return_value=service),
        patch("services.audit.audit.record_committed", AsyncMock(return_value=True)) as admitted,
        patch("services.slm_credential_texts.audit_log", AsyncMock(return_value=True)),
        patch.object(routes, "claim_approval", AsyncMock(return_value=_approval())),
    ):
        test_client = TestClient(app, raise_server_exceptions=False)
        test_client.admitted = admitted
        yield test_client


@pytest.mark.parametrize("handler", _HANDLERS, ids=lambda h: h.__name__)
def test_every_handler_names_its_caller(handler) -> None:
    assert getattr(handler, SERVICE_OPT_IN_ATTR, None), f"{handler.__name__} has no service_opt_in"


@pytest.mark.parametrize(
    "path, body, expected",
    [
        (PROPOSAL_PATH, _BODY, 201),
        (claim_path(str(_ID)), _BODY, 200),
        (outcome_path(str(_ID)), {**_BODY, "result": "applied"}, 204),
    ],
    ids=["propose", "claim", "outcome"],
)
def test_the_internal_key_alone_reaches_the_route_and_the_admission_is_audited(client, path, body, expected) -> None:
    response = client.post(path, json=body, headers={"X-Internal-API-Key": _KEY})
    assert response.status_code == expected, response.text
    client.admitted.assert_awaited_once()


@pytest.mark.parametrize("path", [PROPOSAL_PATH, claim_path(str(_ID)), outcome_path(str(_ID))])
def test_no_key_or_a_wrong_key_is_refused(client, path) -> None:
    assert client.post(path, json=_BODY).status_code in (401, 403)
    assert client.post(path, json=_BODY, headers={"X-Internal-API-Key": "wrong"}).status_code in (401, 403)
    client.admitted.assert_not_awaited()
