# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #18825: memory-graph reads and writes are owner-scoped (query layer, writes, traversal).

Before this, any authenticated user could read every other user's conversation summaries, session
titles and usernames: ``search_entities`` / ``get_entities_as_of`` / ``get_related_entities`` /
``find_path`` took no owner at all, and the scan fallback also dropped the tag filter.

These tests drive the real query / traversal code over an in-memory Redis double, so the assertion is
"user A cannot see user B's entity", not "a parameter was forwarded". The routes are in
``test_owner_scope_routes_18825.py``; the doubles in ``_owner_scope_doubles.py``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.entities import EntityOperationsMixin
from autobot_memory_graph.owner_scope import (
    SHARED_OWNER_ID,
    UNSCOPED_ALL_USERS,
    OwnerScope,
    OwnerScopeRequired,
    entity_visible,
    redis_owner_clause,
)
from autobot_memory_graph.property_graph_mixin import PropertyGraphMixin
from autobot_shared.user_management.base_service import TenantContext
from chat_history.graph_owner import session_owner_scope
from tests.memory_graph._graph_test_doubles import MixinHarness, make_graph
from tests.memory_graph._owner_scope_doubles import (
    ALICE,
    ALICE_CONV,
    ALICE_ID,
    ALL_DOCS,
    BOB,
    BOB_CONV,
    BOB_ID,
    LEGACY_DOC,
    SHARED_DOC,
    QueryHost,
    TraversalHost,
    _doc,
    _names,
)

# ---------------------------------------------------------------------------
# The scope type itself
# ---------------------------------------------------------------------------


class TestEntityVisibility:
    def test_owner_sees_own_entity_and_not_anothers(self):
        assert entity_visible(ALICE_CONV, ALICE)
        assert not entity_visible(BOB_CONV, ALICE)

    def test_shared_entities_are_readable_by_everyone(self):
        assert entity_visible(SHARED_DOC, ALICE) and entity_visible(SHARED_DOC, BOB)

    def test_ownerless_entities_fail_closed(self):
        assert not entity_visible(LEGACY_DOC, ALICE)

    def test_a_different_org_hides_the_entity_even_for_the_same_user(self):
        in_org = _doc("c-org", "Conversation org", ALICE_ID, org="org-1")
        assert entity_visible(in_org, OwnerScope.for_user(ALICE_ID, "org-1"))
        assert not entity_visible(in_org, OwnerScope.for_user(ALICE_ID, "org-2"))
        assert not entity_visible(in_org, ALICE)

    def test_the_unscoped_sentinel_sees_everything_including_ownerless(self):
        assert entity_visible(LEGACY_DOC, UNSCOPED_ALL_USERS) and entity_visible(BOB_CONV, UNSCOPED_ALL_USERS)

    @pytest.mark.parametrize("bad", [None, "", ALICE_ID, "__unscoped_all_users__", {}])
    def test_anything_else_is_refused_not_treated_as_unscoped(self, bad):
        with pytest.raises(OwnerScopeRequired):
            entity_visible(ALICE_CONV, bad)

    def test_a_user_id_cannot_collide_with_a_reserved_owner(self):
        with pytest.raises(OwnerScopeRequired):
            OwnerScope.for_user(SHARED_OWNER_ID)

    def test_the_redis_clause_filters_on_the_owner_tag_and_is_empty_when_unscoped(self):
        clause = redis_owner_clause(ALICE)
        assert "@owner_user_id:{" in clause and "__shared__" in clause
        assert "@owner_org_id:{" in clause and "__no_org__" in clause
        assert redis_owner_clause(UNSCOPED_ALL_USERS) == ""
        with pytest.raises(OwnerScopeRequired):
            redis_owner_clause(None)

    def test_scope_comes_from_the_authenticated_principal_dict(self):
        scope = OwnerScope.from_auth_user({"user_id": "u-1", "username": "alice", "org_id": "o"})
        assert (scope.user_id, scope.org_id) == ("u-1", "o")
        assert OwnerScope.from_auth_user({"username": "alice"}).user_id == "alice"
        with pytest.raises(OwnerScopeRequired):
            OwnerScope.from_auth_user({})

    def test_a_tenant_without_a_user_is_refused(self):
        with pytest.raises(OwnerScopeRequired):
            OwnerScope.from_tenant(TenantContext())


# ---------------------------------------------------------------------------
# search_entities / _fallback_search / get_entities_as_of
# ---------------------------------------------------------------------------


