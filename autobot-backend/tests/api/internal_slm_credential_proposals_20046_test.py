# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's internal propose and claim routes, through the REAL auth gate (#20046, #16333).

The route modules' own tests call the handlers directly and miss the gate: ``get_current_user`` refuses
the internal key on any route that does not name its caller with ``service_opt_in``. Here the REAL
``auth_middleware`` resolves the key; only the database, the approval service and the audit store are
stood in for.
"""

import importlib
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth_service_opt_in
from autobot_shared import node_proxy
from autobot_shared.slm_credential_actions import PROPOSAL_PATH, SSH_PASSWORD_DELETE, claim_path
from testkit.fake_async_session import FakeAsyncSession

KEY = "k" * 40  # pragma: allowlist secret
KEY_HEADERS = {"X-Internal-API-Key": KEY}
NODE = {"action": SSH_PASSWORD_DELETE.name, "node_id": "node-a"}
CLAIM = claim_path(str(uuid.UUID(int=1)))  # fixed: a random id gives each xdist worker a different test id
PROPOSE = PROPOSAL_PATH


@pytest.fixture
def world(real_auth_middleware, monkeypatch):
    """The router imported against the real auth module, with the real key check and a recorded audit."""
    monkeypatch.setitem(sys.modules, "auth_middleware", real_auth_middleware)
    monkeypatch.delitem(sys.modules, "api.internal_slm_credential_proposals", raising=False)
    module = importlib.import_module("api.internal_slm_credential_proposals")
    monkeypatch.setattr(node_proxy, "internal_api_key", lambda: KEY)
    monkeypatch.setattr(real_auth_middleware, "resolve_human_user", AsyncMock(return_value=None))
    approval = SimpleNamespace(id=uuid.UUID("00000000-0000-4000-8000-00000000000c"), status="pending")
    service = MagicMock()
    service.list_approvals = AsyncMock(return_value=[])
    service.create_approval = AsyncMock(return_value=approval)
    claim = AsyncMock()
    monkeypatch.setattr(module, "ApprovalGateService", lambda _session: service)
    monkeypatch.setattr(module, "claim_approval", claim)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[module.get_db_session] = lambda: FakeAsyncSession()
    with patch("services.audit.audit.record_committed", AsyncMock(return_value=True)) as recorded:
        yield SimpleNamespace(
            client=TestClient(app, raise_server_exceptions=False), service=service, claim=claim, audit=recorded
        )
    sys.modules.pop("api.internal_slm_credential_proposals", None)


def test_the_slm_key_proposes_through_the_real_gate_and_the_admission_is_audited(world) -> None:
    response = world.client.post(PROPOSE, json=NODE, headers=KEY_HEADERS)
    assert response.status_code == 201 and response.json()["created"] is True
    event = world.audit.await_args.args[0]
    assert event.actor_id == "service:slm-ssh-password-deletion" and event.resource_id == PROPOSE


def test_the_slm_key_claims_through_the_real_gate(world) -> None:
    response = world.client.post(
        CLAIM, json={"action": SSH_PASSWORD_DELETE.name, "node_id": "node-a"}, headers=KEY_HEADERS
    )
    assert response.status_code == 200 and response.json()["node_id"] == "node-a"
    world.claim.assert_awaited_once()


@pytest.mark.parametrize("url", [PROPOSE, CLAIM], ids=["propose", "claim"])
@pytest.mark.parametrize("headers", [{}, {"X-Internal-API-Key": "wrong"}], ids=["no_key", "wrong_key"])
def test_no_key_or_a_wrong_key_is_refused_and_nothing_is_proposed_or_spent(world, url, headers) -> None:
    body = NODE
    assert world.client.post(url, json=body, headers=headers).status_code in (401, 403)
    world.service.create_approval.assert_not_awaited()
    world.claim.assert_not_awaited()


def test_the_admission_is_recorded_before_the_route_runs(world) -> None:
    world.audit.return_value = False  # fail closed: an unrecorded admission is refused
    assert world.client.post(PROPOSE, json=NODE, headers=KEY_HEADERS).status_code == 503
    world.service.create_approval.assert_not_awaited()


def test_all_handlers_name_the_one_caller() -> None:
    module = importlib.import_module("api.internal_slm_credential_proposals")
    for handler in (
        module.propose_credential_change,
        module.claim_credential_approval,
        module.report_credential_outcome,
    ):
        assert getattr(handler, auth_service_opt_in.SERVICE_OPT_IN_ATTR) == module.SLM_CALLER


@pytest.mark.parametrize("node_id", [".", ".."], ids=["dot", "dotdot"])
def test_a_dot_segment_node_id_is_refused_before_it_can_vanish_from_the_delete_path(world, node_id) -> None:
    response = world.client.post(PROPOSE, json={**NODE, "node_id": node_id}, headers=KEY_HEADERS)
    assert response.status_code == 422
    world.service.create_approval.assert_not_awaited()


def test_propose_is_refused_with_a_clear_message_when_slm_and_backend_are_split(world) -> None:
    from autobot_shared.slm_credential_actions import SPLIT_DEPLOYMENT_MESSAGE  # noqa: PLC0415
    from autobot_shared.ssot_config import config  # noqa: PLC0415

    with patch.object(config.vm, "slm", "slm.cluster.example"), patch.object(config.tls, "slm_tls_enabled", False):
        response = world.client.post(PROPOSE, json=NODE, headers=KEY_HEADERS)
    assert response.status_code == 409 and response.json()["detail"] == SPLIT_DEPLOYMENT_MESSAGE
    world.service.create_approval.assert_not_awaited()
