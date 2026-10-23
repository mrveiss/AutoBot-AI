# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The KB principal: ``kb_principal``, the ``SYSTEM_SCOPE`` sentinel and the one result filter (#16664)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot_shared.scoping import Principal
from knowledge.ownership import KnowledgeOwnership
from knowledge.search_filters import (
    SYSTEM_SCOPE,
    filter_for_principal,
    kb_principal,
    principal_for_identity,
    require_kb_principal,
)

PRIVATE_OF_B = {"id": "f-b", "metadata": {"owner_id": "B", "visibility": "private"}}
OWN = {"id": "f-a", "metadata": {"owner_id": "A", "visibility": "private"}}
SYSTEM = {"id": "f-s", "metadata": {"owner_id": "B", "visibility": "system"}}
GROUP = {"id": "f-g", "metadata": {"owner_id": "B", "visibility": "group", "group_ids": ["g1"]}}


def test_kb_principal_is_built_from_the_same_context_every_kb_read_uses():
    principal = kb_principal({"user_id": "A", "org_id": 7})

    assert principal == Principal("A", "7", frozenset(), True)


def test_kb_principal_carries_the_team_memberships_of_an_orm_user():
    team = SimpleNamespace(team_id=3, team=SimpleNamespace(is_deleted=False))
    gone = SimpleNamespace(team_id=4, team=SimpleNamespace(is_deleted=True))
    user = SimpleNamespace(id=9, org_id=None, team_memberships=[team, gone])

    assert kb_principal(user) == Principal("9", None, frozenset({"3"}), True)


def test_kb_principal_refuses_a_user_with_no_id_instead_of_reading_as_anyone():
    with pytest.raises(ValueError):
        kb_principal({"role": "user"})


def test_a_missing_user_id_reads_as_system_scope_never_as_a_wider_scope():
    assert principal_for_identity(None) is SYSTEM_SCOPE
    assert principal_for_identity("") is SYSTEM_SCOPE
    assert principal_for_identity("A", "o1") == Principal("A", "o1", frozenset(), True)


def test_require_kb_principal_contrast_pair():
    assert require_kb_principal(SYSTEM_SCOPE) is SYSTEM_SCOPE
    assert require_kb_principal(kb_principal({"user_id": "A"})).user_id == "A"
    with pytest.raises(ValueError):
        require_kb_principal(None)
    with pytest.raises(TypeError):
        require_kb_principal("SYSTEM_SCOPE")
    with pytest.raises(TypeError):
        require_kb_principal({"user_id": "A"})


def test_system_scope_is_not_a_string_so_no_username_can_equal_it():
    assert not isinstance(SYSTEM_SCOPE, str)
    assert SYSTEM_SCOPE != "SYSTEM_SCOPE" and SYSTEM_SCOPE != repr(SYSTEM_SCOPE)
    assert repr(SYSTEM_SCOPE) == "SYSTEM_SCOPE"


@pytest.mark.asyncio
async def test_a_user_principal_keeps_own_system_and_group_facts_and_never_anothers_private():
    manager = KnowledgeOwnership(redis_client=object())
    user = Principal("A", None, frozenset({"g1"}), True)

    kept = await filter_for_principal([PRIVATE_OF_B, OWN, SYSTEM, GROUP], user, manager)

    assert kept == [OWN, SYSTEM, GROUP]


@pytest.mark.asyncio
async def test_system_scope_keeps_non_private_facts_only_and_needs_no_ownership_manager():
    kept = await filter_for_principal([PRIVATE_OF_B, OWN, SYSTEM, GROUP], SYSTEM_SCOPE, None)

    assert kept == [SYSTEM]


@pytest.mark.asyncio
async def test_a_user_principal_with_no_ownership_manager_reads_nothing():
    """Fail closed: no manager means no access decision can be made."""
    assert await filter_for_principal([OWN, SYSTEM], kb_principal({"user_id": "A"}), None) == []


@pytest.mark.asyncio
async def test_the_filter_refuses_a_missing_principal():
    manager = AsyncMock()
    with pytest.raises(ValueError):
        await filter_for_principal([OWN], None, manager)
    manager.check_access.assert_not_called()
