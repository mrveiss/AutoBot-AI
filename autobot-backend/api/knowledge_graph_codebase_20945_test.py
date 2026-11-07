# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The graph's codebase section: AutoBot's own code first, reusing the analytics services (#20945)."""

import pytest
from fastapi import HTTPException

from api import knowledge_graph_codebase as cb
from api.codebase_analytics.source_models import CodeSource, SourceStatus
from api.knowledge_graph_sections import graph_sections
from api.schemas_knowledge_graph import GraphRequest

AUTOBOT = CodeSource(id="src-autobot", name="AutoBot", status=SourceStatus.READY, last_synced="2026-11-07T10:00:00")
OTHER = CodeSource(id="src-other", name="Other", status=SourceStatus.READY, last_synced="2026-11-07T12:00:00")
SYNCING = CodeSource(id="src-syncing", name="Syncing", status=SourceStatus.SYNCING)
CALL_GRAPH = {
    "summary": {
        "total_functions": 7,
        "total_call_relationships": 9,
        "resolution_rate": 80.0,
        "files_scanned": 3,
        "truncated": False,
        "top_callers": ["x"],
    }
}
DEPS = {
    "status": "success",
    "dependency_data": {
        "summary": {
            "total_modules": 3,
            "total_import_relationships": 4,
            "circular_dependency_count": 1,
            "external_dependency_count": 2,
        }
    },
}


@pytest.fixture
def analytics(monkeypatch):
    """Stand in for the registry and the two analytics caches; the section must only read them."""
    seen = {"call_graph_roots": [], "deps": []}

    async def default_id():
        return AUTOBOT.id  # the most recently INDEXED, not the most recently listed

    async def listing(owner):
        return [OTHER, SYNCING, AUTOBOT]

    async def root(source_id):
        return f"/root/{source_id}"

    async def cached_graph(root_path):
        seen["call_graph_roots"].append(root_path)
        return CALL_GRAPH if root_path.endswith(AUTOBOT.id) else None

    async def cached_deps(prefix, source_id):
        seen["deps"].append((prefix, source_id))
        if source_id == OTHER.id:
            raise HTTPException(status_code=409, detail="failed")
        return DEPS

    for name, fn in (
        ("get_default_source_id", default_id),
        ("list_sources", listing),
        ("resolve_scan_root", root),
        ("_get_cached_call_graph", cached_graph),
        ("cached_task_result", cached_deps),
    ):
        monkeypatch.setattr(cb, name, fn)
    return seen


@pytest.mark.asyncio
async def test_autobot_code_is_first_and_unindexed_sources_are_left_out(analytics):
    nodes, edges = [{"id": "fact:1", "type": "fact"}], []
    report = await cb.codebase_section_for_graph(nodes, edges, {"id": "u1"}, True)
    assert [n["id"] for n in nodes[:4]] == ["section:codebase", "codebase:src-autobot", "codebase:src-other", "fact:1"]
    assert nodes[1]["metadata"]["is_autobot"] is True and nodes[2]["metadata"]["is_autobot"] is False
    assert [e["to"] for e in edges] == ["codebase:src-autobot", "codebase:src-other"]
    assert report == [{"key": "codebase", "label": "Codebases", "total": 2, "returned": 2, "limited": False}]


@pytest.mark.asyncio
async def test_summaries_come_from_the_analytics_caches_call_graph_first(analytics):
    nodes: list = []
    await cb.codebase_section_for_graph(nodes, [], None, True)
    meta = nodes[1]["metadata"]
    assert list(meta)[-2:] == ["call_graph", "dependencies"]
    assert meta["call_graph"] == {
        "total_functions": 7,
        "total_call_relationships": 9,
        "resolution_rate": 80.0,
        "files_scanned": 3,
        "truncated": False,
    }
    assert meta["dependencies"] == {"total_modules": 3, "total_import_relationships": 4, "circular_dependency_count": 1}
    assert analytics["deps"][0] == (cb.DEPENDENCIES_PREFIX, AUTOBOT.id)


@pytest.mark.asyncio
async def test_a_codebase_not_analysed_yet_is_listed_with_empty_summaries(analytics):
    nodes: list = []
    await cb.codebase_section_for_graph(nodes, [], None, True)
    other = nodes[2]["metadata"]  # no cached call graph, and its dependency scan failed
    assert other["call_graph"] is None and other["dependencies"] is None and other["source_id"] == "src-other"


@pytest.mark.asyncio
async def test_non_admins_get_no_codebase_section(analytics):
    nodes: list = []
    assert await cb.codebase_section_for_graph(nodes, [], None, False) == []
    assert nodes == []


@pytest.mark.asyncio
async def test_an_unreadable_registry_omits_the_section(monkeypatch, analytics):
    async def down():
        raise cb.RegistryUnavailable("down")

    monkeypatch.setattr(cb, "get_default_source_id", down)
    nodes: list = []
    assert await cb.codebase_section_for_graph(nodes, [], None, True) == []


@pytest.mark.asyncio
async def test_graph_sections_lists_codebase_before_facts_and_only_on_the_first_page(analytics, monkeypatch):
    async def facts(kb, returned, offset):
        return {"key": "facts"}

    monkeypatch.setattr("api.knowledge_graph_sections.facts_section", facts)
    body = GraphRequest(include_buckets=True)
    first = await graph_sections(None, body, [], [], True, 0, {"id": "u1"})
    assert [s["key"] for s in first] == ["codebase", "facts"]
    paged = await graph_sections(None, GraphRequest(offset=50), [], [], True, 0, {"id": "u1"})
    assert [s["key"] for s in paged] == ["facts"]
