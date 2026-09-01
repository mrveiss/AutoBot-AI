# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every SDK resource method must come back populated from a real response body.

``repo_tests/sdk_response_model_contract_test.py`` compares *field names* between
an SDK model and the backend model it is fed from. That catches drift, but it
cannot catch the two failures this file exists for, because both survive a
perfectly matched name set:

* **The envelope.** Six methods parsed ``DataResponse[X]`` out of a route that
  returns its document flat. Every envelope field carries a default, so
  ``model_validate`` *succeeded* and returned ``success=True, data=None`` -- a
  plausible object with an empty payload, no exception, no log line (#15116).
* **Requiredness.** ``SessionCreate.session_id`` was required and emitted by
  nothing, so pydantic could satisfy neither the model nor the envelope's
  ``None`` and every successful create raised (#15114). The same shape hit
  ``sessions.list()`` and ``sessions.get()`` through ``Session.session_id`` and
  ``ChatMessage.role``/``content``.

So the assertions here run the real resource method against an ``httpx``
transport that answers with a body **built from the backend response model**, and
read named fields off the result. "It did not raise" is not an assertion this
file makes anywhere -- that is precisely the bar #15116 cleared while returning
nothing.

Fixtures are constructed by instantiating the backend model and dumping it, not
by hand-writing a dict that looks like one: a fixture invented here would drift
from the route exactly the way the SDK did.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import httpx
import pytest
from autobot_sdk import AutoBot

from api.schemas_analytics_collector import AnalyticsPerformanceMetricsResponse, AnalyticsUsageStatisticsResponse
from api.schemas_chat import (
    SessionCreateData,
    SessionDeleteData,
    SessionUpdateData,
)
from api.schemas_chat_rows import SessionListData, SessionMessagesData
from api.schemas_common import DataResponse
from knowledge.schemas.entries import KnowledgeEntriesResponse
from knowledge.schemas.entries import KnowledgeEntry as BackendKnowledgeEntry
from knowledge.schemas.ingestion import AddTextResponse
from knowledge.schemas.operations import KnowledgeStatsResponse
from knowledge.schemas.search import KnowledgeSearchResponse

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"
_BASE = "http://backend.test:9999"


def _call(coroutine_factory, body: dict):
    """Run one SDK method against a transport that answers *body* without dialling."""

    async def run():
        async with AutoBot(base_url=_BASE, token="t") as bot:
            bot._client._transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=body))
            return await coroutine_factory(bot)

    return asyncio.run(run())


def _dict_literal_keys(node: ast.AST) -> frozenset[str]:
    """String keys of *node* when it is a dict literal, else an empty set."""
    if not isinstance(node, ast.Dict):
        return frozenset()
    return frozenset(k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))


