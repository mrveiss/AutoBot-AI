# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The semantic and topic retrieval caches are partitioned by visibility scope (#16664).

A cached RAG result was keyed by the query alone, so user A's cached private result was served to
user B. Both caches now store the caller's scope key in the entry metadata and look up only inside
it. The fake collection honours the ``where`` the cache sends, so a lookup that forgot it would hit.
"""

import pytest

from services.rag_visibility import scope_key
from services.topic_retrieval_cache import CachedChunk
from tests.fixtures.rag_cache_fakes import make_semantic_cache, make_topic_cache

VECTOR = [0.1, 0.2, 0.3]
SCOPE_A = "scope-of-a"
SCOPE_B = "scope-of-b"


@pytest.mark.asyncio
async def test_a_semantic_entry_is_a_hit_in_its_own_scope_and_a_miss_in_another():
    cache = make_semantic_cache()
    assert await cache.store("q", "A's private answer", "rag", embedding=VECTOR, scope=SCOPE_A)

    own = await cache.lookup("q", embedding=VECTOR, scope=SCOPE_A)
    other = await cache.lookup("q", embedding=VECTOR, scope=SCOPE_B)

    assert own is not None and own.response_text == "A's private answer"
    assert other is None, "B must not be served the entry A stored for the same query"


@pytest.mark.asyncio
async def test_the_semantic_lookup_always_sends_the_scope_to_chromadb():
    cache = make_semantic_cache()
    collection = cache._collection
    await cache.lookup("q", embedding=VECTOR, scope=SCOPE_B)
    assert collection.where_seen == [{"scope": SCOPE_B}]


@pytest.mark.asyncio
async def test_the_semantic_entry_keeps_the_scope_in_its_metadata():
    cache = make_semantic_cache()
    collection = cache._collection
    await cache.store("q", "answer", "rag", embedding=VECTOR, scope=SCOPE_A)
    assert collection.rows[0][1]["scope"] == SCOPE_A


@pytest.mark.asyncio
async def test_a_topic_is_a_hit_in_its_own_scope_and_a_miss_in_another():
    cache = make_topic_cache()
    chunk = CachedChunk(content="A's private chunk", metadata={"owner_id": "A"}, score=0.9)
    assert await cache.store([VECTOR], [chunk], scope=SCOPE_A)

    own = await cache.lookup(VECTOR, scope=SCOPE_A)
    other = await cache.lookup(VECTOR, scope=SCOPE_B)

    assert own is not None and own[0].content == "A's private chunk"
    assert other is None, "B must not be served the topic A stored"


@pytest.mark.asyncio
async def test_the_topic_lookup_always_sends_the_scope_to_chromadb():
    cache = make_topic_cache()
    collection = cache._collection
    await cache.lookup(VECTOR, scope=SCOPE_B)
    assert collection.where_seen == [{"scope": SCOPE_B}]


def test_scope_and_lookup_have_no_default_so_a_caller_cannot_forget_it():
    """Contrast: omitting ``scope`` is a TypeError, not a global lookup."""
    cache = make_semantic_cache()
    with pytest.raises(TypeError):
        cache.lookup("q", embedding=VECTOR)  # the call itself raises, before any await
    with pytest.raises(TypeError):
        make_topic_cache().lookup(VECTOR)


def test_the_scope_key_separates_user_org_groups_and_epoch():
    from autobot_shared.scoping import Principal

    def key(user="a", org=None, groups=(), epoch="0"):
        return scope_key(Principal(user, org, frozenset(groups), True), epoch)

    base = key()
    assert key() == base and len(base) == 32
    assert len({base, key(user="b"), key(org="o1"), key(groups=("g1",)), key(epoch="1")}) == 5
    assert key(groups=("g1", "g2")) == key(groups=("g2", "g1")), "group order must not split a scope"


def test_system_scope_has_its_own_readable_key_per_epoch():
    from knowledge.search_filters import SYSTEM_SCOPE

    assert scope_key(SYSTEM_SCOPE, "7") == "system|7"
    assert scope_key(SYSTEM_SCOPE, "7") != scope_key(SYSTEM_SCOPE, "8")
