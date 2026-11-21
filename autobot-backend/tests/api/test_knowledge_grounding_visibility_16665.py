# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Grounding reads the KB as the calling user (#16665): another user's private fact never grounds a claim."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.knowledge_grounding import router as grounding_router
from auth_middleware import get_current_user
from knowledge.ownership import KnowledgeOwnership
from knowledge.read_path_fakes_16665 import QuarantineGatedKB, quarantined_fact
from services.grounded_agent import GroundedAgent
from services.knowledge_grounding_models import Claim, ClaimStatus


@pytest.fixture
def grounded_agent():
    return GroundedAgent()


@pytest.fixture
def sample_claim():
    return Claim(
        claim_text="System latency increased by 15%",
        subject="System latency",
        predicate="increased by",
        object="15%",
        confidence=0.95,
    )


def _build_grounding_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(grounding_router)
    return app


@pytest.mark.asyncio
async def test_grounding_never_verifies_a_claim_against_another_users_private_fact(grounded_agent, sample_claim):
    """#16665: user B's claim is not grounded on user A's private fact; A's is; no user grounds on nothing."""
    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        return_value=[
            {
                "fact_id": "fact-a",
                "content": "System latency increased by 15% (alice's private note)",
                "similarity_score": 0.95,
                "metadata": {"owner_id": "alice", "visibility": "private"},
            }
        ]
    )
    mock_kb.ownership_manager = KnowledgeOwnership(None)
    grounded_agent.kb = mock_kb

    for_bob = await grounded_agent._classify_and_verify_claim(sample_claim, "bob")
    for_alice = await grounded_agent._classify_and_verify_claim(sample_claim, "alice")
    for_nobody = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert for_alice.kb_status == ClaimStatus.IN_KB
    for denied in (for_bob, for_nobody):
        assert denied.kb_status == ClaimStatus.UNKNOWN
        assert "alice" not in repr(denied.evidence) and denied.kb_source in (None, "")


def _verify_claim_as(user: dict, kb) -> "object":
    agent = GroundedAgent()
    agent.kb = kb
    app = _build_grounding_test_app()
    app.dependency_overrides[get_current_user] = lambda: user
    body = {"claim_text": "System latency increased by 15%"}
    with patch("api.knowledge_grounding.get_grounded_agent", return_value=agent):
        return TestClient(app).post("/verify-claim", json=body)


def _alices_private_kb():
    kb = AsyncMock()
    kb.search = AsyncMock(
        return_value=[
            {
                "fact_id": "fact-a",
                "content": "alices private latency note",
                "similarity_score": 0.95,
                "metadata": {"owner_id": "alice", "visibility": "private"},
            }
        ]
    )
    kb.ownership_manager = KnowledgeOwnership(None)
    return kb


def test_verify_claim_route_does_not_return_another_users_private_fact():
    """#16665: B's verdict is built from nothing of A's; A's still is; an unresolvable caller is a 401."""
    for_bob = _verify_claim_as({"user_id": "bob"}, _alices_private_kb())
    for_alice = _verify_claim_as({"user_id": "alice"}, _alices_private_kb())
    nobody = _verify_claim_as({"role": "user"}, _alices_private_kb())

    assert for_alice.json()["kb_status"] == "in_kb"
    assert for_bob.status_code == 200 and for_bob.json()["kb_status"] == "unknown"
    assert "alices" not in for_bob.text and "fact-a" not in for_bob.text
    assert nobody.status_code == 401


def test_ground_response_route_does_not_ground_on_another_users_private_fact():
    agent = GroundedAgent()
    agent.kb = _alices_private_kb()
    agent.llm_service = AsyncMock()
    agent.llm_service.chat = AsyncMock(
        return_value=MagicMock(content=json.dumps([{"claim_text": "latency up", "confidence": 0.9}]))
    )
    body = {"query": "latency?", "agent_response": "latency up"}

    def post(user):
        app = _build_grounding_test_app()
        app.dependency_overrides[get_current_user] = lambda: user
        with patch("api.knowledge_grounding.get_grounded_agent", return_value=agent):
            return TestClient(app).post("/ground-response", json=body)

    for_bob, for_alice, nobody = post({"user_id": "bob"}), post({"user_id": "alice"}), post({"role": "user"})

    assert "alices private" not in for_bob.text and "fact-a" not in for_bob.text
    assert len(for_bob.json()["data"]["verified_claims"]) == 0
    assert len(for_alice.json()["data"]["verified_claims"]) == 1
    assert nobody.status_code == 401


ADMIN = {"user_id": "root", "role": "admin"}
USERS = [{"user_id": "alice", "role": "user"}, {"user_id": "bob", "role": "user"}, ADMIN]


def _ground_response_as(user: dict, kb):
    agent = GroundedAgent()
    agent.kb = kb
    agent.llm_service = AsyncMock()
    agent.llm_service.chat = AsyncMock(
        return_value=MagicMock(content=json.dumps([{"claim_text": "latency up", "confidence": 0.9}]))
    )
    app = _build_grounding_test_app()
    app.dependency_overrides[get_current_user] = lambda: user
    with (
        patch("api.knowledge_grounding.get_grounded_agent", return_value=agent),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        return TestClient(app).post("/ground-response", json={"query": "latency?", "agent_response": "latency up"})


def test_verify_claim_route_grounds_an_admin_on_another_users_private_fact():
    with patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)):
        response = _verify_claim_as(ADMIN, _alices_private_kb())

    assert response.status_code == 200 and response.json()["kb_status"] == "in_kb"


def test_ground_response_route_does_not_ground_an_admin_on_another_users_private_fact():
    """A grounding pass reads by the caller's normal rules, with no admin bypass (scoped_reader, #16665)."""
    response = _ground_response_as(ADMIN, _alices_private_kb())

    assert response.status_code == 200 and len(response.json()["data"]["verified_claims"]) == 0
    assert "alices private" not in response.text and "fact-a" not in response.text


def _quarantine_only_kb():
    """A KB whose only fact is quarantined; the control twin hands the same fact over ungated."""
    kb = QuarantineGatedKB(only_quarantined=True)
    ungated = QuarantineGatedKB(only_quarantined=True)
    ungated.search = AsyncMock(return_value=[quarantined_fact()])
    return kb, ungated


@pytest.mark.parametrize("user", USERS)
def test_verify_claim_never_grounds_on_a_quarantined_research_fact(user):
    kb, ungated = _quarantine_only_kb()
    with patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)):
        gated, control = _verify_claim_as(user, kb), _verify_claim_as(user, ungated)

    assert control.json()["kb_status"] == "in_kb", "control: the same fact ungated must ground the claim"
    assert gated.status_code == 200 and gated.json()["kb_status"] == "unknown"


@pytest.mark.parametrize("user", USERS)
def test_ground_response_never_grounds_on_a_quarantined_research_fact(user):
    kb, ungated = _quarantine_only_kb()
    gated, control = _ground_response_as(user, kb), _ground_response_as(user, ungated)

    assert len(control.json()["data"]["verified_claims"]) == 1, "control: ungated, the fact grounds the claim"
    assert len(gated.json()["data"]["verified_claims"]) == 0
