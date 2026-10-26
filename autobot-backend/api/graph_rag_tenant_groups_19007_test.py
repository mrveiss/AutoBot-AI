# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A tenant-context route sees team-shared facts for team members only (#19007).

``POST /graph-rag/search`` authorises through ``get_tenant_context``. Its KB principal now carries
the caller's teams from the canonical team service, so user A (in team T) sees a fact shared to T and
user B (not in T) does not. The route function is called directly; the graph service stands in only
to apply the canonical ``filter_for_principal`` over the real ownership check to the principal the
route built. A failed membership lookup reads with no groups, and is logged and not cached.
"""

from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from api.graph_rag import graph_rag_search  # noqa: E402
from autobot_shared.user_management.base_service import TenantContext  # noqa: E402
from knowledge import tenant_groups  # noqa: E402
from knowledge.ownership import KnowledgeOwnership  # noqa: E402
from knowledge.search_filters import filter_for_principal, kb_principal_from_tenant  # noqa: E402

TEAM_T = uuid.UUID("77777777-7777-7777-7777-777777777777")
USER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_TEAMS = {USER_A: [SimpleNamespace(id=TEAM_T)], USER_B: []}
_GET_USER_TEAMS = "autobot_shared.user_management.team_service.TeamService.get_user_teams"
_TEAM_FACT = {"id": "f-team", "metadata": {"owner_id": "carol", "visibility": "group", "group_ids": [str(TEAM_T)]}}


@pytest.fixture(autouse=True)
def _fresh_cache():
    tenant_groups._cache.clear()
    yield
    tenant_groups._cache.clear()


class _GraphService:
    """Applies the canonical KB result filter to the principal the route passes, and records it."""

    def __init__(self) -> None:
        self.visible: list = []

    async def graph_aware_search(self, *, principal, **_kwargs):
        self.visible = await filter_for_principal([_TEAM_FACT], principal, KnowledgeOwnership(MagicMock()))
        return [], SimpleNamespace(total_time=0.0, to_response_dict=dict)


async def _search_as(user_id: uuid.UUID) -> list:
    service = _GraphService()
    teams = AsyncMock(side_effect=lambda uid: _TEAMS[uid])
    with patch(_GET_USER_TEAMS, teams):
        response = await graph_rag_search(
            search_request=SimpleNamespace(
                query="q", start_entity=None, max_depth=1, max_results=5, enable_reranking=False, timeout=None
            ),
            service=service,
            tenant=TenantContext(user_id=user_id),
            session=MagicMock(),
        )
    assert response.status_code == 200 and json.loads(response.body)["success"] is True
    return [fact["id"] for fact in service.visible]


@pytest.mark.asyncio
async def test_a_team_member_sees_the_fact_shared_to_the_team():
    assert await _search_as(USER_A) == ["f-team"]


@pytest.mark.asyncio
async def test_a_non_member_does_not_see_the_fact_shared_to_the_team():
    assert await _search_as(USER_B) == []


@pytest.mark.asyncio
async def test_a_failed_membership_lookup_reads_with_no_groups_logged_and_not_cached(caplog):
    tenant = TenantContext(user_id=USER_A)
    failing = AsyncMock(side_effect=RuntimeError("db down"))
    with patch(_GET_USER_TEAMS, failing), caplog.at_level(logging.WARNING):
        principal = await kb_principal_from_tenant(tenant, MagicMock())
    assert principal.group_ids == frozenset() and "reading with no groups" in caplog.text

    with patch(_GET_USER_TEAMS, AsyncMock(side_effect=lambda uid: _TEAMS[uid])):
        assert (await kb_principal_from_tenant(tenant, MagicMock())).group_ids == {str(TEAM_T)}


@pytest.mark.asyncio
async def test_memberships_are_cached_per_user():
    teams = AsyncMock(side_effect=lambda uid: _TEAMS[uid])
    with patch(_GET_USER_TEAMS, teams):
        for _ in range(3):
            await kb_principal_from_tenant(TenantContext(user_id=USER_A), MagicMock())
    assert teams.await_count == 1


@pytest.mark.asyncio
async def test_a_tenant_with_no_user_is_refused_before_any_lookup():
    teams = AsyncMock()
    with patch(_GET_USER_TEAMS, teams), pytest.raises(ValueError):
        await kb_principal_from_tenant(TenantContext(), MagicMock())
    teams.assert_not_awaited()
