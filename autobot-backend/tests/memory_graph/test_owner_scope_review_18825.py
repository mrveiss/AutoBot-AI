# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #18825 review follow-ups: fail-closed owner scope at the edges the first pass left open.

* ``OwnerScope.for_user(None)`` must not become the shared pseudo-user ``"None"``.
* The scan fallback and ``get_entities_as_of`` filter WHILE scanning (other owners' keys cannot starve a caller).
* The Redis conversation cache records and re-checks its owner.
* ``memory.update_graph`` writes under the session owner, never ``OwnerScope.system()``.
* Session metadata carries the AUTHENTICATED principal, never the request body's ``user_id``.
* ``shortest_path`` skips the per-hop read for nodes it has already visited.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_memory_graph.owner_scope import OwnerScope, OwnerScopeRequired
from chat_workflow.session_role import apply_auth_role, stamp_verified_identity
from chat_workflow.tiered_context_sources import resolve_owner_scope
from services.memory.redis_provider import RedisMemoryProvider
from tests.memory_graph._graph_test_doubles import make_graph
from tests.memory_graph._owner_scope_doubles import ALICE, ALICE_ID, BOB_ID, QueryHost, _doc


class TestForUserRejectsMissingIds:
    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_for_user_rejects_none_and_blank_before_str(self, bad):
        with pytest.raises(OwnerScopeRequired):
            OwnerScope.for_user(bad)

    def test_none_never_becomes_the_string_none(self):
        with pytest.raises(OwnerScopeRequired):
            OwnerScope.for_user(None, "org-1")


class TestScansFilterWhileScanning:
    @staticmethod
    def _docs(others, mine):
        bobs = [_doc(f"b{i}", f"Bob {i}", BOB_ID) for i in range(others)]
        alices = [_doc(f"a{i}", f"Alice {i}", ALICE_ID) for i in range(mine)]
        return bobs + alices  # the caller's entities sit AFTER the keyspace a capped scan would reach

    @pytest.mark.asyncio
    async def test_fallback_search_finds_limit_matches_past_other_owners_keys(self):
        host = QueryHost(self._docs(others=600, mine=3))

        found = await host._fallback_search("*", None, 3, owner=ALICE)

        assert sorted(e["name"] for e in found) == ["Alice 0", "Alice 1", "Alice 2"]

    @pytest.mark.asyncio
    async def test_fallback_search_stops_at_limit(self):
        host = QueryHost(self._docs(others=0, mine=120))

        found = await host._fallback_search("*", None, 7, owner=ALICE)

        assert len(found) == 7

    @pytest.mark.asyncio
    async def test_get_entities_as_of_is_not_starved_by_other_owners_keys(self):
        host = QueryHost(self._docs(others=1200, mine=2))

        found = await host.get_entities_as_of("conversation", "2999-01-01T00:00:00+00:00", owner=ALICE)

        assert sorted(e["name"] for e in found) == ["Alice 0", "Alice 1"]


class TestScanBudget:
    """A scan-fallback call examines at most ``_SCAN_KEY_BUDGET`` keys, whatever the keyspace holds (#18825)."""

    BUDGET = 100

    @pytest.fixture(autouse=True)
    def _budget(self, monkeypatch):
        from autobot_memory_graph import queries

        monkeypatch.setattr(queries, "_SCAN_KEY_BUDGET", self.BUDGET)

    @staticmethod
    def _counting(host):
        seen = []
        original = host.redis_client.scan_iter

        async def counting(match=None):
            async for key in original(match=match):
                seen.append(key)
                yield key

        host.redis_client.scan_iter = counting
        return seen

    @pytest.mark.asyncio
    async def test_fallback_search_stops_at_the_budget_and_warns(self, caplog):
        host = QueryHost([_doc(f"b{i}", f"Bob {i}", BOB_ID) for i in range(1000)])
        seen = self._counting(host)

        with caplog.at_level("WARNING", logger="autobot_memory_graph.queries"):
            found = await host._fallback_search("*", None, 5, owner=ALICE)

        assert found == []
        assert len(seen) <= self.BUDGET + 1  # the one key that proved the budget was exceeded
        message = next(r.getMessage() for r in caplog.records if "scan budget exhausted" in r.getMessage())
        assert f"budget={self.BUDGET}" in message and f"examined={self.BUDGET}" in message
        assert "owner_kind=user" in message and BOB_ID not in message and ALICE_ID not in message

    @pytest.mark.asyncio
    async def test_a_match_inside_the_budget_is_found_past_many_foreign_entries(self, caplog):
        docs = [_doc(f"b{i}", f"Bob {i}", BOB_ID) for i in range(self.BUDGET - 10)]
        docs.append(_doc("a0", "Alice 0", ALICE_ID))
        host = QueryHost(docs + [_doc(f"c{i}", f"Bob late {i}", BOB_ID) for i in range(500)])

        with caplog.at_level("WARNING", logger="autobot_memory_graph.queries"):
            found = await host._fallback_search("*", None, 1, owner=ALICE)

        assert [e["name"] for e in found] == ["Alice 0"]
        assert not [r for r in caplog.records if "scan budget exhausted" in r.getMessage()]

    @pytest.mark.asyncio
    async def test_a_match_beyond_the_budget_is_not_reached(self):
        docs = [_doc(f"b{i}", f"Bob {i}", BOB_ID) for i in range(self.BUDGET + 50)] + [_doc("a0", "Alice 0", ALICE_ID)]

        found = await QueryHost(docs)._fallback_search("*", None, 1, owner=ALICE)

        assert found == []

    @pytest.mark.asyncio
    async def test_get_entities_as_of_respects_the_budget(self, caplog):
        host = QueryHost([_doc(f"b{i}", f"Bob {i}", BOB_ID) for i in range(1000)])
        seen = self._counting(host)

        with caplog.at_level("WARNING", logger="autobot_memory_graph.queries"):
            found = await host.get_entities_as_of("conversation", "2999-01-01T00:00:00+00:00", owner=ALICE)

        assert found == [] and len(seen) <= self.BUDGET + 1
        assert any("scan budget exhausted" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_get_entities_as_of_returns_matches_found_before_the_budget(self):
        docs = [_doc(f"a{i}", f"Alice {i}", ALICE_ID) for i in range(3)]
        docs += [_doc(f"b{i}", f"Bob {i}", BOB_ID) for i in range(500)]

        found = await QueryHost(docs).get_entities_as_of("conversation", "2999-01-01T00:00:00+00:00", owner=ALICE)

        assert sorted(e["name"] for e in found) == ["Alice 0", "Alice 1", "Alice 2"]


class _CacheRedis:
    def __init__(self):
        self.store = {}

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


def _provider():
    provider = RedisMemoryProvider()
    provider.redis = _CacheRedis()
    return provider


TURN = {"conversation_id": "c1", "timestamp": "t", "entity_updates": [{"name": "secret"}]}


class TestRedisConversationCacheFailsClosed:
    @pytest.mark.asyncio
    async def test_owner_reads_back_its_own_cache_without_the_owner_fields(self):
        provider = _provider()
        await provider.sync({**TURN, "user_id": ALICE_ID})

        got = await provider.prefetch({"conversation_id": "c1", "user_id": ALICE_ID})

        assert got["entity_updates"] == [{"name": "secret"}]
        assert not any(k.startswith("owner_") for k in got)

    @pytest.mark.asyncio
    async def test_another_user_reads_nothing_from_the_same_conversation_key(self):
        provider = _provider()
        await provider.sync({**TURN, "user_id": ALICE_ID})

        assert await provider.prefetch({"conversation_id": "c1", "user_id": BOB_ID}) == {}

    @pytest.mark.asyncio
    async def test_a_context_without_a_user_reads_nothing(self):
        provider = _provider()
        await provider.sync({**TURN, "user_id": ALICE_ID})

        assert await provider.prefetch({"conversation_id": "c1"}) == {}

    @pytest.mark.asyncio
    async def test_a_turn_without_a_user_is_not_cached(self):
        provider = _provider()

        await provider.sync(TURN)

        assert provider.redis.store == {}

    @pytest.mark.asyncio
    async def test_a_legacy_ownerless_cache_entry_is_invisible(self):
        provider = _provider()
        provider.redis.store["autobot:memory:cache:c1"] = json.dumps({"entity_updates": [1]})

        assert await provider.prefetch({"conversation_id": "c1", "user_id": ALICE_ID}) == {}

    @pytest.mark.asyncio
    async def test_get_entity_and_search_require_and_check_the_owner(self):
        provider = _provider()
        mine = {"id": "e1", **_doc("e1", "mine", ALICE_ID)}
        provider.redis.store["autobot:memory:entity:e1"] = json.dumps(mine)
        provider.redis.store[f"autobot:memory:search:{hash('q') % (10**8)}"] = json.dumps([mine])

        assert await provider.get_entity("e1") is None
        assert await provider.get_entity("e1", owner=OwnerScope.for_user(BOB_ID)) is None
        assert (await provider.get_entity("e1", owner=ALICE))["name"] == "mine"
        assert await provider.search("q", filters=None) == []
        assert await provider.search("q", filters={"user_id": BOB_ID}) == []
        assert len(await provider.search("q", filters={"user_id": ALICE_ID})) == 1

    @pytest.mark.asyncio
    async def test_update_entity_still_works_without_a_read_scope(self):
        provider = _provider()
        provider.redis.store["autobot:memory:entity:e1"] = json.dumps(_doc("e1", "mine", ALICE_ID))

        await provider.update_entity("e1", {"name": "renamed"})

        assert json.loads(provider.redis.store["autobot:memory:entity:e1"])["name"] == "renamed"


class TestUpdateGraphTaskWritesUnderTheSessionOwner:
    @staticmethod
    def _graph():
        from autobot_memory_graph import AutoBotMemoryGraph

        graph = MagicMock(spec=AutoBotMemoryGraph)
        graph.initialize = AsyncMock()
        graph.get_or_create_entity = AsyncMock(return_value=({"id": "e1"}, True))
        return graph

    @pytest.mark.asyncio
    async def test_entities_are_written_as_the_session_owner_not_the_system(self):
        import tasks.memory_tasks as mt

        graph = self._graph()
        with patch("autobot_memory_graph.AutoBotMemoryGraph", return_value=graph):
            await mt._async_update_graph("s1", [{"name": "N", "type": "t", "properties": {}}], [], ALICE_ID, "org-1")

        owner = graph.get_or_create_entity.await_args.kwargs["owner"]
        assert owner == OwnerScope.for_user(ALICE_ID, "org-1")
        assert owner != OwnerScope.system()

    @pytest.mark.asyncio
    async def test_no_user_id_writes_nothing_and_opens_no_connection(self):
        import tasks.memory_tasks as mt

        graph = self._graph()
        with patch("autobot_memory_graph.AutoBotMemoryGraph", return_value=graph) as ctor:
            with pytest.raises(OwnerScopeRequired):
                await mt._async_update_graph("s1", [{"name": "N", "type": "t"}], [], None)

        ctor.assert_not_called()
        graph.get_or_create_entity.assert_not_awaited()

    def test_the_task_rejects_an_ownerless_call_without_retrying(self):
        import tasks.memory_tasks as mt

        def _raise(coro):
            coro.close()
            raise OwnerScopeRequired("no owner")

        with patch.object(mt, "run_or_schedule", side_effect=_raise):
            result = mt.update_graph_task.run("s1", [], [], None, None)

        assert result["status"] == "rejected" and result["entities_written"] == 0


class TestSessionOwnerIsTheAuthenticatedPrincipal:
    def test_a_client_supplied_user_id_never_becomes_the_owner_scope(self):
        context = apply_auth_role(
            {"user_id": BOB_ID, "org_id": "evil"}, "user", {"user_id": ALICE_ID, "org_id": "org-1"}
        )
        metadata = {}

        stamp_verified_identity(metadata, context)

        scope = resolve_owner_scope(SimpleNamespace(metadata=metadata))
        assert scope == OwnerScope.for_user(ALICE_ID, "org-1")

    def test_an_unauthenticated_turn_clears_the_previous_identity(self):
        metadata = {"user_id": ALICE_ID, "org_id": "org-1"}

        stamp_verified_identity(metadata, apply_auth_role({"user_id": BOB_ID}, None, None))

        assert metadata == {"user_id": "", "org_id": ""}
        assert resolve_owner_scope(SimpleNamespace(metadata=metadata)) is None

    def test_a_turn_with_no_context_clears_it_too(self):
        metadata = {"user_id": ALICE_ID, "org_id": "org-1"}

        stamp_verified_identity(metadata, None)

        assert resolve_owner_scope(SimpleNamespace(metadata=metadata)) is None

    @pytest.mark.asyncio
    async def test_the_pre_compact_hook_receives_the_verified_user_never_the_spoofed_one(self):
        """Behaviour: drive ``_prepare_llm_workflow_params`` with a spoofed request ``user_id``."""
        from chat_workflow.manager import ChatWorkflowManager

        manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
        manager._register_user_message_in_history = MagicMock()
        manager._prepare_llm_request_params = AsyncMock(return_value={"prompt": "p", "model": "m"})
        manager._fire_pre_compact_hook = AsyncMock()
        session = SimpleNamespace(session_id="s1", metadata={}, conversation_history=[])
        context = apply_auth_role({"user_id": "spoofed", "org_id": "evil"}, "user", {"user_id": ALICE_ID})

        await manager._prepare_llm_workflow_params(session, "hello", context)
        await asyncio.sleep(0)  # let the fire-and-forget hook task run

        manager._fire_pre_compact_hook.assert_called_once()
        assert manager._fire_pre_compact_hook.call_args.kwargs["user_id"] == ALICE_ID
        assert session.metadata["user_id"] == ALICE_ID

    @pytest.mark.asyncio
    async def test_an_unverified_turn_gives_the_hook_no_user_not_the_spoofed_one(self):
        from chat_workflow.manager import ChatWorkflowManager

        manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
        manager._register_user_message_in_history = MagicMock()
        manager._prepare_llm_request_params = AsyncMock(return_value={"prompt": "p", "model": "m"})
        manager._fire_pre_compact_hook = AsyncMock()
        session = SimpleNamespace(session_id="s1", metadata={"user_id": ALICE_ID}, conversation_history=[])

        await manager._prepare_llm_workflow_params(
            session, "hello", apply_auth_role({"user_id": "spoofed"}, None, None)
        )
        await asyncio.sleep(0)  # let the fire-and-forget hook task run

        assert not manager._fire_pre_compact_hook.call_args.kwargs["user_id"]


class TestShortestPathSkipsVisitedBeforeTheHopRead:
    @pytest.mark.asyncio
    async def test_hop_allowed_is_called_once_per_node_not_once_per_edge(self):
        g = make_graph()
        for n in ("a", "b", "c"):
            await g.add_node(n, {"id": n})
        for src, dst in (("a", "b"), ("a", "c"), ("b", "c"), ("c", "b")):
            await g.add_edge(src, dst, "LEADS_TO")
        seen = []

        async def allowed(node_id):
            seen.append(node_id)
            return True

        assert await g.shortest_path("a", "zzz", hop_allowed=allowed) is None
        assert sorted(seen) == ["b", "c"]

    @pytest.mark.asyncio
    async def test_the_target_is_still_checked_by_the_predicate(self):
        g = make_graph()
        for n in ("a", "b"):
            await g.add_node(n, {"id": n})
        await g.add_edge("a", "b", "LEADS_TO")

        assert await g.shortest_path("a", "b", hop_allowed=AsyncMock(return_value=False)) is None
