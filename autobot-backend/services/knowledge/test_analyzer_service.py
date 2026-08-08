# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AnalyzerService — Issue #4678.

Covers:
- analyze_synthesis_run(): happy path, below-threshold score (no-op), LLM failure
- analyze_rag_session(): happy path, empty results (no-op)
- store_lessons(): ChromaDB upsert called with correct args
- get_lessons_context(): returns formatted string, empty when no results
- Lesson.lesson_id(): stable deterministic ID
- get_analyzer_service(): singleton pattern
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing analyzer_service
# ---------------------------------------------------------------------------

_STUBS: dict = {}
_STUB_MISSING = object()


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name
    _STUBS[name] = mod
    sys.modules.setdefault(name, mod)
    return mod


# autobot_shared.ssot_config — used transitively by chromadb_client
_ssot = _make_stub("autobot_shared.ssot_config")
_ssot.config = MagicMock()  # type: ignore[attr-defined]
_ssot.config.port.chromadb = 8100  # type: ignore[attr-defined]

# utils / chromadb_client stubs
_utils_stub = _make_stub("utils")
_chromadb_stub = _make_stub("utils.chromadb_client")
# AnalyzerService reaches ChromaDB through knowledge.backends'
# get_async_default_client(), which lazily imports get_async_chromadb_client
# from utils.async_chromadb_client (#5316) — not the sync utils.chromadb_client.
# _make_stub() uses sys.modules.setdefault but returns its own fresh object, so
# when a sibling test module registered this name first the returned stub is a
# dangling copy that production code never sees. Read the registered module back.
_make_stub("utils.async_chromadb_client")

# #13651: force *our* stub in for the two chromadb names, remembering what it
# displaced — ``setdefault`` is a no-op once the genuine module is imported, and
# the mutations below must not land on that genuine module.
_DISPLACED_BY_STUB = {}
for _n in ("utils.chromadb_client", "utils.async_chromadb_client"):
    _registered = sys.modules.get(_n, _STUB_MISSING)
    if _registered is not _STUBS[_n]:
        # Only when something else holds the name — rewriting our own stub back
        # over itself is a no-op the leak guard would still record as a mutation.
        _DISPLACED_BY_STUB[_n] = _registered
        sys.modules[_n] = _STUBS[_n]
_async_chromadb_stub = sys.modules["utils.async_chromadb_client"]
# Injecting a submodule straight into sys.modules does not bind it on the
# parent package, so mock.patch("utils.async_chromadb_client....") — used by
# services/rag_service_kb_synthesis_test.py — cannot resolve it. Bind it, and
# seed the symbol production imports so patch() finds an existing attribute.
_async_chromadb_stub.get_async_chromadb_client = AsyncMock()  # type: ignore[attr-defined]
sys.modules["utils"].async_chromadb_client = _async_chromadb_stub  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Load analyzer_service via importlib to bypass package __init__ imports
# ---------------------------------------------------------------------------

_ANALYZER_PATH = Path(__file__).parent / "analyzer_service.py"
_spec = importlib.util.spec_from_file_location("services.knowledge.analyzer_service", str(_ANALYZER_PATH))
assert _spec and _spec.loader, "Could not load analyzer_service spec"
_analyzer_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.knowledge.analyzer_service"] = _analyzer_mod
try:
    _spec.loader.exec_module(_analyzer_mod)  # type: ignore[union-attr]
except BaseException:  # noqa: BLE001 - re-raised below
    # #13651: a failed import must not leave our stub installed for the rest of
    # the session. The guard's own advice is to install and remove in the same
    # try/finally; without this, an ImportError here is strictly worse than the
    # old behaviour, which left the genuine module untouched.
    for _n, _prev in _DISPLACED_BY_STUB.items():
        if _prev is not _STUB_MISSING:
            sys.modules[_n] = _prev
        else:
            sys.modules.pop(_n, None)
    raise

from services.knowledge.analyzer_service import (  # noqa: E402
    AnalyzerService,
    Lesson,
    get_analyzer_service,
)

# #13435: the stubs above were needed to import analyzer_service, and they are
# needed again while this module's tests run, because those tests patch through
# dotted paths such as ``utils.async_chromadb_client.get_async_chromadb_client``
# which resolve via ``sys.modules``. They are NOT needed in between — and
# "in between" is when every other test module in the worker gets imported, so
# leaving them installed is what leaked ``utils`` and its children across the
# session (the leak guard added in #13361 now fails the run on it).
#
# Unload them here; ``_reinstall_module_stubs`` in this package's conftest puts
# these exact objects back for the duration of this module's tests and removes
# them afterwards. The same objects, not fresh ones — analyzer_service captured
# references at import and a different stub would not be the module it holds.
_STUBS_UNLOADED_AFTER_IMPORT = {
    name: sys.modules.pop(name)
    for name in ("utils.chromadb_client", "utils.async_chromadb_client")
    if name in sys.modules
}

