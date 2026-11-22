# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The code-graph query service, and the proof the routes call it rather than a copy (#21327).

Runs the real resolver, the real ``find_impact`` walk and the real provenance reader against a
read-only fake collection, so the answers asserted are the persisted graph's, known by
construction: ``top -> caller -> target`` is the only call chain, and ``helper`` is defined twice.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response

from api.codebase_analytics import code_graph_queries as cgq
from api.codebase_analytics.endpoints import impact
from autobot_shared.code_graph.commit_freshness import freshness_of
from testkit.fake_graph_collection import DEFAULT_COMMIT, FakeGraphCollection, sample_records
from testkit.pattern_store_fakes import install_pattern_fakes


@pytest.fixture
def graph():
    collection = FakeGraphCollection()
    with patch.object(cgq, "get_existing_code_graph_collection", return_value=collection):
        yield collection


def _body(response) -> dict:
    return json.loads(response.body)


# --- symbol resolution --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_unique_bare_name_resolves_to_its_node_id(graph):
    answer = await cgq.resolve_symbol("target")
    assert (answer["status"], answer["node_id"], answer["matched_by"]) == ("resolved", "pkg.a.target", "name")


@pytest.mark.asyncio
async def test_an_ambiguous_name_returns_every_candidate_and_picks_none(graph):
    answer = await cgq.resolve_symbol("helper")
    assert answer["status"] == "ambiguous"
    assert answer["node_id"] is None
    assert [c["node_id"] for c in answer["candidates"]] == ["pkg.a.helper", "pkg.b.helper"]
    assert answer["candidate_count"] == 2 and answer["truncated"] is False


@pytest.mark.asyncio
async def test_a_qualified_name_disambiguates_by_suffix(graph):
    assert (await cgq.resolve_symbol("a.helper"))["node_id"] == "pkg.a.helper"
    method = await cgq.resolve_symbol("Widget.render")
    assert (method["node_id"], method["matched_by"]) == ("pkg.c.Widget.render", "qualified_name")


@pytest.mark.asyncio
async def test_a_qualified_name_never_matches_inside_a_longer_name(graph):
    assert (await cgq.resolve_symbol("ar.helper"))["status"] == "not_found"


@pytest.mark.asyncio
async def test_an_exact_node_id_wins(graph):
    answer = await cgq.resolve_symbol("pkg.b.helper")
    assert (answer["status"], answer["node_id"], answer["matched_by"]) == ("resolved", "pkg.b.helper", "node_id")


@pytest.mark.asyncio
async def test_an_unknown_symbol_is_not_found_not_an_empty_success(graph):
    answer = await cgq.resolve_symbol("no_such_symbol")
    assert (answer["status"], answer["node_id"], answer["candidates"], answer["matched_by"]) == (
        "not_found",
        None,
        [],
        None,
    )
    assert answer["indexed"] is True


@pytest.mark.asyncio
async def test_candidates_are_cut_and_flagged_past_the_limit():
    many = [(f"m{i}.dup", {"record_type": "node", "node_name": "dup", "node_kind": "function"}) for i in range(60)]
    with patch.object(cgq, "get_existing_code_graph_collection", return_value=FakeGraphCollection(many)):
        answer = await cgq.resolve_symbol("dup")
    assert len(answer["candidates"]) == cgq.RESOLVE_MAX_CANDIDATES
    assert answer["candidate_count"] == 60 and answer["truncated"] is True


@pytest.mark.asyncio
async def test_an_empty_or_missing_graph_is_unindexed_not_not_found():
    with patch.object(cgq, "get_existing_code_graph_collection", return_value=FakeGraphCollection([])):
        assert (await cgq.resolve_symbol("target"))["indexed"] is False
    with patch.object(cgq, "get_existing_code_graph_collection", return_value=None):
        assert (await cgq.query_impact("pkg.a.target"))["indexed"] is False