class TestSearchIsOwnerScoped:
    @pytest.mark.asyncio
    async def test_user_a_cannot_see_user_b_conversation_via_the_scan_fallback(self):
        host = QueryHost(ALL_DOCS, search_down=True)

        found = await host.search_entities(query="*", tags=["conversation"], limit=500, owner=ALICE)

        assert _names(found) == {"Conversation alice", "Conversation shared"}

    @pytest.mark.asyncio
    async def test_user_a_cannot_see_user_b_conversation_via_redisearch(self):
        """Even if the index filter is absent or stale, the post-filter holds."""
        host = QueryHost(ALL_DOCS, search_down=False)

        found = await host.search_entities(query="*", limit=500, owner=ALICE)

        assert "Conversation bob" not in _names(found) and "Note bob" not in _names(found)
        assert "Conversation alice" in _names(found)
        sent = " ".join(str(a) for a in host.redis_client.commands[0])
        assert "@owner_user_id:{" in sent  # the owner filter is part of the index query too

    @pytest.mark.asyncio
    async def test_the_fallback_keeps_the_tag_filter(self):
        """It used to drop ``tags`` and turn any collection id into a graph-wide substring search."""
        host = QueryHost(ALL_DOCS, search_down=True)

        found = await host.search_entities(query="*", tags=["conversation"], limit=500, owner=UNSCOPED_ALL_USERS)

        assert "Note alice" not in _names(found) and "Note bob" not in _names(found)
        assert {"Conversation alice", "Conversation bob"} <= _names(found)

    @pytest.mark.asyncio
    async def test_the_fallback_keeps_the_owner_filter_alongside_the_tag_filter(self):
        host = QueryHost(ALL_DOCS, search_down=True)

        found = await host._fallback_search("*", None, 500, owner=ALICE, tags=["other"])

        assert _names(found) == {"Note alice"}

    @pytest.mark.asyncio
    async def test_ownerless_legacy_entities_are_invisible_to_scoped_reads(self):
        host = QueryHost(ALL_DOCS, search_down=True)

        found = await host.search_entities(query="old", limit=50, owner=ALICE)

        assert found == []

    @pytest.mark.asyncio
    async def test_omitting_the_scope_fails_closed_instead_of_reading_everything(self):
        host = QueryHost(ALL_DOCS)

        with pytest.raises(TypeError):
            await host.search_entities(query="*")  # required keyword
        with pytest.raises(OwnerScopeRequired):
            await host.search_entities(query="*", owner=None)
        with pytest.raises(OwnerScopeRequired):
            await host._fallback_search("*", None, 10, owner=None)
        with pytest.raises(OwnerScopeRequired):
            await host.get_entities_as_of("conversation", "2999-01-01T00:00:00+00:00", owner=None)

    @pytest.mark.asyncio
    async def test_get_entities_as_of_is_owner_scoped(self):
        host = QueryHost(ALL_DOCS)

        mine = await host.get_entities_as_of("conversation", "2999-01-01T00:00:00+00:00", owner=ALICE)
        everyone = await host.get_entities_as_of("conversation", "2999-01-01T00:00:00+00:00", owner=UNSCOPED_ALL_USERS)

        assert _names(mine) == {"Conversation alice", "Conversation shared"}
        assert "Conversation bob" in _names(everyone)


# ---------------------------------------------------------------------------
# Writes stamp an owner
# ---------------------------------------------------------------------------


class WriteHost(EntityOperationsMixin):
    def __init__(self):
        self.redis_client = MagicMock()
        self.redis_client.json.return_value.set = AsyncMock()
        self.knowledge_base = None

    def ensure_initialized(self):
        return None