def _returned_dict_keys(source_file: Path, function: str) -> frozenset[str]:
    """String keys of the dict literal *function* returns, read from source.

    The backend types ``SessionListData.sessions`` and
    ``SessionMessagesData.messages`` as ``List[Any]`` (#15138), so no server-side
    model describes a row and the fixtures below have to name the keys themselves.
    Reading them back out of the function that writes them keeps those fixtures
    from becoming a private opinion about the wire.

    Both spellings are read: ``return {...}`` (``_build_session_entry``) and
    ``name = {...}`` followed by ``return name`` (``_build_message_dict``, which then
    adds two keys conditionally -- hence the subset assertion at that call site).
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != function:
            continue
        assigned: dict[str, frozenset[str]] = {}
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign):
                keys = _dict_literal_keys(inner.value)
                for target in inner.targets:
                    if isinstance(target, ast.Name) and keys:
                        assigned[target.id] = keys
            if not isinstance(inner, ast.Return) or inner.value is None:
                continue
            direct = _dict_literal_keys(inner.value)
            if direct:
                return direct
            if isinstance(inner.value, ast.Name) and inner.value.id in assigned:
                return assigned[inner.value.id]
    raise AssertionError(f"{function} in {source_file.name} returns no dict literal -- this check found nothing to pin")


# --- fixtures, each built from the model that describes the real body -------

SESSION_ROW = {
    "id": "s1",
    "chatId": "s1",
    "title": "Planning",
    "name": "Planning",
    "messages": [],
    "messageCount": 3,
    "createdAt": "2026-01-01T00:00:00",
    "createdTime": "2026-01-01T00:00:00",
    "updatedAt": "2026-01-02T00:00:00",
    "lastModified": "2026-01-02T00:00:00",
    "updatedAtEpoch": 1767312000.0,
    "isActive": False,
    "fileSize": 2048,
    "fast_mode": True,
    "companyId": "acme",
    "sessionKind": "user",
}

MESSAGE_ROW = {
    "id": "m1",
    "sender": "user",
    "text": "hello",
    "messageType": "text",
    "metadata": {"k": "v"},
    "timestamp": "2026-01-01 00:00:00",
    "sources": [{"title": "doc", "path": "/d", "score": 0.9, "chunk_id": "c1"}],
    "toolMarkers": ["run"],
    "authorId": "u1",
}


def _envelope(payload) -> dict:
    return DataResponse(success=True, data=payload, message="ok", timestamp="2026-01-01T00:00:00").model_dump()


def test_the_session_row_fixture_matches_the_literal_the_backend_writes():
    """Guards the guard: a key the fixture forgot would make the row assertions vacuous."""
    written = _returned_dict_keys(_BACKEND / "chat_history" / "session_listing.py", "_build_session_entry")

    assert written == frozenset(SESSION_ROW), (
        f"SESSION_ROW no longer matches _build_session_entry: missing {sorted(written - frozenset(SESSION_ROW))}, "
        f"unknown {sorted(frozenset(SESSION_ROW) - written)}"
    )


def test_the_message_row_fixture_covers_the_literal_the_backend_writes():
    """``toolMarkers`` and ``authorId`` are added conditionally, so the literal is a subset."""
    written = _returned_dict_keys(_BACKEND / "chat_history" / "messages.py", "_build_message_dict")

    assert written <= frozenset(MESSAGE_ROW), f"MESSAGE_ROW is missing {sorted(written - frozenset(MESSAGE_ROW))}"
    assert written, "the message literal enumerated no keys"


# --- #15114: the methods that raised on every success ----------------------


def test_create_returns_the_new_session_id_instead_of_raising():
    """AC (#15114): a real create response parses, and every declared field is populated."""
    payload = SessionCreateData(
        id="s1",
        title="Planning",
        metadata={"source": "test"},
        created_at="2026-01-01T00:00:00",
        last_modified="2026-01-01T00:00:00",
    )

    result = _call(lambda bot: bot.sessions.create(title="Planning"), _envelope(payload.model_dump()))

    assert result.data is not None, "the envelope parsed but carried no payload"
    assert result.data.id == "s1"
    assert result.data.title == "Planning"
    assert result.data.metadata == {"source": "test"}
    assert result.data.created_at == "2026-01-01T00:00:00"
    assert result.data.last_modified == "2026-01-01T00:00:00"


def test_update_returns_the_updated_document_instead_of_raising():
    """AC (#15114): same for update, whose ``success`` field duplicated the envelope's."""
    payload = SessionUpdateData(
        id="s1",
        title="Renamed",
        metadata={"source": "test"},
        created_at="2026-01-01T00:00:00",
        last_modified="2026-01-03T00:00:00",
    )

    result = _call(lambda bot: bot.sessions.update("s1", title="Renamed"), _envelope(payload.model_dump()))

    assert result.data is not None
    assert result.data.id == "s1"
    assert result.data.title == "Renamed"
    assert result.data.metadata == {"source": "test"}
    assert result.data.created_at == "2026-01-01T00:00:00"
    assert result.data.last_modified == "2026-01-03T00:00:00"
    assert not hasattr(result.data, "success"), "SessionUpdate still duplicates the envelope's success flag"


def test_list_parses_a_response_that_actually_contains_a_session():
    """``Session.session_id`` was required and emitted by nothing, so this raised whenever a session existed."""
    payload = SessionListData(sessions=[SESSION_ROW], count=1)

    result = _call(lambda bot: bot.sessions.list(), _envelope(payload.model_dump()))

    assert result.data is not None
    assert result.data.count == 1
    assert [s.id for s in result.data.sessions] == ["s1"]
    assert result.data.sessions[0].messageCount == 3
    assert result.data.sessions[0].sessionKind == "user"


def test_get_parses_a_response_that_actually_contains_a_message():
    """``ChatMessage.role``/``content`` were required and emitted by nothing."""
    payload = SessionMessagesData(messages=[MESSAGE_ROW], session_id="s1", total_count=1, page=1, per_page=50)

    result = _call(lambda bot: bot.sessions.get("s1"), _envelope(payload.model_dump()))

    assert result.data is not None
    assert result.data.session_id == "s1"
    assert result.data.total_count == 1
    assert result.data.messages[0].sender == "user"
    assert result.data.messages[0].text == "hello"


def test_delete_reports_a_failed_delete_as_a_failure():
    """AC (#15118): ``SessionDelete.success`` defaulted to True, so a failed delete read as success."""
    payload = SessionDeleteData(session_id="s1", deleted=False, kb_cleanup={"facts_deleted": 0, "facts_preserved": 7})

    result = _call(lambda bot: bot.sessions.delete("s1"), _envelope(payload.model_dump()))

    assert result.data is not None
    assert result.data.deleted is False, "a failed delete must not read as a success"
    assert result.data.kb_cleanup is not None
    assert result.data.kb_cleanup.facts_preserved == 7


# --- #15116: the methods whose payload was always None ---------------------


def test_knowledge_stats_is_populated_rather_than_an_empty_envelope():
    body = KnowledgeStatsResponse(status="online", total_facts=12, categories=["ops", "dev"], db_size=99).model_dump()

    result = _call(lambda bot: bot.knowledge.stats(), body)

    assert result.status == "online"
    assert result.total_facts == 12
    assert result.categories == ["ops", "dev"]


def test_knowledge_add_text_returns_the_fact_id():
    body = AddTextResponse(status="success", message="stored", fact_id="f1", text_length=5, title="t").model_dump()

    result = _call(lambda bot: bot.knowledge.add_text("hello"), body)

    assert result.fact_id == "f1"
    assert result.status == "success"
    assert result.message == "stored", "the route's own message must not be swallowed by an envelope field"


def test_knowledge_search_returns_results_and_a_total():
    body = KnowledgeSearchResponse(
        results=[{"key": "k1", "score": 0.8}], total_results=1, query="q", mode="hybrid"
    ).model_dump()

    result = _call(lambda bot: bot.knowledge.search("q"), body)

    assert result.total_results == 1
    assert result.results == [{"key": "k1", "score": 0.8}]
    assert result.query == "q"


def test_knowledge_entries_returns_rows_and_the_next_cursor():
    body = KnowledgeEntriesResponse(
        entries=[BackendKnowledgeEntry(key="k1", title="T", content="c", category="ops", type="fact")],
        next_cursor="512",
        count=1,
        has_more=True,
    ).model_dump()

    result = _call(lambda bot: bot.knowledge.get_entries(), body)

    assert result.count == 1
    assert result.next_cursor == "512", "without next_cursor on the model a caller cannot page at all"
    assert result.has_more is True
    assert result.entries[0].key == "k1"
    assert result.entries[0].type == "fact"


def test_analytics_usage_is_populated_rather_than_an_empty_envelope():
    body = AnalyticsUsageStatisticsResponse(
        api_usage={"total_calls": 4},
        websocket_usage={"active_connections": 1},
        system_usage={"uptime_hours": 2.5},
        analysis_period={"data_points": 4},
    ).model_dump()

    result = _call(lambda bot: bot.analytics.usage(), body)

    assert result.api_usage == {"total_calls": 4}
    assert result.system_usage == {"uptime_hours": 2.5}
    assert result.analysis_period == {"data_points": 4}


def test_analytics_performance_is_populated_rather_than_an_empty_envelope():
    body = AnalyticsPerformanceMetricsResponse(
        system_performance={"cpu_percent": 9.0},
        network_io={"bytes_sent": 10},
        historical_context={"samples_count": 3},
    ).model_dump()

    result = _call(lambda bot: bot.analytics.performance(), body)

    assert result.system_performance == {"cpu_percent": 9.0}
    assert result.network_io == {"bytes_sent": 10}
    assert result.historical_context == {"samples_count": 3}


# --- #15118: the fields that were present and permanently None -------------


@pytest.mark.parametrize(
    "attribute",
    ["total", "total_entries", "avg_latency_ms", "p95_latency_ms", "error_rate", "cost_usd", "uptime"],
)
def test_no_sdk_model_still_declares_a_name_the_routes_never_emit(attribute):
    """The names #15118 listed are gone from every model, not merely unused."""
    from autobot_sdk import models as sdk

    holders = [
        model.__name__
        for model in vars(sdk).values()
        if isinstance(model, type) and hasattr(model, "model_fields") and attribute in model.model_fields
    ]

    assert not holders, f"{attribute!r} is still declared by {holders}; no route emits it"


def test_agent_health_carries_the_flags_the_route_actually_returns():
    """AC (#15118): ``AgentHealth`` shared one field name with its route and dropped five."""
    body = {
        "status": "healthy",
        "ai_stack_available": True,
        "multi_agent_coordination": False,
        "advanced_capabilities": True,
        "timestamp": "2026-01-01T00:00:00",
        "error": None,
    }

    result = _call(lambda bot: bot.agents.health(), body)

    assert result.status == "healthy"
    assert result.ai_stack_available is True
    assert result.multi_agent_coordination is False
    assert result.advanced_capabilities is True
    assert result.timestamp == "2026-01-01T00:00:00"
