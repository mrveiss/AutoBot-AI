# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/facts/organization/{organization_id}`` answers only the caller's own organisation (#21396)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import knowledge_collaboration as collab

_ORG_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_ORG_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_DENIED = "Not authorized to access this organization's knowledge"


def _kb() -> MagicMock:
    kb = MagicMock()
    kb.ownership_manager.get_organization_facts = AsyncMock(return_value=["f1"])
    return kb


async def _call(kb: MagicMock, organization_id: str, user: dict):
    pagination = MagicMock(limit=10, offset=0)
    with (
        patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(collab, "_fetch_facts_from_redis", AsyncMock(return_value=[{"id": "f1"}])),
    ):
        return await collab.get_organization_knowledge(organization_id, MagicMock(), user, pagination)


@pytest.mark.asyncio
async def test_another_organisation_is_refused_before_the_manager_is_called():
    kb = _kb()
    with pytest.raises(HTTPException) as err:
        await _call(kb, _ORG_B, {"user_id": "alice", "org_id": _ORG_A})
    assert (err.value.status_code, err.value.detail) == (403, _DENIED)
    kb.ownership_manager.get_organization_facts.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_caller_with_no_organisation_is_refused():
    kb = _kb()
    with pytest.raises(HTTPException) as err:
        await _call(kb, _ORG_A, {"user_id": "alice"})
    assert (err.value.status_code, err.value.detail) == (403, _DENIED)
    kb.ownership_manager.get_organization_facts.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_own_organisation_is_answered():
    kb = _kb()
    out = await _call(kb, _ORG_A, {"user_id": "alice", "org_id": _ORG_A})
    assert out == {"facts": [{"id": "f1"}], "count": 1}
    kb.ownership_manager.get_organization_facts.assert_awaited_once_with(organization_id=_ORG_A, limit=10, offset=0)
