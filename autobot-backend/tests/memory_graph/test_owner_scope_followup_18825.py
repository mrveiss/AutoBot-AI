# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #18825 review follow-ups: required owner on every get_entity, one org rule, MCP principal,
generic name-collision 409, and batched edge visibility.

Companion to ``test_owner_scope_18825.py`` / ``test_owner_scope_routes_18825.py``.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.chat_activity_store import _store_single_activity, activity_principal  # noqa: E402
from api.graph_rag import _collect_collection_edges  # noqa: E402
from api.schemas_chat import ActivityCreate  # noqa: E402
from autobot_memory_graph import AutoBotMemoryGraph  # noqa: E402
from autobot_memory_graph.owner_scope import (  # noqa: E402
    NO_ORG,
    UNSCOPED_ALL_USERS,
    OwnerScope,
    OwnerScopeRequired,
    entity_visible,
    owner_fields,
)
from autobot_shared.ssot_config import config  # noqa: E402
from chat_history.graph_owner import session_owner_scope  # noqa: E402
from chat_history.layers import Layer2OnDemand  # noqa: E402
from chat_workflow.tiered_context_sources import resolve_owner_scope  # noqa: E402
from initialization.memory_graph_handlers import ENTITY_NAME_IN_USE_DETAIL, register_memory_graph_handlers  # noqa: E402
from mcp_server.autobot_server import AutoBotMCPServer  # noqa: E402
from memory.manager import _ProviderRouter  # noqa: E402
from services.memory.postgres_provider import PostgresMemoryProvider  # noqa: E402
from tests.memory_graph._owner_scope_doubles import (  # noqa: E402
    ALICE,
    ALICE_CONV,
    ALICE_ID,
    ALICE_UNTAGGED,
    BOB_CONV,
    BOB_ID,
    SHARED_DOC,
    QueryHost,
    RelationHost,
    TraversalHost,
    _doc,
)

ORG_1 = OwnerScope.for_user(ALICE_ID, "org-1")
ORG_2 = OwnerScope.for_user(ALICE_ID, "org-2")


# ---------------------------------------------------------------------------
# get_entity: the owner is required for id lookups too (item 2)
# ---------------------------------------------------------------------------


class TestGetEntityRequiresAnOwner:
    @pytest.mark.asyncio
    async def test_omitting_the_owner_on_an_id_lookup_raises(self):
        with pytest.raises(TypeError):
            await TraversalHost().get_entity(entity_id="a")  # keyword-only, no default

    @pytest.mark.asyncio
    async def test_a_none_or_foreign_owner_on_an_id_lookup_raises_instead_of_reading(self):
        host = TraversalHost()
        with pytest.raises(OwnerScopeRequired):
            await host.get_entity(entity_id="a", owner=None)
        with pytest.raises(OwnerScopeRequired):
            await host.get_entity(entity_id="a", owner=ALICE_ID)

    @pytest.mark.asyncio
    async def test_the_sentinel_still_reads_by_id(self):
        assert (await TraversalHost().get_entity(entity_id="x", owner=UNSCOPED_ALL_USERS))["id"] == "x"

    @pytest.mark.asyncio
    async def test_the_provider_refuses_an_id_read_with_no_caller_scope(self):
        provider = PostgresMemoryProvider.__new__(PostgresMemoryProvider)
        provider.memory_graph = MagicMock()
        provider.memory_graph.get_entity = AsyncMock(return_value=BOB_CONV)

        assert await provider.get_entity("c-bob") is None
        provider.memory_graph.get_entity.assert_not_called()
        assert await provider.get_entity("c-bob", owner=ALICE) == BOB_CONV
        provider.memory_graph.get_entity.assert_awaited_once_with(entity_id="c-bob", owner=ALICE)

    @pytest.mark.asyncio
    async def test_the_router_passes_the_callers_scope_down(self):
        router = _ProviderRouter.__new__(_ProviderRouter)
        router.built_in = MagicMock()
        router.built_in.get_entity = AsyncMock(return_value=None)

        await router.get_entity("c-1", owner=ALICE)

        router.built_in.get_entity.assert_awaited_once_with("c-1", owner=ALICE)


# ---------------------------------------------------------------------------
# One org rule on write and read (item 4) and in the RediSearch query (item 5)
# ---------------------------------------------------------------------------


