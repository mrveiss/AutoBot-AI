# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge graph's per-codebase nodes: persisted summary, provenance ordering, the code section (#20945)."""

import pytest
from fastapi import HTTPException

from api import knowledge_graph_codebase as cb
from api.codebase_analytics import call_graph_summary as store
from api.codebase_analytics.endpoints.call_graph import CALL_GRAPH_CACHE_TTL
from api.codebase_analytics.source_models import CodeSource, SourceStatus
from api.knowledge_graph_sections import bucket_sections_for_graph
from api.schemas_knowledge_graph import GraphRequest
from tests.fixtures.graph_buckets_fakes_20945 import ListingKB, client_with, viewer

ALPHA = CodeSource(id="src-alpha", name="Alpha", status=SourceStatus.READY, last_synced="2026-11-07T12:00:00")
BETA = CodeSource(id="src-beta", name="Beta", status=SourceStatus.READY, last_synced="2026-11-07T10:00:00")
SYNCING = CodeSource(id="src-syncing", name="Aaa", status=SourceStatus.SYNCING)
BUILT = {
    "summary": {
        "total_functions": 7,
        "total_call_relationships": 9,
        "resolution_rate": 80.0,
        "files_scanned": 3,
        "files_total": 3,
        "truncated": False,
        "top_callers": ["x"],
    }
}
DEPS = {
    "status": "success",
    "dependency_data": {
        "summary": {"total_modules": 3, "total_import_relationships": 4, "circular_dependency_count": 1, "extra": 2}
    },
}


class FakeRedis:
    """An async Redis holding only what the summary store writes; ``ttls`` records each key's expiry."""

    def __init__(self):
        self.data, self.ttls = {}, {}

    async def set(self, key, value, ex=None):
        self.data[key], self.ttls[key] = value, ex

    async def get(self, key):
        return self.data.get(key)


@pytest.fixture
def analytics(monkeypatch, tmp_path):
    """The registry, the index root and the dependency result stood in; the summary store runs for real on FakeRedis."""
    redis = FakeRedis()
    state = {"root": None, "deps_error": {BETA.id}, "sources": [BETA, SYNCING, ALPHA]}

    async def listing(owner):
        return state["sources"]

    async def index_root():
        return state["root"]

    async def cached_deps(prefix, source_id):
        if source_id in state["deps_error"]:
            raise HTTPException(status_code=409, detail="failed")
        return state.get("deps", DEPS)

    async def get_redis(database=None):
        return redis

    monkeypatch.setattr(cb, "list_sources", listing)
    monkeypatch.setattr(cb, "provenance_root_dir", index_root)
    monkeypatch.setattr(cb, "cached_task_result", cached_deps)
    monkeypatch.setattr(store, "get_async_redis_client", get_redis)
    state["redis"], state["tmp"] = redis, tmp_path
    return state


@pytest.mark.asyncio
async def test_the_summary_outlives_the_call_graph_cache_entry(analytics):
    await store.store_call_graph_summary(ALPHA.id, BUILT)
    key = next(iter(analytics["redis"].ttls))
    assert analytics["redis"].ttls[key] > CALL_GRAPH_CACHE_TTL, "the summary must not carry the 5-minute expiry"
    # the 5-minute cache entry is gone (nothing in it is read): the node still reports the persisted summary
    nodes, _ = await cb.codebase_nodes_for_graph(None, viewer(admin=True))
    meta = {n["metadata"]["source_id"]: n["metadata"] for n in nodes}[ALPHA.id]
    assert meta["call_graph"] == {
        "total_functions": 7,
        "total_call_relationships": 9,
        "resolution_rate": 80.0,
        "files_scanned": 3,
        "files_total": 3,
        "truncated": False,
    }
    assert meta["dependencies"] == {
        "total_modules": 3,
        "total_import_relationships": 4,
        "circular_dependency_count": 1,
        "stale": False,
        "completed_at": None,
    }
    assert list(meta)[-2:] == ["call_graph", "dependencies"]