class TestWritesStampTheOwner:
    @pytest.mark.asyncio
    async def test_create_entity_records_owner_user_and_org_and_created_by(self):
        host = WriteHost()

        entity = await host.create_entity("TASK", "T", ["o"], owner=OwnerScope.for_user(ALICE_ID, "org-1"))

        assert entity["owner_user_id"] == ALICE_ID and entity["owner_org_id"] == "org-1"
        assert entity["metadata"]["created_by"] == ALICE_ID  # no longer overwritten with "autobot"
        stored = host.redis_client.json.return_value.set.await_args.args[2]
        assert stored["owner_user_id"] == ALICE_ID

    @pytest.mark.asyncio
    async def test_create_entity_without_an_owner_is_refused(self):
        host = WriteHost()

        with pytest.raises(TypeError):
            await host.create_entity("TASK", "T", ["o"])
        with pytest.raises(OwnerScopeRequired):
            await host.create_entity("TASK", "T", ["o"], owner=UNSCOPED_ALL_USERS)
        with pytest.raises(OwnerScopeRequired):
            await host.create_entity("TASK", "T", ["o"], owner=None)

    @pytest.mark.asyncio
    async def test_platform_entities_are_stamped_system_and_hidden_from_users(self):
        entity = await WriteHost().create_entity("TASK", "T", ["o"], owner=OwnerScope.system())

        assert not entity_visible(entity, ALICE)
        assert entity_visible(entity, UNSCOPED_ALL_USERS)

    @pytest.mark.asyncio
    async def test_get_or_create_never_hands_back_another_users_entity(self):
        graph = AutoBotMemoryGraph()
        graph._initialized = True
        graph.knowledge_base = None
        redis = MagicMock()
        redis.get = AsyncMock(return_value=b"c-bob")
        redis.json.return_value.get = AsyncMock(return_value=BOB_CONV)
        graph.redis_client = redis

        with pytest.raises(PermissionError):
            await graph.get_or_create_entity("CONVERSATION", "Conversation bob", [], owner=ALICE)
        entity, created = await graph.get_or_create_entity("CONVERSATION", "Conversation bob", [], owner=BOB)
        assert created is False and entity["id"] == "c-bob"

    def test_session_owner_scope_uses_the_stamped_identity_and_never_fails_open(self):
        assert session_owner_scope({"user_id": ALICE_ID, "org_id": "o"}) == OwnerScope.for_user(ALICE_ID, "o")
        assert session_owner_scope({"owner": "alice"}) == OwnerScope.for_user("alice")
        assert session_owner_scope(None) == OwnerScope.system()  # create-on-missing keeps an owner
        assert not entity_visible(_doc("c", "Conversation x", OwnerScope.system().user_id), ALICE)


# ---------------------------------------------------------------------------
# Traversal drops non-owned hops
# ---------------------------------------------------------------------------


class TestTraversalDropsForeignHops:
    @pytest.mark.asyncio
    async def test_related_entities_do_not_cross_another_owners_node(self):
        related = await TraversalHost().get_related_entities("A", direction="outgoing", max_depth=3, owner=ALICE)

        assert related == []  # X is bob's; C is only reachable through X

    @pytest.mark.asyncio
    async def test_the_unscoped_sentinel_still_walks_the_whole_chain(self):
        related = await TraversalHost().get_related_entities(
            "A", direction="outgoing", max_depth=3, owner=UNSCOPED_ALL_USERS
        )

        assert [r["entity"]["id"] for r in related] == ["x", "c"]

    @pytest.mark.asyncio
    async def test_a_start_entity_the_caller_does_not_own_resolves_to_nothing(self):
        assert await TraversalHost().get_related_entities("X", direction="both", owner=ALICE) == []

    @pytest.mark.asyncio
    async def test_omitting_the_scope_fails_closed(self):
        with pytest.raises(OwnerScopeRequired):
            await TraversalHost().get_related_entities("A", owner=None)

    @pytest.mark.asyncio
    async def test_find_path_never_runs_through_a_node_the_caller_cannot_read(self):
        graph = make_graph()
        entities = {
            "A": _doc("a", "A", ALICE_ID, entity_type="note"),
            "X": _doc("x", "X", BOB_ID, entity_type="note"),
            "C": _doc("c", "C", ALICE_ID, entity_type="note"),
        }
        for ent in entities.values():
            await graph.add_node(ent["id"], {"name": ent["name"], "type": ent["type"]})
        await graph.add_edge("a", "x", "CAUSED")
        await graph.add_edge("x", "c", "CAUSED")
        harness = MixinHarness(graph, entities)
        assert PropertyGraphMixin in type(harness).__mro__

        scoped = await harness.find_path("A", "C", owner=ALICE)
        unscoped = await harness.find_path("A", "C", owner=UNSCOPED_ALL_USERS)

        assert scoped["found"] is False and scoped["reason"] == "no_path"
        assert unscoped["found"] is True and unscoped["hops"] == 2

    @pytest.mark.asyncio
    async def test_find_path_to_an_entity_the_caller_does_not_own_reports_it_missing(self):
        graph = make_graph()
        entities = {"A": _doc("a", "A", ALICE_ID), "X": _doc("x", "X", BOB_ID)}
        harness = MixinHarness(graph, entities)

        result = await harness.find_path("A", "X", owner=ALICE)

        assert result["reason"] == "entity_not_found" and result["missing_entities"] == ["X"]