class TestOrgRule:
    def test_a_users_own_org_less_entity_is_visible_from_any_org_context(self):
        org_less = _doc("c-1", "Conversation 1", ALICE_ID)
        assert entity_visible(org_less, ALICE) and entity_visible(org_less, ORG_1) and entity_visible(org_less, ORG_2)
        assert entity_visible({**org_less, "owner_org_id": NO_ORG}, ORG_1)

    def test_an_entity_stamped_with_an_org_is_visible_only_in_that_org(self):
        in_org_1 = _doc("c-2", "Conversation 2", ALICE_ID, org="org-1")
        assert entity_visible(in_org_1, ORG_1)
        assert not entity_visible(in_org_1, ORG_2) and not entity_visible(in_org_1, ALICE)

    def test_another_users_org_less_entity_is_still_not_visible(self):
        assert not entity_visible(_doc("c-3", "Conversation 3", BOB_ID), ORG_1)

    def test_writes_stamp_the_principals_org_or_the_no_org_tag(self):
        assert owner_fields(ORG_1)["owner_org_id"] == "org-1"
        assert owner_fields(ALICE)["owner_org_id"] == NO_ORG

    @pytest.mark.asyncio
    async def test_the_search_query_itself_carries_the_org_clause(self):
        host = QueryHost([ALICE_CONV, BOB_CONV], search_down=False)

        found = await host.search_entities(query="plan", owner=ORG_1)

        sent = host.redis_client.commands[0][2]
        assert "@owner_org_id:{" in sent and "org\\-1" in sent and NO_ORG in sent
        assert all(e.get("owner_user_id", ALICE_ID) == ALICE_ID for e in found)  # backstop drops bob's

    @pytest.mark.asyncio
    async def test_a_cross_org_entity_is_not_returned_even_if_the_index_returned_it(self):
        other_org = _doc("c-x", "Conversation x", ALICE_ID, org="org-2")
        host = QueryHost([other_org], search_down=True)

        assert await host.search_entities(query="x", owner=ORG_1) == []
        assert [e["id"] for e in await host.search_entities(query="x", owner=ORG_2)] == ["c-x"]

    def test_the_conversation_org_key_is_org_id_on_both_the_stamp_and_the_l2_read(self):
        meta = {"user_id": ALICE_ID, "org_id": "org-1"}
        session = SimpleNamespace(metadata={**meta, "tenant_id": "someone-elses-tenant"})

        assert resolve_owner_scope(session) == session_owner_scope(meta) == ORG_1

    @pytest.mark.asyncio
    async def test_l2_context_finds_the_conversation_the_session_wrote(self):
        meta = {"user_id": ALICE_ID, "org_id": "org-1"}
        stamped = {**ALICE_CONV, **owner_fields(session_owner_scope(meta))}
        graph = QueryHost([stamped, BOB_CONV], search_down=True)
        owner = resolve_owner_scope(SimpleNamespace(metadata=meta))

        context = {"user_message": "Tell me about Alice", "memory_graph": graph, "owner": owner}
        out = await Layer2OnDemand().render(context)

        assert "Conversation alice" in out and "Conversation bob" not in out

    @pytest.mark.asyncio
    async def test_the_principals_org_reaches_the_activity_write(self):
        principal = activity_principal({"user_data": {"user_id": ALICE_ID, "org_id": "org-1"}})
        assert principal == (ALICE_ID, "org-1")
        assert activity_principal({"user_data": {"user_id": ALICE_ID}}) == (ALICE_ID, None)

        graph = MagicMock()
        graph.create_activity_entity = AsyncMock(return_value={})
        activity = ActivityCreate(type="terminal", user_id="spoofed", content="ls", activity_id="a-1", timestamp="t")
        await _store_single_activity(graph, "chat-1", activity, *principal)

        assert graph.create_activity_entity.await_args.kwargs["org_id"] == "org-1"


# ---------------------------------------------------------------------------
# The MCP memory tools read under the authenticated principal (item 3)
# ---------------------------------------------------------------------------

MCP_KEY = "unit-test-placeholder"