# Put back whatever those stubs displaced (#13651): a genuine module imported
# before this one must survive it as the same, unmutated object.
#
# The parent attribute is restored alongside the ``sys.modules`` entry. They are
# two separate channels -- ``mock.patch("utils.async_chromadb_client.X")``
# resolves via ``getattr(sys.modules["utils"], ...)`` (#11532, #12463), while
# ``import utils.async_chromadb_client`` reads the key -- and letting them
# disagree would mean patching a stub while the code under test holds the real
# module.
for _n, _prev in _DISPLACED_BY_STUB.items():
    if _prev is not _STUB_MISSING:
        sys.modules[_n] = _prev
        _parent_name, _, _leaf = _n.rpartition(".")
        _parent = sys.modules.get(_parent_name) if _parent_name else None
        if _parent is not None:
            setattr(_parent, _leaf, _prev)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(content: str = "Use shorter prompts.\nPrefer diverse sources.") -> MagicMock:
    llm = MagicMock()
    response = MagicMock()
    response.content = content
    llm.chat = AsyncMock(return_value=response)
    return llm


def _make_collection(query_results: dict | None = None) -> AsyncMock:
    col = AsyncMock()
    col.upsert = AsyncMock()
    default = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
    col.query = AsyncMock(return_value=query_results or default)
    return col


def _make_chromadb_client(collection: AsyncMock) -> AsyncMock:
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=collection)
    return client


def _patch_chromadb(analyzer: AnalyzerService, collection: AsyncMock) -> None:
    """Inject a mock ChromaDB client into analyzer._get_collection path."""
    client = _make_chromadb_client(collection)
    _async_chromadb_stub.get_async_chromadb_client = AsyncMock(return_value=client)


# ---------------------------------------------------------------------------
# Tests: Lesson dataclass
# ---------------------------------------------------------------------------


def test_lesson_id_stable() -> None:
    lsn = Lesson(content="Use shorter prompts.", domain="synthesis", score_delta=0.5)
    assert lsn.lesson_id() == lsn.lesson_id()


def test_lesson_id_starts_with_prefix() -> None:
    lsn = Lesson(content="abc", domain="synthesis", score_delta=0.3)
    assert lsn.lesson_id().startswith("lesson_")


def test_lesson_id_differs_by_content() -> None:
    a = Lesson(content="foo", domain="synthesis", score_delta=0.3)
    b = Lesson(content="bar", domain="synthesis", score_delta=0.3)
    assert a.lesson_id() != b.lesson_id()


def test_lesson_to_metadata_keys() -> None:
    lsn = Lesson(content="abc", domain="retrieval", score_delta=0.7, tags=["a", "b"], run_id="r1")
    meta = lsn.to_metadata()
    assert meta["domain"] == "retrieval"
    assert meta["run_id"] == "r1"
    assert "score_delta" in meta
    assert "created_at" in meta


# ---------------------------------------------------------------------------
# Tests: analyze_synthesis_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_synthesis_run_happy_path() -> None:
    llm = _make_llm("Lesson one.\nLesson two.")
    svc = AnalyzerService(llm)
    lessons = await svc.analyze_synthesis_run(
        run_id="run1",
        input_docs=["doc content " * 50],
        output_summary="summary content " * 10,
        score=0.5,
    )
    assert len(lessons) == 2
    assert lessons[0].domain == "synthesis"
    assert lessons[0].run_id == "run1"
    assert lessons[0].score_delta == pytest.approx(0.5)
    llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_synthesis_run_below_threshold() -> None:
    llm = _make_llm("Should not be called.")
    svc = AnalyzerService(llm)
    lessons = await svc.analyze_synthesis_run(
        run_id="run_low",
        input_docs=["doc"],
        output_summary="short",
        score=0.05,  # below _MIN_SCORE_DELTA=0.1
    )
    assert lessons == []
    llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_synthesis_run_llm_failure() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    svc = AnalyzerService(llm)
    # Should return [] gracefully, not raise
    lessons = await svc.analyze_synthesis_run(
        run_id="run_err",
        input_docs=["doc"],
        output_summary="summary",
        score=0.8,
    )
    assert lessons == []


