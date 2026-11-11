# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The read-only ``code.*`` MCP tools (#21327, #13475).

The tools run the real server dispatcher, scope check and argument models, over the real query
service and a read-only fake graph: the answers asserted are the persisted graph's.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics import code_graph_queries as cgq
from api.codebase_analytics.endpoints import impact
from api.codebase_analytics.source_models import SourceAccess
from autobot_shared.ssot_config import config
from mcp_server import code_graph_tools
from mcp_server.autobot_server import AutoBotMCPServer
from testkit.fake_graph_collection import DEFAULT_COMMIT, FakeGraphCollection

SECRET = "code-tools-secret"  # pragma: allowlist secret
CODE_TOKEN = f"{SECRET}:code"
KB_TOKEN = f"{SECRET}:kb"
EXPECTED_TOOLS = {"code.resolve_symbol", "code.affected", "code.similar"}


@pytest.fixture(autouse=True)
def _graph():
    collection = FakeGraphCollection()
    with (
        patch.object(config.misc, "mcp_token", SECRET),
        patch.object(cgq, "get_existing_code_graph_collection", return_value=collection),
    ):
        yield collection


async def _call(name, arguments, token=CODE_TOKEN):
    return await AutoBotMCPServer().handle_request(
        "tools/call", {"name": name, "arguments": arguments}, token, req_id=1
    )


def _payload(resp) -> dict:
    return json.loads(resp["result"]["content"][0]["text"])


# --- scope ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_code_scope_lists_exactly_the_three_tools_and_other_scopes_do_not():
    listed = await AutoBotMCPServer().handle_request("tools/list", {}, CODE_TOKEN, req_id=1)
    assert {t["name"] for t in listed["result"]["tools"] if t["name"].startswith("code.")} == EXPECTED_TOOLS
    other = await AutoBotMCPServer().handle_request("tools/list", {}, KB_TOKEN, req_id=1)
    assert not [t for t in other["result"]["tools"] if t["name"].startswith("code.")]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
async def test_a_token_without_the_code_scope_is_denied_every_code_tool(name):
    resp = await _call(name, {"symbol": "target", "code": "x", "source_id": "s"}, token=KB_TOKEN)
    assert resp["error"]["code"] == -32001 and "result" not in resp


# --- resolve --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_all_candidates_for_an_ambiguous_symbol():
    answer = _payload(await _call("code.resolve_symbol", {"symbol": "helper"}))
    assert answer["status"] == "ambiguous" and answer["node_id"] is None
    assert [c["node_id"] for c in answer["candidates"]] == ["pkg.a.helper", "pkg.b.helper"]


@pytest.mark.asyncio
async def test_resolve_reports_an_unknown_symbol_as_not_found():
    answer = _payload(await _call("code.resolve_symbol", {"symbol": "no_such_symbol"}))
    assert (answer["status"], answer["candidates"]) == ("not_found", [])


# --- affected -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_affected_by_symbol_is_what_the_service_returns():
    tool = _payload(await _call("code.affected", {"symbol": "target"}))
    assert tool == await cgq.query_affected(symbol="target")
    assert tool["reached"] == ["pkg.b.caller", "pkg.d.top"] and tool["indexed_at_commit"] == DEFAULT_COMMIT


@pytest.mark.asyncio
async def test_affected_by_node_id_equals_the_http_route_answer():
    tool = _payload(await _call("code.affected", {"node_id": "pkg.a.target", "expected_commit": "0" * 40}))
    route = await impact.analyze_impact(node_id="pkg.a.target", symbol=None, max_depth=None, expected_commit="0" * 40)
    assert tool == json.loads(route.body)
    assert tool["reached"] == ["pkg.b.caller", "pkg.d.top"]


@pytest.mark.asyncio
async def test_affected_flags_a_stale_graph_explicitly():
    answer = _payload(await _call("code.affected", {"symbol": "target", "expected_commit": "0" * 40}))
    assert (answer["stale"], answer["freshness"]) == (True, "stale")
    assert answer["indexed_at_commit"] == DEFAULT_COMMIT and answer["reached"]