@pytest.mark.asyncio
async def test_a_rebuild_overwrites_the_summary(analytics):
    await store.store_call_graph_summary(ALPHA.id, BUILT)
    await store.store_call_graph_summary(ALPHA.id, {"summary": {**BUILT["summary"], "total_functions": 11}})
    assert (await store.load_call_graph_summary(ALPHA.id))["total_functions"] == 11


def _clone(analytics, source, name):
    path = analytics["tmp"] / name
    path.mkdir()
    return source.model_copy(update={"clone_path": str(path)})


@pytest.mark.asyncio
@pytest.mark.parametrize("root_of, expected", (("beta", "src-beta"), ("alpha", "src-alpha")))
async def test_the_source_cloned_at_the_provenance_root_is_first(analytics, root_of, expected):
    alpha, beta = _clone(analytics, ALPHA, "alpha"), _clone(analytics, BETA, "beta")
    analytics["sources"] = [beta, SYNCING, alpha]
    analytics["root"] = str(analytics["tmp"] / root_of)
    nodes, _ = await cb.codebase_nodes_for_graph(None, viewer(admin=True))
    assert [n["metadata"]["source_id"] for n in nodes][0] == expected
    assert len(nodes) == 2  # the source still syncing is not an indexed codebase


@pytest.mark.asyncio
async def test_without_provenance_the_order_is_by_name_then_id(analytics):
    ids = [s.id for s in await cb.indexed_codebases(None)]
    assert ids == ["src-alpha", "src-beta"]


@pytest.mark.asyncio
async def test_non_admins_get_no_codebase_nodes(analytics):
    assert await cb.codebase_nodes_for_graph(None, viewer(admin=False)) == ([], [])


