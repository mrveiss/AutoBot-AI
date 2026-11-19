# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The graph's codebase section: newest-synced code first, reusing the analytics services (#20945)."""

import pytest
from fastapi import HTTPException

from api import knowledge_graph_codebase as cb
from api.codebase_analytics.source_models import CodeSource, SourceStatus
from api.knowledge_graph_facts import FactsPage
from api.knowledge_graph_sections import graph_sections
from api.schemas_knowledge_graph import GraphRequest
from knowledge.graph_bucket_visibility import Viewer
from knowledge.root_read import AdminReadLedger


def _viewer(admin: bool = True) -> Viewer:
    return Viewer("u1", None, (), AdminReadLedger() if admin else False)


LEDGER = AdminReadLedger()
AUTOBOT = CodeSource(id="src-autobot", name="AutoBot", status=SourceStatus.READY, last_synced="2026-11-07T12:00:00")
OTHER = CodeSource(id="src-other", name="Other", status=SourceStatus.READY, last_synced="2026-11-07T10:00:00")
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
        ("list_sources", listing),
        ("resolve_scan_root", root),
        ("_get_cached_call_graph", cached_graph),
        ("cached_task_result", cached_deps),
    ):
        monkeypatch.setattr(cb, name, fn)
    return seen


@pytest.mark.asyncio
async def test_newest_synced_code_is_first_and_unindexed_sources_are_left_out(analytics):
    nodes, edges = [{"id": "fact:1", "type": "fact"}], []
    report = await cb.codebase_section_for_graph(nodes, edges, {"id": "u1"}, _viewer())
    assert [n["id"] for n in nodes[:4]] == ["section:codebase", "codebase:src-autobot", "codebase:src-other", "fact:1"]
    assert [e["to"] for e in edges] == ["codebase:src-autobot", "codebase:src-other"]
    assert report == [
        {
            "key": "codebase",
            "label": "Codebases",
            "total": 2,
            "returned": 2,
            "limited": False,
            "truncated": False,
            "budget_exhausted": False,
            "failed": False,
        }
    ]


@pytest.mark.asyncio
async def test_summaries_come_from_the_analytics_caches_call_graph_first(analytics):
    nodes: list = []
    await cb.codebase_section_for_graph(nodes, [], None, _viewer())
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
    await cb.codebase_section_for_graph(nodes, [], None, _viewer())
    other = nodes[2]["metadata"]  # no cached call graph, and its dependency scan failed
    assert other["call_graph"] is None and other["dependencies"] is None and other["source_id"] == "src-other"


@pytest.mark.asyncio
async def test_non_admins_get_no_codebase_section(analytics):
    nodes: list = []
    assert await cb.codebase_section_for_graph(nodes, [], None, _viewer(False)) == []
    assert nodes == []


@pytest.mark.asyncio
async def test_an_unreadable_registry_omits_the_section(monkeypatch, analytics):
    async def down():
        raise cb.RegistryUnavailable("down")

    monkeypatch.setattr(cb, "list_sources", lambda owner: down())
    nodes: list = []
    assert await cb.codebase_section_for_graph(nodes, [], None, _viewer()) == []


@pytest.mark.asyncio
async def test_graph_sections_lists_codebase_before_facts_and_only_on_the_first_page(analytics, monkeypatch):
    def facts(page, offset):
        return {"key": "facts"}

    monkeypatch.setattr("api.knowledge_graph_sections.facts_section", facts)
    body = GraphRequest(include_buckets=True)
    first = await graph_sections(None, body, [], [], LEDGER, FactsPage(), {"id": "u1", "role": "admin"})
    assert [s["key"] for s in first] == ["codebase", "facts"]
    paged = await graph_sections(
        None, GraphRequest(offset=50), [], [], LEDGER, FactsPage(), {"id": "u1", "role": "admin"}
    )
    assert [s["key"] for s in paged] == ["facts"]


@pytest.mark.asyncio
async def test_an_admin_read_of_the_codebase_section_is_recorded_in_the_ledger(analytics):
    viewer = _viewer()
    await cb.codebase_section_for_graph([], [], None, viewer)
    assert viewer.ledger.fact_ids == ["codebase:src-autobot", "codebase:src-other"]
