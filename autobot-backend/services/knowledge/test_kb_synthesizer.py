# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for KBSynthesizer — Issue #4564.

Covers:
- synthesize_docs(): happy path, empty input, LLM error (best-effort)
- _index_documents(): ChromaDB upsert called with correct args
- get_relevant_context(): returns formatted string from ChromaDB query results
- _cluster_id(): stable, deterministic
- _query_summaries(): empty results handled gracefully
- get_kb_synthesizer(): singleton pattern
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing kb_synthesizer
# ---------------------------------------------------------------------------

_STUBS: dict = {}


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

# utils / chromadb_client stubs (loaded lazily inside methods — stub at import time)
_utils_stub = _make_stub("utils")
_chromadb_stub = _make_stub("utils.chromadb_client")
_async_chromadb_stub = _make_stub("utils.async_chromadb_client")

# ---------------------------------------------------------------------------
# Load kb_synthesizer via importlib to bypass package __init__ imports
# ---------------------------------------------------------------------------

_KB_SYNTH_PATH = Path(__file__).parent / "kb_synthesizer.py"
_spec = importlib.util.spec_from_file_location(
    "services.knowledge.kb_synthesizer", str(_KB_SYNTH_PATH)
)
assert _spec and _spec.loader, "Could not load kb_synthesizer spec"
_kb_synth_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.knowledge.kb_synthesizer"] = _kb_synth_mod
_spec.loader.exec_module(_kb_synth_mod)  # type: ignore[union-attr]

# Expose the module as an attribute on the package stub so patch() can resolve it
if "services.knowledge" in sys.modules:
    sys.modules["services.knowledge"].kb_synthesizer = _kb_synth_mod  # type: ignore[attr-defined]

from services.knowledge.kb_synthesizer import (  # noqa: E402
    KBSynthesizer,
    get_kb_synthesizer,
)

# Private static helpers — in Python 3.10+ staticmethods are plain functions on the class
_cluster_id = KBSynthesizer._cluster_id  # type: ignore[attr-defined]
_read_docs = KBSynthesizer._read_docs  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(content: str = "Summary text") -> MagicMock:
    """Return a mock LLM service whose .chat() returns a response with .content."""
    llm = MagicMock()
    response = MagicMock()
    response.content = content
    llm.chat = AsyncMock(return_value=response)
    return llm


def _make_collection(query_results: dict | None = None) -> AsyncMock:
    """Return a mock AsyncChromaCollection."""
    col = AsyncMock()
    col.upsert = AsyncMock()
    default = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
    col.query = AsyncMock(return_value=query_results or default)
    return col


def _make_chromadb_client(collection: AsyncMock) -> AsyncMock:
    """Return a mock async ChromaDB client."""
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=collection)
    return client


# ---------------------------------------------------------------------------
# Tests: _cluster_id
# ---------------------------------------------------------------------------


def test_cluster_id_stable():
    paths = ["/a/b.md", "/a/c.md"]
    assert _cluster_id(paths) == _cluster_id(paths)


def test_cluster_id_order_independent():
    assert _cluster_id(["/a.md", "/b.md"]) == _cluster_id(["/b.md", "/a.md"])


def test_cluster_id_prefix():
    cid = _cluster_id(["/a.md"])
    assert cid.startswith("kb_syn_")


# ---------------------------------------------------------------------------
# Tests: _read_docs (sync)
# ---------------------------------------------------------------------------


def test_read_docs_missing_file(tmp_path):
    result = _read_docs([str(tmp_path / "missing.md")])
    assert result == ""


