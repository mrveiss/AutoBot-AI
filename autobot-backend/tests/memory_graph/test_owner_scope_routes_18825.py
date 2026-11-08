# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #18825: the Graph-RAG routes, activity attribution and other graph readers are owner-scoped.

Routes are driven directly over the real query layer (in-memory Redis double), asserting what each
caller *receives*: user A never gets user B's conversation, session title or username back.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from api.chat_activity_store import _store_single_activity, activity_principal_id  # noqa: E402
from api.graph_rag import _owner_scope, collection_graph, graph_rag_path, graph_rag_search  # noqa: E402
from api.schemas_chat import ActivityCreate  # noqa: E402
from api.schemas_knowledge import GraphRAGPathRequest, GraphRAGSearchRequest  # noqa: E402
from autobot_memory_graph.owner_scope import OwnerScopeRequired  # noqa: E402
from autobot_shared.user_management.base_service import TenantContext  # noqa: E402
from chat_history.layers import Layer2OnDemand  # noqa: E402
from services.memory.postgres_provider import PostgresMemoryProvider  # noqa: E402
from tests.memory_graph._owner_scope_doubles import (  # noqa: E402
    ALICE,
    ALICE_CONV,
    ALICE_ID,
    ALL_DOCS,
    BOB,
    BOB_CONV,
    BOB_ID,
    QueryHost,
    RelationHost,
    TraversalHost,
)

ALICE_TENANT = TenantContext(user_id=uuid.UUID(ALICE_ID))
BOB_TENANT = TenantContext(user_id=uuid.UUID(BOB_ID))


def _collection_service(search_down=True):
    graph = QueryHost(ALL_DOCS, search_down)
    graph.get_relations = AsyncMock(return_value={"relations": []})

    return SimpleNamespace(graph=graph)


class TestGraphRagRoutes:
    @pytest.mark.asyncio
    async def test_collection_graph_returns_only_the_callers_conversations(self):
        service = _collection_service()

        alice = await collection_graph(collection_id="conversation", service=service, tenant=ALICE_TENANT)
        bob = await collection_graph(collection_id="conversation", service=service, tenant=BOB_TENANT)

        alice_body = json.loads(bytes(alice.body).decode("utf-8"))
        bob_body = json.loads(bytes(bob.body).decode("utf-8"))
        assert {n["name"] for n in alice_body["nodes"]} == {"Conversation alice", "Conversation shared"}
        assert "bob's private plan" not in json.dumps(alice_body)
        assert {n["name"] for n in bob_body["nodes"]} == {"Conversation bob", "Conversation shared"}
        assert "alice's private plan" not in json.dumps(bob_body)

    @pytest.mark.asyncio
    async def test_collection_graph_drops_edges_into_entities_the_caller_cannot_read(self):
        out = {"c-alice": [{"to": "c-bob", "type": "REFERENCES"}, {"to": "s-1", "type": "MENTIONS"}]}
        service = SimpleNamespace(graph=RelationHost(ALL_DOCS, out=out))

        response = await collection_graph(collection_id="conversation", service=service, tenant=ALICE_TENANT)

        edges = json.loads(bytes(response.body).decode("utf-8"))["edges"]
        assert [e["type"] for e in edges] == ["MENTIONS"]  # the edge into bob's conversation is gone

    @pytest.mark.asyncio
    async def test_search_route_passes_the_callers_scope_to_the_service(self):
        service = MagicMock()
        metrics = MagicMock(total_time=0.0)
        metrics.to_response_dict.return_value = {}
        service.graph_aware_search = AsyncMock(return_value=([], metrics))

        await graph_rag_search(
            search_request=GraphRAGSearchRequest(query="redis config"),
            service=service,
            tenant=ALICE_TENANT,
            current_user={"role": "user"},
        )

        assert service.graph_aware_search.await_args.kwargs["owner"] == ALICE

    @pytest.mark.asyncio
    async def test_path_route_passes_the_callers_scope_to_the_service(self):
        service = MagicMock()
        service.find_connection_path = AsyncMock(return_value={"found": True, "hops": 0, "path": []})

        await graph_rag_path(
            path_request=GraphRAGPathRequest(from_entity="A", to_entity="B"), service=service, tenant=BOB_TENANT
        )

        assert service.find_connection_path.await_args.kwargs["owner"] == BOB

    @pytest.mark.asyncio
    async def test_a_tenant_with_no_user_is_a_403_not_an_unscoped_read(self):
        from fastapi import HTTPException

        service = _collection_service()

        with pytest.raises(HTTPException) as exc:
            await collection_graph(collection_id="conversation", service=service, tenant=TenantContext())

        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Activity attribution comes from the principal, never the body
