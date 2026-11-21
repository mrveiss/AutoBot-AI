# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A KB write orphans the semantic and topic retrieval caches, and every write path is wired (#20958)."""

import ast
import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.testfile_names import is_test_filename
from knowledge.acl_epoch import ACL_EPOCH_KEY
from knowledge.retrieval_invalidation import (
    COMPOSED,
    WRITE_ENTRY_POINTS,
    invalidate_retrieval_caches,
    invalidates_retrieval_caches,
    invalidating_writes,
)
from knowledge.search_filters import SYSTEM_SCOPE
from services.rag_visibility import cache_scope
from services.topic_retrieval_cache import CachedChunk
from tests.fixtures.rag_cache_fakes import make_semantic_cache, make_topic_cache

BACKEND = Path(__file__).resolve().parent.parent
VECTOR = [0.1, 0.2, 0.3]
DECORATOR = "invalidates_retrieval_caches"
CONCURRENT_SEARCHES = 5
FAILED_RETRIES = 20


class _Kv:
    """The knowledge-database epoch key: async get / SET NX, as ``read_epoch_token`` uses it."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.reject_writes = False
        self.set_calls = 0
        self.hold_replies: list[asyncio.Event] = []  # the next SET lands, then waits for its event
        self.parked = asyncio.Event()  # set once a SET is waiting on its reply

    async def get(self, key):
        return self.data[key].encode() if key in self.data else None

    async def set(self, key, value, nx=False):
        if self.reject_writes:
            raise ConnectionError("READONLY You can't write against a read only replica")
        self.set_calls += 1
        if not (nx and key in self.data):
            self.data[key] = value
        if self.hold_replies:
            gate = self.hold_replies.pop(0)
            self.parked.set()
            await gate.wait()


@pytest.fixture(autouse=True)
def _no_pending_marker():
    """The pending marker, failure generation, in-flight guard and suppressed count are module state."""
    with patch.multiple(
        "knowledge.retrieval_invalidation", _pending=False, _failures=0, _retry_in_flight=False, _suppressed=0
    ):
        yield


@pytest.fixture
def kv():
    store = _Kv()
    getter = AsyncMock(return_value=store)
    with (
        patch("knowledge.acl_epoch.get_async_redis_client", new=getter),
        patch("knowledge.retrieval_invalidation.get_async_redis_client", new=getter),
    ):
        yield store


async def _fill(semantic, topic, scope):
    assert await semantic.store("q", "answer", "rag", embedding=VECTOR, scope=scope)
    assert await topic.store([VECTOR], [CachedChunk("chunk", {}, 0.9)], scope=scope)


async def _served(semantic, topic, scope) -> bool:
    hit_semantic = await semantic.lookup("q", embedding=VECTOR, scope=scope)
    return hit_semantic is not None and await topic.lookup(VECTOR, scope=scope) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", sorted({e.reason for e in WRITE_ENTRY_POINTS}))
async def test_a_cached_result_is_not_served_after_each_kind_of_write(kv, reason):
    semantic, topic = make_semantic_cache(), make_topic_cache()
    before = await cache_scope(SYSTEM_SCOPE)
    await _fill(semantic, topic, before)
    assert await _served(semantic, topic, before), "control: the entry is served before the write"

    @invalidates_retrieval_caches(reason)
    async def write() -> str:
        return "written"

    assert await write() == "written"

    after = await cache_scope(SYSTEM_SCOPE)
    assert after != before
    assert not await _served(semantic, topic, after), f"stale result served after a {reason} write"


@pytest.mark.asyncio
async def test_a_write_that_raises_still_invalidates_because_it_may_have_changed_the_store(kv):
    before = await cache_scope(SYSTEM_SCOPE)

    @invalidates_retrieval_caches("fact_updated")
    async def write() -> None:
        raise RuntimeError("half-way")

    with pytest.raises(RuntimeError):
        await write()
    assert await cache_scope(SYSTEM_SCOPE) != before


@pytest.mark.asyncio
async def test_a_failed_bump_is_reported_not_raised_and_never_changes_the_write_result():
    with patch("knowledge.retrieval_invalidation.get_async_redis_client", new=AsyncMock(return_value=None)):
        assert await invalidate_retrieval_caches("fact_added") is False

        @invalidates_retrieval_caches("fact_added")
        async def write() -> str:
            return "stored"

        assert await write() == "stored"


@pytest.mark.asyncio
async def test_each_bump_is_a_fresh_token_in_the_acl_epoch_key(kv):
    assert await invalidate_retrieval_caches("fact_added")
    first = kv.data[ACL_EPOCH_KEY]
    assert await invalidate_retrieval_caches("fact_deleted")
    assert kv.data[ACL_EPOCH_KEY] != first


@pytest.mark.asyncio
async def test_a_rejected_bump_with_working_reads_bypasses_the_cache_instead_of_keeping_the_old_scope(kv):
    semantic, topic = make_semantic_cache(), make_topic_cache()
    before = await cache_scope(SYSTEM_SCOPE)
    await _fill(semantic, topic, before)
    kv.reject_writes = True

    @invalidates_retrieval_caches("fact_updated")
    async def write() -> str:
        return "written"

    assert await write() == "written"
    assert await cache_scope(SYSTEM_SCOPE) is None, "the pre-write epoch must not stay usable"
    assert await semantic.lookup("q", embedding=VECTOR, scope=None) is None
    assert await topic.lookup(VECTOR, scope=None) is None


@pytest.mark.asyncio
async def test_a_later_successful_bump_restores_caching_under_the_new_epoch(kv):
    semantic, topic = make_semantic_cache(), make_topic_cache()
    before = await cache_scope(SYSTEM_SCOPE)
    await _fill(semantic, topic, before)
    kv.reject_writes = True
    assert await invalidate_retrieval_caches("fact_updated") is False
    assert await cache_scope(SYSTEM_SCOPE) is None, "still rejected: the retry fails and the bypass holds"

    kv.reject_writes = False
    after = await cache_scope(SYSTEM_SCOPE)  # the retry inside the call succeeds
    assert after is not None and after != before
    assert await semantic.lookup("q", embedding=VECTOR, scope=after) is None, "nothing from the old epoch"
    assert await topic.lookup(VECTOR, scope=after) is None, "nothing from the old epoch"
    await _fill(semantic, topic, after)
    assert await semantic.lookup("q", embedding=VECTOR, scope=after) is not None
    assert await topic.lookup(VECTOR, scope=after) is not None
    assert await cache_scope(SYSTEM_SCOPE) == after, "no bump once the marker is clear"


@pytest.mark.asyncio
async def test_a_late_success_cannot_clear_a_newer_failed_bump(kv):
    gate = asyncio.Event()
    kv.hold_replies.append(gate)
    bump_a = asyncio.create_task(invalidate_retrieval_caches("fact_added"))
    await kv.parked.wait()  # A's SET has landed (epoch tA); its reply is delayed
    epoch_a = kv.data[ACL_EPOCH_KEY]
    semantic, topic = make_semantic_cache(), make_topic_cache()
    scope_a = await cache_scope(SYSTEM_SCOPE)
    await _fill(semantic, topic, scope_a)  # pre-write results cached under tA
    kv.reject_writes = True
    assert await invalidate_retrieval_caches("fact_updated") is False  # write W's bump B fails
    gate.set()
    assert await bump_a is True  # A's late success must not clear B's failure
    assert await cache_scope(SYSTEM_SCOPE) is None, "still pending: no pre-write entry may be served"
    assert not await _served(semantic, topic, None)

    kv.reject_writes = False
    fresh = await cache_scope(SYSTEM_SCOPE)  # a bump that started after B's failure clears it
    assert fresh is not None and fresh != scope_a
    assert kv.data[ACL_EPOCH_KEY] != epoch_a
    assert not await _served(semantic, topic, fresh)


@pytest.mark.asyncio
async def test_concurrent_searches_while_pending_issue_exactly_one_retry(kv):
    kv.reject_writes = True
    assert await invalidate_retrieval_caches("fact_added") is False
    kv.reject_writes = False
    kv.set_calls = 0
    gate = asyncio.Event()
    kv.hold_replies.append(gate)
    tasks = [asyncio.create_task(cache_scope(SYSTEM_SCOPE)) for _ in range(CONCURRENT_SEARCHES)]
    await kv.parked.wait()  # the one retry is in flight
    assert await asyncio.gather(*tasks[1:]) == [None] * (CONCURRENT_SEARCHES - 1)
    gate.set()
    assert await tasks[0] is not None
    assert kv.set_calls == 1


@pytest.mark.asyncio
async def test_a_rejecting_redis_logs_the_transitions_not_every_failed_retry(kv, caplog):
    kv.reject_writes = True
    with caplog.at_level(logging.DEBUG):
        assert await invalidate_retrieval_caches("fact_added") is False
        for _ in range(FAILED_RETRIES):
            assert await cache_scope(SYSTEM_SCOPE) is None
        kv.reject_writes = False
        assert await cache_scope(SYSTEM_SCOPE) is not None
        assert await cache_scope(SYSTEM_SCOPE) is not None
    loud = [r for r in caplog.records if r.name.endswith("retrieval_invalidation") and r.levelno >= logging.INFO]
    assert [r.levelno for r in loud] == [logging.WARNING, logging.INFO]
    assert f"{FAILED_RETRIES} failures suppressed" in loud[1].getMessage()


@pytest.mark.asyncio
async def test_a_working_bump_leaves_no_pending_marker_and_scopes_stay_stable(kv):
    assert await invalidate_retrieval_caches("fact_added") is True
    scope = await cache_scope(SYSTEM_SCOPE)
    assert scope is not None
    assert await cache_scope(SYSTEM_SCOPE) == scope


def test_the_decorator_refuses_a_sync_function():
    with pytest.raises(TypeError):
        invalidates_retrieval_caches("fact_added")(lambda: None)


@pytest.mark.asyncio
async def test_the_class_decorator_wraps_only_the_registered_methods_of_that_class(kv):
    methods = {e.qualname.split(".")[1] for e in WRITE_ENTRY_POINTS if e.path == COMPOSED}

    async def noop(self):
        return 1

    async def search(self):
        return 2

    cls = invalidating_writes(type("KnowledgeBase", (), {**dict.fromkeys(methods, noop), "search": search}))
    before = await cache_scope(SYSTEM_SCOPE)
    assert await cls().search() == 2
    assert await cache_scope(SYSTEM_SCOPE) == before, "a read must not invalidate"
    assert await cls().store_fact() == 1
    assert await cache_scope(SYSTEM_SCOPE) != before


def test_the_composed_knowledge_base_really_wraps_every_registered_method():
    from knowledge._composed import KnowledgeBase

    for entry in (e for e in WRITE_ENTRY_POINTS if e.path == COMPOSED):
        method = getattr(KnowledgeBase, entry.qualname.split(".")[1])
        assert hasattr(method, "__wrapped__"), f"{entry.qualname} is not wrapped"


# ---- the guard: every KB write entry point reaches the hook -------------------------------------


def _tree(path: str) -> ast.Module:
    return ast.parse((BACKEND / path).read_text(encoding="utf-8"))


def _decorator_reasons(node: ast.AST, name: str) -> list[str]:
    """First-argument literals of every ``@name("reason")`` on *node*."""
    return [
        d.args[0].value
        for d in getattr(node, "decorator_list", [])
        if isinstance(d, ast.Call) and getattr(d.func, "id", None) == name and d.args
    ]


def _find(tree: ast.AST, qualname: str) -> ast.AST | None:
    node: ast.AST | None = tree
    for part in qualname.split("."):
        node = next(
            (
                c
                for c in ast.walk(node)
                if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and c.name == part
            ),
            None,
        )
        if node is None:
            return None
    return node


def _mixin_defines(method: str) -> bool:
    return any(
        isinstance(n, ast.AsyncFunctionDef) and n.name == method and n.body and not _raises_not_implemented(n)
        for p in (BACKEND / "knowledge").glob("*.py")
        if not is_test_filename(p.name)
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
    )


def _raises_not_implemented(fn: ast.AsyncFunctionDef) -> bool:
    return any(isinstance(n, ast.Raise) and "NotImplementedError" in ast.unparse(n) for n in ast.walk(fn))


@pytest.mark.parametrize("entry", WRITE_ENTRY_POINTS, ids=lambda e: f"{e.path}:{e.qualname}")
def test_every_registered_write_entry_point_is_wired_to_the_hook(entry):
    tree = _tree(entry.path)
    if entry.path == COMPOSED:
        cls_name, _, method = entry.qualname.partition(".")
        cls = _find(tree, cls_name)
        assert cls is not None and any(
            getattr(d, "id", None) == "invalidating_writes" for d in cls.decorator_list
        ), f"{cls_name} lost @invalidating_writes"
        assert _mixin_defines(method), f"no mixin implements {method}"
        return
    node = _find(tree, entry.qualname)
    assert isinstance(node, ast.AsyncFunctionDef), f"{entry.qualname} is missing from {entry.path}"
    assert entry.reason in _decorator_reasons(node, DECORATOR), f"{entry.qualname} must carry @{DECORATOR}"


def _decorated_functions() -> set[tuple[str, str]]:
    found = set()
    for sub in ("knowledge", "services", "api"):
        for path in (BACKEND / sub).rglob("*.py"):
            if is_test_filename(path.name) or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if DECORATOR not in text:
                continue
            rel = str(path.relative_to(BACKEND))
            for fn in (n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.AsyncFunctionDef)):
                if _decorator_reasons(fn, DECORATOR):
                    found.add((rel, fn.name))
    return found


def test_no_function_uses_the_hook_without_being_registered():
    registered = {(e.path, e.qualname.rsplit(".", 1)[-1]) for e in WRITE_ENTRY_POINTS}
    unregistered = _decorated_functions() - registered - {("knowledge/retrieval_invalidation.py", "wrapper")}
    assert not unregistered, f"add to WRITE_ENTRY_POINTS: {sorted(unregistered)}"


#: Where a raw vector write may sit. "entry" = a registered entry point; anything else says why the
#: write cannot change a RAG answer or which entry point covers it. A new site must be added here.
_ENTRY = "entry"
_BACKEND_ADAPTER = "storage adapter: its callers are the registered entry points or non-RAG collections"
_NOT_RAG = "collection the RAG service does not read (it reads KB facts, autobot_docs and kb_synthesis*)"
_VECTOR_WRITES: dict[tuple[str, str], str] = {
    ("api/knowledge_vectorization.py", "_upsert_enriched_chunks"): _NOT_RAG,
    ("knowledge/backends/async_chromadb_adapter.py", "delete_collection"): _BACKEND_ADAPTER,
    ("knowledge/backends/async_chromadb_adapter.py", "upsert"): _BACKEND_ADAPTER,
    ("knowledge/backends/async_memory_adapter.py", "delete_collection"): _BACKEND_ADAPTER,
    ("knowledge/backends/async_memory_adapter.py", "upsert"): _BACKEND_ADAPTER,
    ("knowledge/backends/chromadb_adapter.py", "delete_collection"): _BACKEND_ADAPTER,
    ("knowledge/backends/chromadb_adapter.py", "upsert"): _BACKEND_ADAPTER,
    ("knowledge/facts.py", "_delete_fact_from_vector_store"): "KnowledgeBase.delete_fact / delete_facts_by_session",
    ("knowledge/facts.py", "_revectorize_fact"): "KnowledgeBase.update_fact",
    ("knowledge/facts.py", "_write_vector"): "KnowledgeBase.store_fact / update_fact (+ write_buffer flush)",
    ("knowledge/index.py", "_prepare_target_collection"): "HNSW rebuild copies the same vectors: content is unchanged",
    ("knowledge/pipeline/loaders/chromadb_loader.py", "_upsert_chunk_batch"): _NOT_RAG,
    ("knowledge/pipeline/loaders/chromadb_loader.py", "_upsert_summary_batch"): _NOT_RAG,
    ("knowledge/rag_benchmarks.py", "chroma_collection"): "benchmark scratch collection",
    ("knowledge/write_buffer.py", "_flush"): _ENTRY,
    ("services/knowledge/analyzer_service.py", "store_lessons"): _NOT_RAG,
    ("services/knowledge/code_indexer.py", "_upsert_edges"): _NOT_RAG,
    ("services/knowledge/code_indexer.py", "_upsert_node"): _NOT_RAG,
    ("services/knowledge/code_indexer.py", "_write_provenance"): _NOT_RAG,
    ("services/knowledge/cognition_seeder.py", "_upsert_chunk"): _NOT_RAG,
    ("services/knowledge/doc_index_orphans.py", "drop_collection"): _ENTRY,
    ("services/knowledge/doc_indexer.py", "_embed_and_upsert"): "doc_index_orphans.reindex_file (registered)",
    (
        "services/knowledge/doc_indexer.py",
        "_handle_dim_mismatch",
    ): "sync init path; the re-index it forces runs reindex_file",
    ("services/knowledge/kb_synthesizer.py", "_index_documents"): _ENTRY,
    ("services/knowledge/lineage_service.py", "rollback_entity"): _NOT_RAG,
    ("services/knowledge/lineage_service.py", "stamp_entity_version"): _NOT_RAG,
}


def _vector_write_sites() -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()

    def walk(node: ast.AST, fn: str, rel: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if isinstance(child, ast.Attribute) and _is_vector_write(child):
                sites.add((rel, name))
            walk(child, name, rel)

    roots = [BACKEND / "knowledge", BACKEND / "services/knowledge", BACKEND / "api/knowledge_vectorization.py"]
    for root in roots:
        for path in [root] if root.is_file() else root.rglob("*.py"):
            if is_test_filename(path.name) or "tests" in path.parts:
                continue
            walk(ast.parse(path.read_text(encoding="utf-8")), "<module>", str(path.relative_to(BACKEND)))
    return sites


def _is_vector_write(attr: ast.Attribute) -> bool:
    if attr.attr in ("upsert", "delete_collection"):
        return True
    return attr.attr in ("add", "delete") and ast.unparse(attr.value).endswith("vector_store")


def test_every_raw_vector_write_is_an_entry_point_or_explained():
    sites = _vector_write_sites()
    assert not sites - set(
        _VECTOR_WRITES
    ), f"unclassified vector write(s), wire the hook or classify: {sorted(sites - set(_VECTOR_WRITES))}"
    assert not set(_VECTOR_WRITES) - sites, f"stale classification(s): {sorted(set(_VECTOR_WRITES) - sites)}"


def test_every_site_marked_entry_is_a_registered_entry_point():
    registered = {(e.path, e.qualname.rsplit(".", 1)[-1]) for e in WRITE_ENTRY_POINTS}
    assert {k for k, v in _VECTOR_WRITES.items() if v == _ENTRY} <= registered
