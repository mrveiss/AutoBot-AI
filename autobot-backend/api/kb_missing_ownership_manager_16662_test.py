# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A missing ownership manager fails closed in every ownership-aware route (#16662).

Without the ownership manager no access decision can be made, so each route must answer
503 rather than read facts unfiltered. The helper side is pinned in
``knowledge/search_filters_16662_test.py``. These tests drive the routes themselves, with
a knowledge base whose ``ownership_manager`` is ``None``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

_USER = {"user_id": "u1", "username": "u1", "role": "user"}


def _kb_without_manager():
    kb = MagicMock()
    kb.ownership_manager = None
    return kb


async def _expect_503(module, call):
    with patch.object(module, "get_or_create_knowledge_base", AsyncMock(return_value=_kb_without_manager())):
        with pytest.raises(HTTPException) as err:
            await call()
    assert err.value.status_code == 503


def _request():
    request = MagicMock()
    request.state.user = _USER
    return request


@pytest.mark.asyncio
async def test_my_facts_route_refuses_without_the_manager():
    from api import knowledge_ownership as mod

    await _expect_503(mod, lambda: mod.get_my_facts(_request(), limit=10, offset=0, include_shared=True, _={}))


@pytest.mark.asyncio
async def test_shared_with_me_route_refuses_without_the_manager():
    from api import knowledge_ownership as mod

    await _expect_503(mod, lambda: mod.get_shared_facts(_request(), limit=10, offset=0, _={}))


@pytest.mark.asyncio
async def test_collaboration_permissions_route_refuses_without_the_manager():
    from api import knowledge_collaboration as mod

    body = SimpleNamespace(visibility="private", organization_id=None, group_ids=[])
    await _expect_503(
        mod,
        lambda: mod.update_knowledge_permissions(
            fact_id="f1", permissions_request=body, request=_request(), current_user=_USER
        ),
    )


@pytest.mark.asyncio
async def test_collaboration_share_route_refuses_without_the_manager():
    from api import knowledge_collaboration as mod

    body = SimpleNamespace(user_ids=["u2"], group_ids=[])
    await _expect_503(
        mod,
        lambda: mod.share_knowledge(fact_id="f1", share_request=body, request=_request(), current_user=_USER),
    )


@pytest.mark.asyncio
async def test_collaboration_access_info_route_refuses_without_the_manager():
    from api import knowledge_collaboration as mod

    await _expect_503(mod, lambda: mod.get_knowledge_access_info(fact_id="f1", request=_request(), current_user=_USER))


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["scoped_search", "scoped_rag_search"])
async def test_scoped_search_routes_refuse_without_the_manager(route):
    from api import knowledge_search_scoped as mod

    body = SimpleNamespace(query="q", top_k=5, limit=5, category=None, tags=None)
    await _expect_503(mod, lambda: getattr(mod, route)(search_request=body, request=_request(), current_user=_USER))
