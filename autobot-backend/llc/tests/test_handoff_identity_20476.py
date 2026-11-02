# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who acts on a handoff comes from the verified caller, never the body (#20476)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from llc.api import _handoff_identity as identity
from llc.api.work_items import HandoffToAgentRequest, HandoffToHumanRequest, ReviewChangesRequest

_AGENT = uuid.uuid4()
_ORG, _REVIEWER = str(uuid.uuid4()), str(uuid.uuid4())


def test_a_person_hands_off_for_the_items_agent_whatever_the_body_says() -> None:
    item = SimpleNamespace(assignee_agent_id=_AGENT)
    with patch.object(identity, "is_interactive_human", return_value=True):
        assert identity.handing_off_agent(item, {"id": "someone"}) == str(_AGENT)


def test_an_agent_credential_is_refused_on_the_route() -> None:
    item = SimpleNamespace(assignee_agent_id=_AGENT)
    with patch.object(identity, "is_interactive_human", return_value=False), pytest.raises(HTTPException) as refused:
        identity.handing_off_agent(item, {"agent_id": str(_AGENT)})
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_a_named_reviewer_must_be_a_member() -> None:
    with patch.object(identity, "membership_role", AsyncMock(return_value="member")):
        assert await identity.member_reviewer(AsyncMock(), _ORG, _REVIEWER) == _REVIEWER
    with patch.object(identity, "membership_role", AsyncMock(return_value=None)), pytest.raises(HTTPException) as no:
        await identity.member_reviewer(AsyncMock(), _ORG, _REVIEWER)
    assert no.value.status_code == 422


@pytest.mark.asyncio
async def test_a_malformed_reviewer_reads_like_a_non_member() -> None:
    with pytest.raises(HTTPException) as refused:
        await identity.member_reviewer(AsyncMock(), _ORG, "not-a-uuid")
    assert refused.value.status_code == 422


@pytest.mark.parametrize(
    ("model", "forged"),
    [
        (HandoffToAgentRequest, ("user_id", "company_id", "user_display")),
        (HandoffToHumanRequest, ("agent_id", "company_id")),
        (ReviewChangesRequest, ("reviewer_user_id", "company_id")),
    ],
)
def test_the_request_bodies_have_no_acting_identity(model, forged) -> None:
    assert not set(forged) & set(model.model_fields)


def test_an_item_with_no_assigned_agent_is_refused_not_handed_off_as_none() -> None:
    item = SimpleNamespace(assignee_agent_id=None)
    with patch.object(identity, "is_interactive_human", return_value=True), pytest.raises(HTTPException) as refused:
        identity.handing_off_agent(item, {"id": "someone"})
    assert refused.value.status_code == 409
    assert "no assigned agent" in refused.value.detail


@pytest.mark.parametrize("route", ["review/approve", "review/request-changes"])
def test_a_non_interactive_credential_is_refused_on_the_review_routes(route: str) -> None:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api import work_items  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415
    from user_management.services import TenantContext  # noqa: PLC0415

    app = FastAPI()
    app.include_router(work_items.router)

    async def _session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=uuid.UUID(_ORG), user_id=uuid.uuid4())
    body = {"change_request": "please fix"} if route.endswith("changes") else None
    resp = TestClient(app).post(f"/work-items/{uuid.uuid4()}/{route}", json=body)
    assert resp.status_code == 403
