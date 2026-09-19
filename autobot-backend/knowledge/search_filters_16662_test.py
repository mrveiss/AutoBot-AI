# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The permission helpers fail closed, and the pre-filter admits everything
check_access would allow (#16662)."""

import pytest

from knowledge.ownership import KnowledgeOwnership
from knowledge.search_filters import (
    augment_search_request_with_permissions,
    build_chromadb_permission_filter,
    filter_search_results_by_permission,
)

USER = "user-1"
ORG = "org-1"
GROUP = "grp-1"


def _matches(where: dict, meta: dict) -> bool:
    """Evaluate the subset of ChromaDB's where syntax the pre-filter uses."""
    if "$or" in where:
        return any(_matches(clause, meta) for clause in where["$or"])
    if "$and" in where:
        return all(_matches(clause, meta) for clause in where["$and"])
    ((key, cond),) = where.items()
    if isinstance(cond, dict):
        ((op, operand),) = cond.items()
        if op == "$in":
            return meta.get(key) in operand
        raise AssertionError(f"unsupported operator {op}")
    return meta.get(key) == cond


def _fact(visibility, access_level="user", owner="someone-else", **extra) -> dict:
    return {"owner_id": owner, "visibility": visibility, "access_level": access_level, **extra}


# Every fact here is one check_access lets USER read; the pre-filter must admit each.
_READABLE = [
    _fact("private", owner=USER),
    _fact("system"),
    _fact("public"),
    _fact("organization", organization_id=ORG),
    _fact("group", group_ids=GROUP),
    _fact("shared", shared_with=f"{USER}, other"),
    _fact("private", access_level="general"),
    _fact("private", access_level="autobot"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("meta", _READABLE, ids=lambda m: f"{m['visibility']}/{m['access_level']}")
async def test_the_pre_filter_admits_every_fact_check_access_allows(meta):
    mgr = KnowledgeOwnership(redis_client=object())
    assert await mgr.check_access("f", USER, meta, user_org_id=ORG, user_group_ids=[GROUP]) is True
    where = await build_chromadb_permission_filter(USER, user_org_id=ORG, user_group_ids=[GROUP])
    assert _matches(where, meta), "a pre-filter narrower than check_access drops a readable fact"


@pytest.mark.asyncio
async def test_no_ownership_manager_means_no_results():
    results = [{"id": "f", "metadata": _fact("private")}]
    assert await filter_search_results_by_permission(results, USER, ownership_manager=None) == []


@pytest.mark.asyncio
async def test_an_admin_read_is_not_narrowed_and_passes_the_admin_input_through():
    original = {"collection": {"$ne": "research"}}
    assert await augment_search_request_with_permissions("q", "admin-1", original_where=original, is_admin=True) == (
        original
    )
    mgr = KnowledgeOwnership(redis_client=object())
    results = [{"id": "f", "metadata": _fact("private")}]
    kept = await filter_search_results_by_permission(results, "admin-1", ownership_manager=mgr, is_admin=True)
    assert kept == results
    assert await filter_search_results_by_permission(results, "admin-1", ownership_manager=mgr) == []