def test_the_read_accessor_never_creates_the_collection():
    """A read of a graph that was never built must leave it never built, not create an empty one."""
    from api.codebase_analytics import storage

    client = SimpleNamespace(
        get_collection=MagicMock(side_effect=ValueError("does not exist")), get_or_create_collection=MagicMock()
    )
    with (
        patch.object(storage, "get_default_client", return_value=client),
        patch.object(storage, "chromadb_data_dir", return_value="unused"),
    ):
        assert storage.get_existing_code_graph_collection() is None
    client.get_or_create_collection.assert_not_called()


# --- impact and provenance -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_impact_by_symbol_walks_the_transitive_callers_and_names_the_commit(graph):
    answer = await cgq.query_impact_by_symbol("target")
    assert answer["reached"] == ["pkg.b.caller", "pkg.d.top"]
    assert answer["root_id"] == "pkg.a.target" and answer["depth_capped"] is False
    assert answer["indexed_at_commit"] == DEFAULT_COMMIT
    assert answer["source_scope"] == "cross-source" and answer["index_root"] == "project"


@pytest.mark.asyncio
async def test_impact_by_an_ambiguous_symbol_returns_the_candidates_and_no_walk(graph):
    answer = await cgq.query_impact_by_symbol("helper")
    assert answer["status"] == "ambiguous" and answer["impact"] is None
    assert "reached" not in answer and len(answer["candidates"]) == 2


@pytest.mark.asyncio
async def test_impact_by_an_unknown_symbol_is_not_found(graph):
    answer = await cgq.query_impact_by_symbol("no_such_symbol")
    assert answer["status"] == "not_found" and "reached" not in answer


@pytest.mark.asyncio
async def test_a_different_expected_commit_flags_the_answer_stale(graph):
    answer = await cgq.query_impact("pkg.a.target", expected_commit="0" * 40)
    assert (answer["stale"], answer["freshness"]) == (True, "stale")
    assert answer["expected_commit"] == "0" * 40 and answer["reached"]


@pytest.mark.asyncio
async def test_the_matching_commit_full_or_abbreviated_is_current(graph):
    for expected in (DEFAULT_COMMIT, DEFAULT_COMMIT[:9].upper()):
        answer = await cgq.query_impact("pkg.a.target", expected_commit=expected)
        assert (answer["stale"], answer["freshness"]) == (False, "current")


@pytest.mark.asyncio
async def test_no_expectation_is_unchecked_never_current(graph):
    answer = await cgq.resolve_symbol("target")
    assert (answer["stale"], answer["freshness"]) == (None, "unchecked")


@pytest.mark.asyncio
async def test_a_graph_without_a_provenance_record_is_unknown_never_current():
    collection = FakeGraphCollection(sample_records(commit=None))
    with patch.object(cgq, "get_existing_code_graph_collection", return_value=collection):
        answer = await cgq.query_impact("pkg.a.target", expected_commit=DEFAULT_COMMIT)
    assert (answer["indexed_at_commit"], answer["stale"], answer["freshness"]) == (None, None, "unknown")


def test_a_malformed_expected_commit_is_refused():
    with pytest.raises(ValueError):
        freshness_of(DEFAULT_COMMIT, "not-a-commit")


@pytest.mark.asyncio
async def test_the_read_paths_never_write(graph):
    await cgq.resolve_symbol("helper")
    await cgq.query_impact_by_symbol("target")
    assert graph.reads > 0  # a write attempt raises inside the fake; reaching here means none was made


# --- similar code --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_similar_code_embeds_the_snippet_and_scopes_the_search_to_the_source(monkeypatch):
    hits = [{"pattern_id": "p1", "similarity": 0.9}]
    search = AsyncMock(return_value=hits)
    analyzer = MagicMock()
    analyzer.return_value._generate_embedding = AsyncMock(return_value=[1.0])
    install_pattern_fakes(monkeypatch, analyzer=analyzer, search=search)
    assert await cgq.find_similar_code("def f(): pass", "src-a", "dup", 5) == hits
    search.assert_awaited_once_with(query_embedding=[1.0], pattern_type="dup", n_results=5, source_id="src-a")