class _McpGraph(RelationHost):
    """A real owner-scoped graph over the in-memory Redis double, shaped for the MCP tools.

    alice's conversation points at her own note, at bob's conversation and at a shared entity;
    bob's conversation points back at alice's.
    """

    def __init__(self):
        super().__init__(
            [ALICE_CONV, BOB_CONV, SHARED_DOC, ALICE_UNTAGGED],
            out={
                "c-alice": [
                    {"to": "n-alice", "type": "related_to"},
                    {"to": "c-bob", "type": "references"},
                    {"to": "s-1", "type": "mentions"},
                ],
                "c-bob": [{"to": "c-alice", "type": "blocks"}],
            },
            inc={"c-alice": [{"from": "c-bob", "type": "blocks"}]},
        )


def _lookup(name, **extra):
    return {"name": "memory.entity_lookup", "arguments": {"name": name}, **extra}


def _claims(agent_id, tenant_id="org-1"):
    return {"jti": "j", "agent_id": agent_id, "tenant_id": tenant_id, "scope": ["mcp:knowledge"]}


async def _call(server, params, token="", client_ip=None):
    graph = _McpGraph()
    with patch("autobot_memory_graph.AutoBotMemoryGraph", return_value=graph):
        resp = await server.handle_request("tools/call", params, token, req_id=1, client_ip=client_ip)
    if "error" in resp:
        return resp
    return json.loads(resp["result"]["content"][0]["text"])


@pytest.fixture
def _mcp_key():
    with patch.object(config.misc, "mcp_token", MCP_KEY):
        yield