@pytest.mark.asyncio
async def test_a_codebase_without_a_readable_summary_is_reported_not_analysed(analytics, monkeypatch):
    async def unreadable(source_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(cb, "load_call_graph_summary", unreadable)
    nodes, _ = await cb.codebase_nodes_for_graph(None, viewer(admin=True))
    beta = next(n["metadata"] for n in nodes if n["metadata"]["source_id"] == BETA.id)
    assert beta["analysed"] is False and beta["call_graph"] is None and beta["dependencies"] is None


@pytest.mark.asyncio
async def test_an_unreadable_registry_omits_the_nodes(analytics, monkeypatch):
    async def down(owner):
        raise cb.RegistryUnavailable("down")

    monkeypatch.setattr(cb, "list_sources", down)
    assert await cb.codebase_nodes_for_graph(None, viewer(admin=True)) == ([], [])


async def _graph(kb, offset=0, admin=True):
    nodes, edges, ledger = [], [], viewer(admin=admin).ledger
    sections = await bucket_sections_for_graph(
        kb, GraphRequest(include_buckets=True, offset=offset), nodes, edges, {"id": "u1"}, ledger
    )
    return nodes, edges, sections, ledger


@pytest.mark.asyncio
async def test_the_codebase_nodes_are_inside_the_code_section_and_no_section_of_their_own(analytics):
    await store.store_call_graph_summary(ALPHA.id, BUILT)
    kb = ListingKB([], await client_with({"autobot_code": [("r1", {"k": "v"})]}))
    nodes, edges, sections, _ = await _graph(kb)
    codebases = [n for n in nodes if n["type"] == "codebase"]
    assert len(codebases) == 2 and {n["section"] for n in codebases} == {"code"}
    assert {e["from"] for e in edges if e["to"].startswith("codebase:")} == {"section:code"}
    assert [s["key"] for s in sections] == ["code"], "no separate codebase section"
    assert "section:codebase" not in {n["id"] for n in nodes}
    assert (sections[0]["total"], sections[0]["returned"]) == (3, 3)  # the record + the two codebases


@pytest.mark.asyncio
async def test_the_code_section_exists_for_codebases_when_no_collection_feeds_it(analytics):
    nodes, _, sections, _ = await _graph(ListingKB([], await client_with({})))
    assert [s["key"] for s in sections] == ["code"] and sections[0]["label"] == "Code analysis"
    assert [n["id"] for n in nodes if n["type"] == "section"] == ["section:code"]


@pytest.mark.asyncio
async def test_codebases_are_on_the_first_page_only_and_recorded_in_the_ledger(analytics):
    kb = ListingKB([], await client_with({}))
    _, _, sections, ledger = await _graph(kb)
    assert sorted(ledger.fact_ids) == ["codebase:src-alpha", "codebase:src-beta"]
    nodes, _, paged, paged_ledger = await _graph(kb, offset=50)
    assert not [n for n in nodes if n["type"] == "codebase"] and paged_ledger.fact_ids == []
    assert [(s["key"], s["returned"]) for s in paged] == [("code", 0)]


@pytest.mark.asyncio
async def test_a_codebase_fault_leaves_the_bucket_sections_reporting(analytics, monkeypatch, caplog):
    async def boom(owner):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(cb, "list_sources", boom)
    kb = ListingKB([], await client_with({"autobot_code": [("r1", {"k": "v"})]}))
    with caplog.at_level("WARNING"):
        nodes, _, sections, _ = await _graph(kb)
    assert not any(s.get("failed") for s in sections), sections
    assert not [n for n in nodes if n["type"] == "codebase"]
    assert "Codebase nodes omitted" in caplog.text


@pytest.mark.asyncio
async def test_a_stale_dependency_result_is_marked_stale_on_the_node(analytics):
    analytics["deps_error"] = set()
    analytics["deps"] = {**DEPS, "stale": True, "completed_at": "2026-11-01T08:00:00"}
    nodes, _ = await cb.codebase_nodes_for_graph(None, viewer(admin=True))
    deps = next(n["metadata"]["dependencies"] for n in nodes if n["metadata"]["source_id"] == ALPHA.id)
    assert deps["stale"] is True and deps["completed_at"] == "2026-11-01T08:00:00" and deps["total_modules"] == 3
    analytics["deps"] = {**DEPS, "stale": False, "completed_at": "2026-11-08T08:00:00"}
    nodes, _ = await cb.codebase_nodes_for_graph(None, viewer(admin=True))
    assert nodes[0]["metadata"]["dependencies"]["stale"] is False


RECORDS = [("r1", {"k": "v"}), ("r2", {"k": "v"}), ("r3", {"k": "v"})]


async def _code_total(offset, admin=True):
    kb = ListingKB([], await client_with({"autobot_code": RECORDS}))
    _, _, sections, _ = await _graph(kb, offset=offset, admin=admin)
    return next(s["total"] for s in sections if s["key"] == "code")


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", (1, 50))
async def test_the_code_section_total_is_the_same_on_every_page(analytics, offset):
    assert await _code_total(0) == await _code_total(offset) == 5  # 3 records + 2 codebases, whatever the page


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", (0, 1))
async def test_a_non_admin_total_is_the_records_only_on_every_page(analytics, offset):
    assert await _code_total(offset, admin=False) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", (0, 1))
async def test_an_unavailable_registry_total_is_the_records_only_on_every_page(analytics, monkeypatch, offset):
    async def down(owner):
        raise cb.RegistryUnavailable("down")

    monkeypatch.setattr(cb, "list_sources", down)
    assert await _code_total(offset) == 3


@pytest.mark.asyncio
async def test_a_codebase_count_fault_on_a_later_page_leaves_the_sections_reporting(analytics, monkeypatch, caplog):
    async def boom(user):
        raise RuntimeError("count exploded")

    monkeypatch.setattr(cb, "indexed_codebases", boom)
    kb = ListingKB([], await client_with({"autobot_code": RECORDS}))
    with caplog.at_level("WARNING"):
        _, _, sections, _ = await _graph(kb, offset=1)
    assert sections and not any(s.get("failed") for s in sections), sections
    assert "Codebase nodes omitted" in caplog.text
