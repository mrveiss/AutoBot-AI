# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one share/unshare route (collaboration): owner or admin may write, a reader gets 403,
a non-reader 404, and the request body keeps ShareFactRequest's limits (#18795)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api import knowledge_collaboration as collab
from api.schemas_knowledge import ShareKnowledgeRequest

OWNER = {"user_id": "alice", "role": "user"}
OTHER = {"user_id": "carol", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}


def _kb(metadata: dict):
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value={"fact_id": "f1", "metadata": metadata})
    kb.ownership_manager.check_access = AsyncMock(return_value=metadata.get("visibility") == "public")
    kb.ownership_manager.share_fact = AsyncMock(return_value={"shared_with": ["u2"], "visibility": "shared"})
    kb.ownership_manager.unshare_fact = AsyncMock(return_value={"shared_with": [], "visibility": "private"})
    kb.update_fact = AsyncMock(return_value={"status": "success"})
    return kb


async def _call(action: str, kb, user: dict):
    with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        if action == "share":
            body = ShareKnowledgeRequest(user_ids=["u2"])
            return await collab.share_knowledge("f1", body, MagicMock(), user)
        return await collab.unshare_knowledge("f1", "u2", MagicMock(), user, entity_type="user")


ACTIONS = pytest.mark.parametrize("action", ["share", "unshare"])


@pytest.mark.asyncio
@ACTIONS
async def test_the_owner_can_share_and_unshare(action):
    kb = _kb({"owner_id": "alice", "visibility": "private"})
    assert (await _call(action, kb, OWNER))["success"] is True
    kb.update_fact.assert_awaited_once()


@pytest.mark.asyncio
@ACTIONS
@pytest.mark.parametrize("metadata", [{"visibility": "private"}, {"owner_id": "bob", "visibility": "private"}])
async def test_an_admin_can_share_and_unshare_an_ownerless_or_foreign_fact(action, metadata):
    kb = _kb(metadata)
    assert (await _call(action, kb, ADMIN))["success"] is True
    kb.update_fact.assert_awaited_once()


@pytest.mark.asyncio
@ACTIONS
async def test_a_non_owner_reader_gets_403(action):
    kb = _kb({"owner_id": "bob", "visibility": "public"})
    with pytest.raises(HTTPException) as err:
        await _call(action, kb, OTHER)
    assert err.value.status_code == 403
    kb.update_fact.assert_not_awaited()


@pytest.mark.asyncio
@ACTIONS
async def test_a_non_reader_gets_404(action):
    kb = _kb({"owner_id": "bob", "visibility": "private"})
    with pytest.raises(HTTPException) as err:
        await _call(action, kb, OTHER)
    assert (err.value.status_code, err.value.detail) == (404, "Fact not found")
    kb.update_fact.assert_not_awaited()


@pytest.mark.asyncio
@ACTIONS
async def test_a_missing_fact_is_the_same_404_for_a_non_admin(action):
    kb = _kb({})
    kb.get_fact = MagicMock(return_value=None)
    with pytest.raises(HTTPException) as err:
        await _call(action, kb, OTHER)
    assert (err.value.status_code, err.value.detail) == (404, "Fact not found")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_ids": [], "group_ids": []},
        {"user_ids": ["u"] * 51},
        {"group_ids": ["g"] * 51},
        {"user_ids": ["x" * 101]},
        {"group_ids": ["x" * 101]},
        {"user_ids": [""]},
    ],
)
def test_the_share_body_limits_are_a_422(payload):
    with pytest.raises(ValidationError):
        ShareKnowledgeRequest(**payload)


@pytest.mark.parametrize(
    "payload",
    [{"user_ids": ["u"] * 50}, {"group_ids": ["x" * 100]}, {"user_ids": ["u"], "group_ids": ["g"]}],
)
def test_the_share_body_accepts_the_limits_themselves(payload):
    assert ShareKnowledgeRequest(**payload)