def test_similar_code_answer_records_no_commit_so_an_expectation_is_unknown():
    answer = cgq.similar_code_answer([{"id": 1}], "src-a", DEFAULT_COMMIT)
    assert (answer["indexed_at_commit"], answer["stale"], answer["freshness"]) == (None, None, "unknown")
    assert answer["source_id"] == "src-a" and answer["count"] == 1


# --- the routes delegate: same function, same answer ----------------------------------------------


def test_the_impact_route_returns_exactly_what_the_service_returns(graph):
    route = _body(
        asyncio.run(
            impact.analyze_impact(node_id="pkg.a.target", symbol=None, max_depth=None, expected_commit="0" * 40)
        )
    )
    service = asyncio.run(cgq.query_impact("pkg.a.target", None, "0" * 40))
    assert route == service


def test_the_impact_route_resolves_a_symbol_exactly_as_the_service_does(graph):
    route = _body(
        asyncio.run(impact.analyze_impact(node_id=None, symbol="target", max_depth=None, expected_commit=None))
    )
    assert route == asyncio.run(cgq.query_affected(symbol="target"))
    assert route["reached"] == ["pkg.b.caller", "pkg.d.top"]
    ambiguous = _body(asyncio.run(impact.analyze_impact(node_id=None, symbol="helper", max_depth=None)))
    assert ambiguous["status"] == "ambiguous" and "reached" not in ambiguous


@pytest.mark.parametrize("target", [{}, {"node_id": "pkg.a.target", "symbol": "target"}])
def test_the_impact_route_needs_exactly_one_of_node_id_or_symbol(graph, target):
    with pytest.raises(HTTPException) as caught:
        asyncio.run(impact.analyze_impact(**{"node_id": None, "symbol": None, "max_depth": None, **target}))
    assert caught.value.status_code == 422


@pytest.mark.asyncio
async def test_the_service_entry_point_refuses_neither_and_both():
    for target in ({}, {"node_id": "a", "symbol": "b"}):
        with pytest.raises(ValueError):
            await cgq.query_affected(**target)


def test_the_impact_module_holds_no_second_implementation_of_the_walk():
    """The route imports the service functions; it does not import the engine or the graph store itself."""
    for name in ("find_impact", "get_existing_code_graph_collection", "load_graph_provenance", "find_callers"):
        assert not hasattr(impact, name), f"endpoints/impact.py re-implements the query via {name}"
    assert impact.query_affected is cgq.query_affected


def test_the_similar_route_returns_what_the_service_returns():
    from api.codebase_analytics.endpoints import pattern_analysis

    hits = [{"pattern_id": "p1"}]
    find = AsyncMock(return_value=hits)
    with patch.object(pattern_analysis, "find_similar_code", find):
        route = asyncio.run(
            pattern_analysis.search_similar_patterns_endpoint(
                source_id="src-a", response=Response(), code="x = 1", pattern_type=None, limit=3
            )
        )
    assert route == hits
    find.assert_awaited_once_with("x = 1", "src-a", None, 3)


def test_the_similar_route_imports_the_service_function_itself():
    from api.codebase_analytics.endpoints import pattern_analysis

    assert pattern_analysis.find_similar_code is cgq.find_similar_code


def test_a_service_failure_surfaces_as_a_500_on_the_similar_route():
    from api.codebase_analytics.endpoints import pattern_analysis

    with patch.object(pattern_analysis, "find_similar_code", AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(
                pattern_analysis.search_similar_patterns_endpoint(
                    source_id="src-a", response=Response(), code="x", pattern_type=None, limit=3
                )
            )
    assert caught.value.status_code == 500