# ---------------------------------------------------------------------------
# Tests: analyze_rag_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_rag_session_happy_path() -> None:
    llm = _make_llm("Prefer source diversity.\nApply reranking always.")
    svc = AnalyzerService(llm)

    result = MagicMock()
    result.content = "Result content here"

    lessons = await svc.analyze_rag_session(
        query="What is Redis?",
        results=[result, result],
    )
    assert len(lessons) == 2
    assert all(lsn.domain == "retrieval" for lsn in lessons)
    llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_rag_session_empty_results() -> None:
    llm = _make_llm("Lesson.")
    svc = AnalyzerService(llm)
    lessons = await svc.analyze_rag_session(query="q", results=[])
    assert lessons == []
    llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_rag_session_higher_score_with_feedback() -> None:
    llm = _make_llm("One lesson.")
    svc = AnalyzerService(llm)
    result = MagicMock()
    result.content = "some content"
    lessons = await svc.analyze_rag_session(query="q", results=[result], user_feedback="Very helpful!")
    assert len(lessons) == 1
    # score_delta should be 0.5 when user_feedback is provided
    assert lessons[0].score_delta == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Tests: store_lessons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_lessons_calls_upsert() -> None:
    llm = _make_llm()
    svc = AnalyzerService(llm)
    col = _make_collection()
    _patch_chromadb(svc, col)

    lessons = [
        Lesson(content="Use shorter prompts.", domain="synthesis", score_delta=0.5, run_id="r1"),
        Lesson(content="Prefer diverse sources.", domain="synthesis", score_delta=0.4, run_id="r1"),
    ]
    await svc.store_lessons(lessons)
    col.upsert.assert_awaited_once()
    call_kwargs = col.upsert.call_args.kwargs
    assert len(call_kwargs["ids"]) == 2
    assert len(call_kwargs["documents"]) == 2
    assert len(call_kwargs["metadatas"]) == 2


@pytest.mark.asyncio
async def test_store_lessons_empty_no_op() -> None:
    llm = _make_llm()
    svc = AnalyzerService(llm)
    col = _make_collection()
    _patch_chromadb(svc, col)
    await svc.store_lessons([])
    col.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_lessons_chromadb_error_graceful() -> None:
    llm = _make_llm()
    svc = AnalyzerService(llm)
    col = _make_collection()
    col.upsert = AsyncMock(side_effect=RuntimeError("ChromaDB error"))
    _patch_chromadb(svc, col)
    lessons = [Lesson(content="Lesson.", domain="synthesis", score_delta=0.5)]
    # Should not raise
    await svc.store_lessons(lessons)


# ---------------------------------------------------------------------------
# Tests: get_lessons_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_lessons_context_returns_formatted_string() -> None:
    llm = _make_llm()
    svc = AnalyzerService(llm)
    query_results = {
        "ids": [["lesson_abc123"]],
        "documents": [["Use shorter prompts."]],
        "metadatas": [[{"domain": "synthesis"}]],
    }
    col = _make_collection(query_results)
    _patch_chromadb(svc, col)

    ctx = await svc.get_lessons_context("test query")
    assert "Analyzer lessons:" in ctx
    assert "Use shorter prompts." in ctx


@pytest.mark.asyncio
async def test_get_lessons_context_empty_when_no_results() -> None:
    llm = _make_llm()
    svc = AnalyzerService(llm)
    col = _make_collection()  # default empty results
    _patch_chromadb(svc, col)

    ctx = await svc.get_lessons_context("test query")
    assert ctx == ""


@pytest.mark.asyncio
async def test_get_lessons_context_chromadb_error_returns_empty() -> None:
    llm = _make_llm()
    svc = AnalyzerService(llm)
    # Make chromadb client raise
    _chromadb_stub.get_async_chromadb_client = AsyncMock(side_effect=RuntimeError("ChromaDB unavailable"))
    ctx = await svc.get_lessons_context("test query")
    assert ctx == ""


# ---------------------------------------------------------------------------
# Tests: singleton
# ---------------------------------------------------------------------------


def test_get_analyzer_service_singleton() -> None:
    import services.knowledge.analyzer_service as _mod

    # Reset singleton for isolation
    _mod._analyzer_service = None
    llm = _make_llm()
    svc1 = get_analyzer_service(llm)
    svc2 = get_analyzer_service(MagicMock())  # second call should return cached
    assert svc1 is svc2
    _mod._analyzer_service = None  # clean up