@pytest.mark.asyncio
async def test_affected_on_an_ambiguous_symbol_returns_candidates_not_a_guess():
    answer = _payload(await _call("code.affected", {"symbol": "helper"}))
    assert answer["status"] == "ambiguous" and answer["impact"] is None and "reached" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"symbol": "a", "node_id": "pkg.a.target"},
        {"symbol": "target", "max_depth": 99},
        {"symbol": "target", "expected_commit": "HEAD"},
    ],
)
async def test_affected_rejects_bad_arguments_as_invalid_params(arguments):
    assert (await _call("code.affected", arguments))["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_lists_are_capped_and_the_cut_is_reported():
    with patch.object(code_graph_tools, "CODE_TOOL_MAX_ITEMS", 1):
        answer = _payload(await _call("code.affected", {"symbol": "target"}))
    assert answer["reached"] == ["pkg.b.caller"] and answer["omitted"] == {"reached": 1, "edges": 1}


# --- similar --------------------------------------------------------------------------------------


def _source(owner, access=SourceAccess.PRIVATE):
    return SimpleNamespace(owner_id=owner, access=access, shared_with=[])


@pytest.mark.asyncio
async def test_similar_returns_hits_with_their_source_and_the_same_function_as_the_route():
    hits = [{"pattern_id": "p1", "similarity": 0.91}]
    find = AsyncMock(return_value=hits)
    with (
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=_source(None))),
        patch.object(cgq, "find_similar_code", find),
    ):
        answer = _payload(await _call("code.similar", {"code": "def f(): pass", "source_id": "src-a", "limit": 4}))
    find.assert_awaited_once_with("def f(): pass", "src-a", None, 4)
    assert answer["results"] == hits and answer["source_id"] == "src-a"
    assert (answer["indexed_at_commit"], answer["freshness"]) == (None, "unchecked")


@pytest.mark.asyncio
async def test_similar_cannot_read_another_owners_private_source():
    find = AsyncMock(return_value=[{"pattern_id": "secret"}])
    with (
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=_source("alice"))),
        patch.object(cgq, "find_similar_code", find),
    ):
        answer = _payload(await _call("code.similar", {"code": "x", "source_id": "alice-src"}))
    assert answer == {"error": "Code source not found", "source_id": "alice-src"}
    find.assert_not_awaited()


@pytest.mark.asyncio
async def test_similar_rejects_a_missing_or_malformed_source_id():
    assert (await _call("code.similar", {"code": "x"}))["error"]["code"] == -32602
    assert (await _call("code.similar", {"code": "x", "source_id": "../etc"}))["error"]["code"] == -32602


# --- read-only by construction ----------------------------------------------------------------------

_MUTATING = ("index", "delete", "clear", "upsert", "remove", "write", "update", "reset", "drop", "insert", "create")


def test_the_tool_surface_is_exactly_the_three_read_tools_and_takes_no_target_to_index():
    assert set(code_graph_tools.CODE_TOOLS) == EXPECTED_TOOLS
    assert {n for n in AutoBotMCPServer.TOOLS if n.startswith("code.")} == EXPECTED_TOOLS
    properties = {p for t in code_graph_tools.CODE_TOOLS.values() for p in t["inputSchema"]["properties"]}
    assert not properties & {"root_path", "ref", "path", "force", "delete", "reindex"}


def test_no_code_path_reachable_from_a_tool_names_a_mutating_operation():
    """Secondary, structural: the end-to-end test below is the one that fails on a real write."""
    handlers = [getattr(code_graph_tools.CodeGraphToolsMixin, "_" + n.replace(".", "_")) for n in EXPECTED_TOOLS]
    queries = [
        getattr(cgq, n) for n in ("resolve_symbol", "query_impact", "query_impact_by_symbol", "find_similar_code")
    ]
    queries += [cgq.open_graph, cgq.load_provenance, cgq.similar_code_answer]
    for fn in handlers + queries:
        offending = [n for n in fn.__code__.co_names if n.lower().startswith(_MUTATING) or n.lower().endswith("_write")]
        assert not offending, f"{fn.__qualname__} reaches {offending}"


def test_the_modules_import_no_indexer_or_deleter():
    for module in (code_graph_tools, cgq):
        assert not [n for n in vars(module) if n.lower().startswith(_MUTATING) and not n.startswith("_")], module
        assert "CodeIndexer" not in vars(module) and "clear_patterns" not in vars(module)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["add", "upsert", "update", "delete", "modify"])
async def test_the_fake_graph_refuses_every_write(method):
    with pytest.raises(AssertionError, match="attempted a write"):
        getattr(FakeGraphCollection(), method)(ids=["x"])


@pytest.mark.asyncio
async def test_running_every_read_tool_end_to_end_never_writes_to_the_graph(_graph):
    """Each tool runs against a graph whose every write raises; a write would surface as an error response."""
    pattern_search = AsyncMock(return_value=[{"pattern_id": "p1"}])
    with (
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=_source(None))),
        patch("code_intelligence.pattern_analysis.CodePatternAnalyzer") as analyzer,
        patch("code_intelligence.pattern_analysis.storage.search_similar_patterns", pattern_search),
    ):
        analyzer.return_value._generate_embedding = AsyncMock(return_value=[0.0])
        for name, arguments in (
            ("code.resolve_symbol", {"symbol": "helper"}),
            ("code.affected", {"symbol": "target"}),
            ("code.affected", {"node_id": "pkg.a.target"}),
            ("code.similar", {"code": "def f(): pass", "source_id": "src-a"}),
        ):
            response = await _call(name, arguments)
            assert "result" in response, (name, response)
            assert "attempted a write" not in json.dumps(response)
    assert _graph.reads > 0 and pattern_search.await_count == 1
