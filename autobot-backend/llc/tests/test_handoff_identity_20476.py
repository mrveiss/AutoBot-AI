# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who acts on a handoff comes from the verified caller, never the body (#20476)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

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
