# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The 11 fact-returning knowledge-CRUD routes flagged by #16665's T3 allowlist
(repo_tests/kb_read_visibility_allowlist.py) as SCOPED/ADMIN_ONLY, not filtered,
because they already require Depends(check_admin_permission). This is the
regression test that keeps that claim true: each route's resolved dependant
tree must still reach check_admin_permission, or the allowlist entry is a lie.

Uses the #15737 method (api/settings_route_posture_test.py, api/user_management/
user_management_route_posture_test.py): walk the real Dependant tree FastAPI
resolves, comparing dependency callables by identity. The walk is copied rather
than imported -- importing a sweep module would pull in its whole router set.
"""

from api.knowledge import router as knowledge_router
from api.knowledge import search_man_pages
from api.knowledge_categories import get_facts_in_category
from api.knowledge_categories import router as knowledge_categories_router
from api.knowledge_collections import export_collection, get_facts_in_collection
from api.knowledge_collections import router as knowledge_collections_router
from api.knowledge_metadata import router as knowledge_metadata_router
from api.knowledge_metadata import search_by_metadata
from api.knowledge_relations import get_fact_relations, hybrid_search
from api.knowledge_relations import router as knowledge_relations_router
from api.knowledge_relations import traverse_relations
from api.knowledge_tags import get_facts_by_tag
from api.knowledge_tags import router as knowledge_tags_router
from api.knowledge_tags import search_facts_by_tags
from api.knowledge_verification import list_pending_verification
from api.knowledge_verification import router as knowledge_verification_router
from auth_middleware import check_admin_permission
from autobot_shared.api_routing.router_routes import effective_routes


def _dependency_calls(dependant) -> list:
    """Every dependency callable reachable from *dependant*, at any depth."""
    calls: list = []
    stack = [dependant]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        for dep in getattr(node, "dependencies", None) or ():
            call = getattr(dep, "call", None)
            if call is not None:
                calls.append(call)
            stack.append(dep)
    return calls


def _is_admin_gated(router, endpoint) -> bool:
    for mounted in effective_routes(router):
        if getattr(mounted.route, "endpoint", None) is endpoint:
            return check_admin_permission in _dependency_calls(mounted.route.dependant)
    raise AssertionError(f"{endpoint!r} is not a mounted route on {router!r}")


def test_search_man_pages_is_admin_gated():
    assert _is_admin_gated(knowledge_router, search_man_pages)


def test_get_facts_in_category_is_admin_gated():
    assert _is_admin_gated(knowledge_categories_router, get_facts_in_category)


def test_export_collection_is_admin_gated():
    assert _is_admin_gated(knowledge_collections_router, export_collection)


def test_get_facts_in_collection_is_admin_gated():
    assert _is_admin_gated(knowledge_collections_router, get_facts_in_collection)


def test_search_by_metadata_is_admin_gated():
    assert _is_admin_gated(knowledge_metadata_router, search_by_metadata)


def test_get_fact_relations_is_admin_gated():
    assert _is_admin_gated(knowledge_relations_router, get_fact_relations)


def test_hybrid_search_is_admin_gated():
    assert _is_admin_gated(knowledge_relations_router, hybrid_search)


def test_traverse_relations_is_admin_gated():
    assert _is_admin_gated(knowledge_relations_router, traverse_relations)


def test_get_facts_by_tag_is_admin_gated():
    assert _is_admin_gated(knowledge_tags_router, get_facts_by_tag)


def test_search_facts_by_tags_is_admin_gated():
    assert _is_admin_gated(knowledge_tags_router, search_facts_by_tags)


def test_list_pending_verification_is_admin_gated():
    assert _is_admin_gated(knowledge_verification_router, list_pending_verification)