# ---------------------------------------------------------------------------


class TestActivityIgnoresTheBodyUserId:
    def test_the_principal_is_the_authenticated_user(self):
        assert activity_principal_id({"user_data": {"user_id": "alice-id", "username": "alice"}}) == "alice-id"

    def test_no_authenticated_user_is_a_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            activity_principal_id({})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_spoofed_body_user_id_never_reaches_the_graph(self):
        graph = MagicMock()
        graph.create_activity_entity = AsyncMock(return_value={"entity_id": "e"})
        activity = ActivityCreate(
            activity_id="a-1",
            type="terminal",
            user_id="victim-user",
            content="rm -rf",
            timestamp="2026-01-01T00:00:00Z",
        )

        await _store_single_activity(graph, "chat-1", activity, "alice-id")

        assert graph.create_activity_entity.await_args.kwargs["user_id"] == "alice-id"


# ---------------------------------------------------------------------------
# Other readers: chat context (L2) and the memory provider
# ---------------------------------------------------------------------------


class TestExtractionAndLookupByName:
    @pytest.mark.asyncio
    async def test_extracted_entities_are_stamped_with_the_requesting_principal(self):
        from agents.graph_entity_writer import create_entities_in_graph

        graph = MagicMock()
        graph.create_entity = AsyncMock(return_value={"id": "e1"})
        candidate = SimpleNamespace(
            entity_type="feature",
            name="Feature X",
            observations=["o"],
            confidence=0.9,
            temporal_type=None,
            tags=["t"],
        )

        await create_entities_in_graph(graph, [candidate], ALICE)

        assert graph.create_entity.await_args.kwargs["owner"] == ALICE

    @pytest.mark.asyncio
    async def test_a_name_lookup_without_a_scope_raises_instead_of_reading_as_not_found(self):
        host = TraversalHost()

        with pytest.raises(TypeError):
            await host.get_entity(entity_name="A")  # keyword-only, no default
        with pytest.raises(OwnerScopeRequired):
            await host.get_entity(entity_name="A", owner=None)

    @pytest.mark.asyncio
    async def test_an_id_lookup_with_a_scope_hides_another_owners_entity(self):
        host = TraversalHost()

        assert await host.get_entity(entity_id="x", owner=ALICE) is None
        assert (await host.get_entity(entity_id="x", owner=BOB))["id"] == "x"


class TestOtherReadersAreScoped:
    @pytest.mark.asyncio
    async def test_l2_context_without_an_owner_reads_nothing(self):
        graph = MagicMock()
        graph.search_entities = AsyncMock(return_value=[ALICE_CONV])

        out = await Layer2OnDemand().render({"user_message": "Tell me about Redis", "memory_graph": graph})

        assert out == ""
        graph.search_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_l2_context_searches_within_the_turns_owner(self):
        graph = MagicMock()
        graph.search_entities = AsyncMock(return_value=[])

        await Layer2OnDemand().render({"user_message": "Tell me about Redis", "memory_graph": graph, "owner": ALICE})

        assert graph.search_entities.await_args.kwargs["owner"] == ALICE

    @pytest.mark.asyncio
    async def test_the_memory_provider_refuses_a_search_with_no_user_scope(self):
        provider = PostgresMemoryProvider.__new__(PostgresMemoryProvider)
        provider.memory_graph = MagicMock()
        provider.memory_graph.search_entities = AsyncMock(return_value=[BOB_CONV])

        assert await provider.search("plan", limit=5) == []
        assert await provider.search("plan", limit=5, filters={"user_id": ALICE_ID}) == [BOB_CONV]
        assert provider.memory_graph.search_entities.await_args.kwargs["owner"] == ALICE


