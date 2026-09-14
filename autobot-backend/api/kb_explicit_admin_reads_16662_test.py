# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The explicit read APIs let an admin read any fact; everyone else keeps their scope (#16662).

Owner decision on #16654: an admin can read any fact through the explicit search and read
APIs, and an admin's chat gets no bypass. These tests use the real ``KnowledgeOwnership``
access check. ``repo_tests/kb_admin_read_bypass_guard_test.py`` pins that nothing else passes
the admin input.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from knowledge.ownership import KnowledgeOwnership

_PRIVATE = {"owner_id": "u1", "visibility": "private", "access_level": "user"}


def _kb(get_fact=None, stored_metadata=None):
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.get_fact = MagicMock(return_value=get_fact)
    redis = MagicMock()
    redis.hget = AsyncMock(return_value=json.dumps(stored_metadata) if stored_metadata else None)
    kb.redis.return_value = redis
    return kb


@pytest.mark.asyncio
async def test_the_admin_ownership_routes_read_another_users_private_fact():
    from api.knowledge_ownership import _get_fact_with_ownership

    fact = {"metadata": dict(_PRIVATE)}
    assert await _get_fact_with_ownership(_kb(get_fact=fact), "f1", "admin-1") == fact


async def _access_info(role: str):
    from api import knowledge_collaboration as mod

    kb = _kb(stored_metadata=dict(_PRIVATE))
    with patch.object(mod, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await mod.get_knowledge_access_info(
            fact_id="f1", request=MagicMock(), current_user={"user_id": "other", "role": role}
        )


@pytest.mark.asyncio
async def test_access_info_lets_an_admin_read_another_users_private_fact():
    assert (await _access_info("admin"))["fact_id"] == "f1"


@pytest.mark.asyncio
async def test_access_info_refuses_a_non_admin_the_same_fact():
    with pytest.raises(HTTPException) as err:
        await _access_info("user")
    assert err.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("is_admin", "narrowed"), [(True, False), (False, True)])
async def test_scoped_search_narrows_the_query_for_everyone_but_an_admin(is_admin, narrowed):
    from api.knowledge_search_scoped import _execute_permission_filtered_search

    kb = MagicMock()
    kb.search = AsyncMock(return_value=[])
    request = SimpleNamespace(query="q", top_k=5)

    await _execute_permission_filtered_search(kb, request, "other", None, [], is_admin=is_admin)

    assert (kb.search.await_args.kwargs["filters"] is not None) is narrowed


@pytest.mark.asyncio
@pytest.mark.parametrize(("is_admin", "kept"), [(True, 1), (False, 0)])
async def test_scoped_search_keeps_another_users_private_fact_only_for_an_admin(is_admin, kept):
    from api.knowledge_search_scoped import _build_scoped_search_response

    results = [{"id": "f1", "content": "c", "metadata": dict(_PRIVATE)}]
    request = SimpleNamespace(query="q", mode="auto")

    response = await _build_scoped_search_response(
        results, request, "other", None, [], KnowledgeOwnership(redis_client=object()), is_admin=is_admin
    )

    assert response["total_results"] == kept