class TestMcpMemoryToolsFollowThePrincipal:
    @pytest.mark.asyncio
    async def test_an_http_run_jwt_principal_reads_its_own_entities_and_not_anothers(self):
        server = AutoBotMCPServer()
        # Alice's conversation was written org-less: visible to her from the run's org (item 4).
        with patch("mcp_server.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_claims(ALICE_ID))):
            mine = await _call(server, _lookup("Conversation alice", run_jwt="t"))
            theirs = await _call(server, _lookup("Conversation bob", run_jwt="t"))

        assert mine["id"] == "c-alice"
        assert theirs == {"error": "Entity not found", "name": "Conversation bob"}

    @pytest.mark.asyncio
    async def test_principal_b_cannot_read_principal_as_entities(self):
        server = AutoBotMCPServer()
        with patch("mcp_server.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_claims(BOB_ID))):
            out = await _call(server, _lookup("Conversation alice", run_jwt="t"))

        assert out["error"] == "Entity not found"

    @pytest.mark.asyncio
    async def test_an_http_bearer_principal_owns_nothing_but_still_reads_shared_entities(self, _mcp_key):
        server = AutoBotMCPServer()
        token = f"{MCP_KEY}:memory"

        assert (await _call(server, _lookup("Conversation alice"), token, "203.0.113.9"))["error"] == "Entity not found"
        assert (await _call(server, _lookup("Conversation shared"), token, "203.0.113.9"))["id"] == "s-1"

    @pytest.mark.asyncio
    async def test_the_stdio_transport_has_no_identity_and_fails_closed(self, _mcp_key):
        server = AutoBotMCPServer()

        resp = await _call(server, _lookup("Conversation alice"), f"{MCP_KEY}:memory", "stdio")

        assert resp["error"]["code"] == -32003
        assert "c-alice" not in json.dumps(resp)

    @pytest.mark.asyncio
    async def test_a_handler_called_with_no_principal_bound_fails_closed(self):
        with pytest.raises(OwnerScopeRequired):
            await AutoBotMCPServer()._memory_entity_lookup("Conversation alice")


# ---------------------------------------------------------------------------
# A name collision is a generic 409 with nothing user-written in it (item 6)
# ---------------------------------------------------------------------------


class TestNameCollisionIsAGeneric409:
    def _client(self, graph):
        app = FastAPI()
        register_memory_graph_handlers(app)

        @app.post("/entity")
        async def create():
            await graph.get_or_create_entity("CONVERSATION", "Conversation bob", [], owner=ALICE)

        return TestClient(app, raise_server_exceptions=False)

    def _graph_where_bob_holds_the_name(self):
        graph = AutoBotMemoryGraph()
        graph._initialized = True
        graph.knowledge_base = None
        redis = MagicMock()
        redis.get = AsyncMock(return_value=b"c-bob")
        redis.json.return_value.get = AsyncMock(return_value=BOB_CONV)
        graph.redis_client = redis
        return graph

    def test_the_route_answers_409_without_the_name(self, caplog):
        with caplog.at_level(logging.DEBUG):
            resp = self._client(self._graph_where_bob_holds_the_name()).post("/entity")

        assert resp.status_code == 409
        assert resp.json() == {"detail": ENTITY_NAME_IN_USE_DETAIL}
        assert "bob" not in resp.text.lower()
        assert "Conversation bob" not in caplog.text


# ---------------------------------------------------------------------------
# Edge visibility is one batched fetch, not a get_entity per edge (item 7)
# ---------------------------------------------------------------------------


class TestCollectionEdgesAreBatched:
    @pytest.mark.asyncio
    async def test_many_edges_cost_batched_fetches_and_no_get_entity(self):
        docs = [_doc(f"a{i}", f"Conversation a{i}", ALICE_ID) for i in range(30)]
        docs += [_doc(f"b{i}", f"Conversation b{i}", BOB_ID) for i in range(30)]
        targets = [{"to": f"{kind}{i}", "type": "related_to"} for kind in "ab" for i in range(30)]
        graph = RelationHost(docs, out={"a0": targets, "a1": targets})
        graph.get_entity = AsyncMock(side_effect=AssertionError("per-edge get_entity"))
        pipelines = []
        real_pipeline = graph.redis_client.pipeline
        graph.redis_client.pipeline = lambda: pipelines.append(1) or real_pipeline()

        edges = await _collect_collection_edges(SimpleNamespace(graph=graph), ["a0", "a1"], ALICE)

        assert {e["to"] for e in edges} == {f"a{i}" for i in range(30)}  # bob's targets dropped
        assert len(edges) == 60
        assert len(pipelines) == 4  # per node: 60 targets + the node at 50 per round trip, not 60 gets


# ---------------------------------------------------------------------------
# Relations never reveal an endpoint the principal cannot read (#18825)
# ---------------------------------------------------------------------------


def _rendered(payload):
    return json.dumps(payload)


class TestMcpRelationsStayInTheCallersScope:
    @pytest.mark.asyncio
    async def test_timeline_for_a_omits_relations_to_bs_entities_and_keeps_a_to_a(self):
        server = AutoBotMCPServer()
        params = {"name": "memory.timeline", "arguments": {"entity": "Conversation alice"}, "run_jwt": "t"}
        with patch("mcp_server.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_claims(ALICE_ID))):
            out = await _call(server, params)

        rels = out["entity"]["relations"]
        assert [r["to"] for r in rels["outgoing"]] == ["n-alice", "s-1"]  # A->A and A->shared kept
        assert rels["incoming"] == []  # bob's edge into alice is gone with its type
        assert "c-bob" not in _rendered(out) and "references" not in _rendered(out) and "blocks" not in _rendered(out)
        assert {e["id"] for e in out["timeline"]} == {"n-alice", "s-1"}

    @pytest.mark.asyncio
    async def test_related_for_a_omits_relations_to_bs_entities_and_keeps_a_to_a(self):
        server = AutoBotMCPServer()
        params = {"name": "memory.related", "arguments": {"entity": "Conversation alice"}, "run_jwt": "t"}
        with patch("mcp_server.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_claims(ALICE_ID))):
            out = await _call(server, params)

        assert [r["to"] for r in out["root"]["relations"]["outgoing"]] == ["n-alice", "s-1"]
        assert {e["id"] for e in out["related"]} == {"c-alice", "n-alice", "s-1"}
        assert "c-bob" not in _rendered(out) and "references" not in _rendered(out)

    @pytest.mark.asyncio
    async def test_get_relations_needs_an_owner_and_the_sentinel_still_sees_everything(self):
        graph = _McpGraph()
        with pytest.raises(TypeError):
            await graph.get_relations("c-alice")  # keyword-only, no default
        with pytest.raises(OwnerScopeRequired):
            await graph.get_relations("c-alice", owner=None)

        everything = await graph.get_relations("c-alice", direction="both", owner=UNSCOPED_ALL_USERS)
        scoped = await graph.get_relations("c-alice", direction="both", owner=ALICE)

        assert {r["type"] for r in everything["relations"]} == {"related_to", "references", "mentions", "blocks"}
        assert {r["type"] for r in scoped["relations"]} == {"related_to", "mentions"}

    @pytest.mark.asyncio
    async def test_get_relations_on_an_entity_the_caller_cannot_read_returns_nothing(self):
        out = await _McpGraph().get_relations("c-bob", direction="both", owner=ALICE)

        assert out == {"relations": []}  # bob's c-bob -> alice's c-alice edge is not alice's to see