def test_read_docs_reads_content(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("Hello world", encoding="utf-8")
    result = _read_docs([str(f)])
    assert "Hello world" in result


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer._get_collection (lazy init)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_collection_creates_once():
    col = _make_collection()
    client = _make_chromadb_client(col)

    synth = KBSynthesizer(llm_service=_make_llm())
    # Patch the lazily-imported symbol inside utils.chromadb_client stub
    _chromadb_stub.get_async_chromadb_client = AsyncMock(return_value=client)

    c1 = await synth._get_collection()
    c2 = await synth._get_collection()

    assert c1 is c2
    assert client.get_or_create_collection.await_count == 1


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer._index_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_documents_upsert_called():
    col = _make_collection()
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col  # inject directly

    docs = [
        {"id": "kb_syn_abc", "summary": "A summary",
         "doc_count": 1, "synthesized_at": 0.0, "source_paths": ""}
    ]
    await synth._index_documents(docs)

    col.upsert.assert_awaited_once()
    call_kwargs = col.upsert.call_args
    ids_arg = call_kwargs.kwargs.get("ids") or (call_kwargs.args[0] if call_kwargs.args else [])
    assert "kb_syn_abc" in ids_arg


@pytest.mark.asyncio
async def test_index_documents_empty_noop():
    col = _make_collection()
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col
    await synth._index_documents([])
    col.upsert.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer.synthesize_docs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_docs_happy_path(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# Topic\nSome content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Synthesized summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)])

    llm.chat.assert_awaited_once()
    col.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_synthesize_docs_empty_paths():
    llm = _make_llm()
    synth = KBSynthesizer(llm_service=llm)
    await synth.synthesize_docs([])  # must not raise
    llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_docs_llm_error_is_swallowed(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("content", encoding="utf-8")

    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    col = _make_collection()
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)])  # must not raise

    col.upsert.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer.get_relevant_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_relevant_context_with_results():
    query_results = {
        "ids": [["id1"]],
        "documents": [["A summary about Redis."]],
        "metadatas": [[{"source_paths": "/docs/redis.md"}]],
    }
    col = _make_collection(query_results)
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col

    ctx = await synth.get_relevant_context("redis", limit=1)

    assert "KB synthesis context:" in ctx
    assert "A summary about Redis." in ctx


@pytest.mark.asyncio
async def test_get_relevant_context_empty_collection():
    col = _make_collection()  # returns empty ids
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col

    ctx = await synth.get_relevant_context("anything")

    assert ctx == ""


# ---------------------------------------------------------------------------
# Tests: get_kb_synthesizer singleton
# ---------------------------------------------------------------------------


def test_get_kb_synthesizer_singleton():
    # Reset module-level singleton first
    _kb_synth_mod._kb_synthesizer = None  # type: ignore[attr-defined]

    llm = _make_llm()
    s1 = get_kb_synthesizer(llm)
    s2 = get_kb_synthesizer(_make_llm())  # second call — different llm, same instance

    assert s1 is s2
    assert s1._llm is llm  # bound to first llm


def test_get_kb_synthesizer_returns_instance():
    _kb_synth_mod._kb_synthesizer = None  # type: ignore[attr-defined]
    synth = get_kb_synthesizer(_make_llm())
    assert isinstance(synth, KBSynthesizer)


# ---------------------------------------------------------------------------
# Helpers: CollectionConfig stub
# ---------------------------------------------------------------------------


def _make_collection_config(name: str = "test_col", prompt_template: str = "Custom prompt: {documents}"):
    """Return a minimal CollectionConfig-like object for testing."""
    cfg = MagicMock()
    cfg.name = name
    cfg.prompt_template = prompt_template
    cfg.paths = ["docs/test"]
    return cfg


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer._resolve_prompt (#4614)
# ---------------------------------------------------------------------------


def test_resolve_prompt_no_config_returns_default():
    synth = KBSynthesizer(llm_service=_make_llm())
    prompt = synth._resolve_prompt(None)
    assert prompt == _kb_synth_mod._SYNTHESIS_PROMPT


def test_resolve_prompt_with_config_returns_template():
    synth = KBSynthesizer(llm_service=_make_llm())
    cfg = _make_collection_config(prompt_template="Custom: {documents}")
    prompt = synth._resolve_prompt(cfg)
    assert prompt == "Custom: {documents}"


def test_resolve_prompt_empty_template_falls_back_to_default():
    synth = KBSynthesizer(llm_service=_make_llm())
    cfg = _make_collection_config(prompt_template="   ")
    prompt = synth._resolve_prompt(cfg)
    assert prompt == _kb_synth_mod._SYNTHESIS_PROMPT


# ---------------------------------------------------------------------------
# Tests: synthesize_docs with collection_config (#4614)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_docs_uses_collection_config_prompt(tmp_path):
    f = tmp_path / "arch.md"
    f.write_text("# Architecture\nSome details.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Architecture synthesis")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    cfg = _make_collection_config(
        name="architecture_adrs",
        prompt_template="You are an architecture assistant. Docs: {documents}",
    )

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    llm.chat.assert_awaited_once()
    call_kwargs = llm.chat.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
    system_content = next(m["content"] for m in messages if m["role"] == "system")
    assert "You are an architecture assistant." in system_content


@pytest.mark.asyncio
async def test_synthesize_docs_no_config_uses_default_prompt(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# Topic\nSome content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Generic synthesis")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)], collection_config=None)

    llm.chat.assert_awaited_once()
    call_kwargs = llm.chat.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
    system_content = next(m["content"] for m in messages if m["role"] == "system")
    assert system_content == _kb_synth_mod._SYNTHESIS_PROMPT
