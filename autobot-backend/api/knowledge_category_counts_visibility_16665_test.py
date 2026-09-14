# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""_get_or_compute_category_counts caches one count per category, shared by every
caller (#16665). A private fact must never inflate that shared count -- otherwise
one user's private fact count leaks to every other authenticated user through the
same cache key.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.knowledge_category_counts import (
    _get_or_compute_category_counts,
    _visible_to_every_authenticated_user,
)
from knowledge_categories import KnowledgeCategory, get_category_for_source


def test_private_fact_is_not_visible_to_every_authenticated_user():
    assert not _visible_to_every_authenticated_user({"metadata": {"owner_id": "u1", "visibility": "private"}})


def test_system_visibility_fact_is_visible_to_every_authenticated_user():
    assert _visible_to_every_authenticated_user({"metadata": {"visibility": "system"}})


def test_autobot_access_level_fact_is_visible_regardless_of_visibility():
    assert _visible_to_every_authenticated_user({"metadata": {"access_level": "autobot", "visibility": "private"}})


def test_fact_with_no_metadata_defaults_closed():
    assert not _visible_to_every_authenticated_user({})


@pytest.mark.asyncio
async def test_a_private_fact_does_not_change_the_cached_public_count():
    """Regression test for the coordinator-flagged side channel: a global,
    1h-cached category count must not vary with who happens to trigger the
    cache-miss recompute."""
    public_fact = {
        "fact_id": "f1",
        "content": "public",
        "metadata": {"source": "system_docs", "visibility": "system"},
    }
    private_fact = {
        "fact_id": "f2",
        "content": "secret",
        "metadata": {"owner_id": "u1", "source": "system_docs", "visibility": "private"},
    }

    kb = MagicMock()
    redis_mock = MagicMock()
    redis_mock.mget = AsyncMock(return_value=[None, None, None])
    redis_mock.set = AsyncMock()
    kb.redis = MagicMock(return_value=redis_mock)
    kb.get_all_facts = AsyncMock(return_value=[public_fact, private_fact])

    cache_keys = {cat: f"cache:{cat}" for cat in KnowledgeCategory}
    counts = {cat: 0 for cat in KnowledgeCategory}

    await _get_or_compute_category_counts(kb, cache_keys, get_category_for_source, counts)

    expected_category = get_category_for_source("system_docs")
    assert counts[expected_category] == 1, f"private fact must not be counted in the shared cache entry: {counts}"