class TestAdminsGetNoCrossUserPath:
    """ADMIN RULE (#18825): ``is_platform_admin`` widens nothing on the graph routes."""

    @pytest.mark.asyncio
    async def test_an_admin_does_not_see_another_users_entity_through_collection_graph(self):
        admin_tenant = TenantContext(user_id=uuid.UUID(ALICE_ID), is_platform_admin=True)
        out = {"c-alice": [{"to": "c-bob", "type": "REFERENCES"}]}
        service = SimpleNamespace(graph=RelationHost(ALL_DOCS, out=out))

        response = await collection_graph(collection_id="conversation", service=service, tenant=admin_tenant)

        body = json.loads(bytes(response.body).decode("utf-8"))
        assert "Conversation bob" not in {n["name"] for n in body["nodes"]}
        assert "bob's private plan" not in json.dumps(body)
        assert body["edges"] == []  # the edge into bob's conversation is gone for the admin too

    def test_the_admin_flag_does_not_change_the_scope(self):
        plain = TenantContext(user_id=uuid.UUID(ALICE_ID))
        admin = TenantContext(user_id=uuid.UUID(ALICE_ID), is_platform_admin=True)

        assert _owner_scope(admin) == _owner_scope(plain) == ALICE

    @pytest.mark.asyncio
    async def test_an_admin_scope_cannot_get_another_users_entity_by_id(self):
        graph = RelationHost(ALL_DOCS)
        admin = TenantContext(user_id=uuid.UUID(ALICE_ID), is_platform_admin=True)
        assert await graph.get_entity(entity_id="c-bob", owner=_owner_scope(admin)) is None


class TestSessionActivitiesReachTheGraph:
    """The activities route passed ``activity_type=`` to a graph method whose parameter is
    ``activity_types``; the TypeError was swallowed into an empty 200 (#18825)."""

    class _Graph:
        def __init__(self):
            self.calls = []

        async def get_session_activities(self, session_id, activity_types=None, user_id=None, limit=100):
            self.calls.append({"session_id": session_id, "activity_types": activity_types, "user_id": user_id})
            return [{"type": "terminal", "session_id": session_id}]

    @pytest.mark.asyncio
    async def test_a_type_filter_reaches_the_graph_as_a_list_and_activities_come_back(self):
        from api.chat_sessions import _fetch_activities_from_graph

        graph = self._Graph()
        response = await _fetch_activities_from_graph(graph, "s1", "terminal", "u1", 10, "req")
        assert graph.calls == [{"session_id": "s1", "activity_types": ["terminal"], "user_id": "u1"}]
        assert json.loads(response.body)["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_no_type_filter_is_none_not_an_empty_list(self):
        from api.chat_sessions import _fetch_activities_from_graph

        graph = self._Graph()
        await _fetch_activities_from_graph(graph, "s1", None, "u1", 10, "req")
        assert graph.calls[0]["activity_types"] is None

    @pytest.mark.asyncio
    async def test_a_graph_failure_is_not_turned_into_an_empty_success(self):
        from api.chat_sessions import _fetch_activities_from_graph

        graph = MagicMock()
        graph.get_session_activities = AsyncMock(side_effect=RuntimeError("graph down"))
        with pytest.raises(RuntimeError):
            await _fetch_activities_from_graph(graph, "s1", None, "u1", 10, "req")
