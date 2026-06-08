# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
_spec = importlib.util.spec_from_file_location("services.knowledge.kb_synthesizer", str(_KB_SYNTH_PATH))
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


def test_cluster_id_stable() -> None:
    paths = ["/a/b.md", "/a/c.md"]
    assert _cluster_id(paths) == _cluster_id(paths)


def test_cluster_id_order_independent() -> None:
    assert _cluster_id(["/a.md", "/b.md"]) == _cluster_id(["/b.md", "/a.md"])


def test_cluster_id_prefix() -> None:
    cid = _cluster_id(["/a.md"])
    assert cid.startswith("kb_syn_")


# ---------------------------------------------------------------------------
# Tests: _read_docs (sync)
# ---------------------------------------------------------------------------


def test_read_docs_missing_file(tmp_path) -> None:
    result = _read_docs([str(tmp_path / "missing.md")])
    assert result == ""


def test_read_docs_reads_content(tmp_path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("Hello world", encoding="utf-8")
    result = _read_docs([str(f)])
    assert "Hello world" in result


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer._get_collection (lazy init)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_collection_creates_once() -> None:
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
async def test_index_documents_upsert_called() -> None:
    col = _make_collection()
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col  # inject directly

    docs = [{"id": "kb_syn_abc", "summary": "A summary", "doc_count": 1, "synthesized_at": 0.0, "source_paths": ""}]
    await synth._index_documents(docs)

    col.upsert.assert_awaited_once()
    call_kwargs = col.upsert.call_args
    ids_arg = call_kwargs.kwargs.get("ids") or (call_kwargs.args[0] if call_kwargs.args else [])
    assert "kb_syn_abc" in ids_arg


@pytest.mark.asyncio
async def test_index_documents_empty_noop() -> None:
    col = _make_collection()
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col
    await synth._index_documents([])
    col.upsert.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer.synthesize_docs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_docs_happy_path(tmp_path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("# Topic\nSome content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Synthesized summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col
    # Issue #4785: AnalyzerService (#4678) makes a second llm.chat call; patch it
    # out so the synthesis-only assertion on assert_awaited_once() stays valid.
    synth._run_analyzer = AsyncMock()

    await synth.synthesize_docs([str(f)])

    llm.chat.assert_awaited_once()
    col.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_synthesize_docs_empty_paths() -> None:
    llm = _make_llm()
    synth = KBSynthesizer(llm_service=llm)
    await synth.synthesize_docs([])  # must not raise
    llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_docs_llm_error_is_swallowed(tmp_path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("content", encoding="utf-8")

    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    col = _make_collection()
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)])  # must not raise

    col.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_docs_calls_provenance_log_run(tmp_path) -> None:
    """After a successful synthesis, log_run must be called on the provenance log (#4656)."""
    f = tmp_path / "doc.md"
    f.write_text("# Topic\nContent here.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Synthesized summary")
    provenance_log = MagicMock()
    provenance_log.log_run = AsyncMock()

    synth = KBSynthesizer(llm_service=llm, provenance_log=provenance_log)
    synth._collection = col

    await synth.synthesize_docs([str(f)])

    provenance_log.log_run.assert_awaited_once()
    call_kwargs = provenance_log.log_run.call_args.kwargs
    assert call_kwargs["source_docs"] == [str(f)]
    assert len(call_kwargs["synthesis_ids"]) == 1
    assert call_kwargs["synthesis_ids"][0].startswith("kb_syn_")
    assert call_kwargs["run_id"] == call_kwargs["synthesis_ids"][0]
    assert isinstance(call_kwargs["duration_ms"], int)


@pytest.mark.asyncio
async def test_synthesize_docs_provenance_log_not_called_on_llm_error(tmp_path) -> None:
    """When LLM fails, log_run must NOT be called (#4656)."""
    f = tmp_path / "doc.md"
    f.write_text("content", encoding="utf-8")

    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    col = _make_collection()
    provenance_log = MagicMock()
    provenance_log.log_run = AsyncMock()

    synth = KBSynthesizer(llm_service=llm, provenance_log=provenance_log)
    synth._collection = col

    await synth.synthesize_docs([str(f)])  # must not raise

    provenance_log.log_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer.get_relevant_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_relevant_context_with_results() -> None:
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
async def test_get_relevant_context_empty_collection() -> None:
    col = _make_collection()  # returns empty ids
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col

    ctx = await synth.get_relevant_context("anything")

    assert ctx == ""


# ---------------------------------------------------------------------------
# Tests: get_kb_synthesizer singleton
# ---------------------------------------------------------------------------


def test_get_kb_synthesizer_singleton() -> None:
    # Reset module-level singleton first
    _kb_synth_mod._kb_synthesizer = None  # type: ignore[attr-defined]

    llm = _make_llm()
    s1 = get_kb_synthesizer(llm)
    s2 = get_kb_synthesizer(_make_llm())  # second call — different llm, same instance

    assert s1 is s2
    assert s1._llm is llm  # bound to first llm


def test_get_kb_synthesizer_returns_instance() -> None:
    _kb_synth_mod._kb_synthesizer = None  # type: ignore[attr-defined]
    synth = get_kb_synthesizer(_make_llm())
    assert isinstance(synth, KBSynthesizer)


# ---------------------------------------------------------------------------
# Helpers: CollectionConfig stub
# ---------------------------------------------------------------------------


def _make_collection_config(
    name: str = "test_col",
    prompt_template: str = "Custom prompt: {documents}",
    synthesis_target: str = "",
):
    """Return a minimal CollectionConfig-like object for testing."""
    cfg = MagicMock()
    cfg.name = name
    cfg.prompt_template = prompt_template
    cfg.synthesis_target = synthesis_target
    cfg.paths = ["docs/test"]
    return cfg


# ---------------------------------------------------------------------------
# Tests: KBSynthesizer._resolve_prompt (#4614)
# ---------------------------------------------------------------------------


def test_resolve_prompt_no_config_returns_default() -> None:
    synth = KBSynthesizer(llm_service=_make_llm())
    prompt = synth._resolve_prompt(None)
    assert prompt == _kb_synth_mod._SYNTHESIS_PROMPT


def test_resolve_prompt_with_config_returns_template() -> None:
    synth = KBSynthesizer(llm_service=_make_llm())
    cfg = _make_collection_config(prompt_template="Custom: {documents}")
    prompt = synth._resolve_prompt(cfg)
    assert prompt == "Custom: {documents}"


def test_resolve_prompt_empty_template_falls_back_to_default() -> None:
    synth = KBSynthesizer(llm_service=_make_llm())
    cfg = _make_collection_config(prompt_template="   ")
    prompt = synth._resolve_prompt(cfg)
    assert prompt == _kb_synth_mod._SYNTHESIS_PROMPT


# ---------------------------------------------------------------------------
# Tests: synthesize_docs with collection_config (#4614)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_docs_uses_collection_config_prompt(tmp_path) -> None:
    """Template with {documents} sends a single user message with docs substituted (Option A)."""
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
    # With {documents} placeholder: single user message, no system message
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "You are an architecture assistant." in messages[0]["content"]
    assert "# Architecture" in messages[0]["content"]


@pytest.mark.asyncio
async def test_synthesize_docs_no_config_uses_default_prompt(tmp_path) -> None:
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


# ---------------------------------------------------------------------------
# Tests: {documents} placeholder substitution in _synthesize_cluster (#4634)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_cluster_with_documents_placeholder_single_user_message(tmp_path) -> None:
    """When template has {documents}, LLM receives a single user message with docs substituted."""
    f = tmp_path / "doc.md"
    f.write_text("Important content here.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Synthesis result")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    cfg = _make_collection_config(
        name="test_col",
        prompt_template="Summarize these docs:\n\n{documents}\n\nEnd.",
    )

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    llm.chat.assert_awaited_once()
    messages = llm.chat.call_args.kwargs.get("messages") or llm.chat.call_args.args[0]
    # Must be exactly one user message — no system message
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "Important content here." in messages[0]["content"]
    assert "{documents}" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_synthesize_cluster_without_documents_placeholder_two_message_format(tmp_path) -> None:
    """When template has no {documents}, LLM receives system + user two-message format."""
    f = tmp_path / "doc.md"
    f.write_text("Some content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Synthesis result")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    # No {documents} placeholder — generic fallback-style prompt
    cfg = _make_collection_config(
        name="test_col",
        prompt_template="You are a helpful assistant.",
    )

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    llm.chat.assert_awaited_once()
    messages = llm.chat.call_args.kwargs.get("messages") or llm.chat.call_args.args[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful assistant."
    assert messages[1]["role"] == "user"
    assert "Some content." in messages[1]["content"]


@pytest.mark.asyncio
async def test_synthesize_cluster_documents_placeholder_substitutes_actual_content(tmp_path) -> None:
    """The substituted {documents} value contains the actual file content, not a literal."""
    f = tmp_path / "readme.md"
    f.write_text("Redis caching layer docs.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("done")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    cfg = _make_collection_config(
        prompt_template="Prefix:\n{documents}\nSuffix",
    )

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    messages = llm.chat.call_args.kwargs.get("messages") or llm.chat.call_args.args[0]
    user_content = messages[0]["content"]
    assert "Redis caching layer docs." in user_content
    assert "Prefix:" in user_content
    assert "Suffix" in user_content


@pytest.mark.asyncio
async def test_synthesize_cluster_default_prompt_no_documents_placeholder(tmp_path) -> None:
    """Default (no collection_config) prompt has no {documents} — uses two-message format."""
    f = tmp_path / "doc.md"
    f.write_text("Content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("result")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)], collection_config=None)

    messages = llm.chat.call_args.kwargs.get("messages") or llm.chat.call_args.args[0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# Tests: synthesis_target routing (#4635)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_cluster_writes_to_synthesis_target(tmp_path) -> None:
    """When synthesis_target is set, _index_documents is called with that name."""
    f = tmp_path / "arch.md"
    f.write_text("# Architecture", encoding="utf-8")

    target_col = _make_collection()
    default_col = _make_collection()

    llm = _make_llm("Architecture summary")
    synth = KBSynthesizer(llm_service=llm)
    # Inject default collection to verify it is NOT written to.
    synth._collection = default_col

    # Inject named collection so _get_collection(collection_name) returns target_col.
    synth._named_collections["autobot_synthesis_architecture"] = target_col

    cfg = _make_collection_config(
        name="architecture_adrs",
        synthesis_target="autobot_synthesis_architecture",
    )

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    # Must write to synthesis_target, not to the default collection.
    target_col.upsert.assert_awaited_once()
    default_col.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_cluster_falls_back_to_default_when_no_target(tmp_path) -> None:
    """When synthesis_target is empty, output goes to the default collection."""
    f = tmp_path / "doc.md"
    f.write_text("# Topic\nContent.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Generic summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    cfg = _make_collection_config(name="no_target_col", synthesis_target="")

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    col.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_synthesize_cluster_falls_back_when_config_is_none(tmp_path) -> None:
    """When collection_config is None, output goes to the default collection."""
    f = tmp_path / "doc.md"
    f.write_text("# Topic\nContent.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)], collection_config=None)

    col.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_relevant_context_queries_extra_collections() -> None:
    """get_relevant_context queries extra collection names in addition to default."""
    default_results = {
        "ids": [["id1"]],
        "documents": [["Default summary."]],
        "metadatas": [[{}]],
    }
    extra_results = {
        "ids": [["id2"]],
        "documents": [["Architecture summary."]],
        "metadatas": [[{}]],
    }
    default_col = _make_collection(default_results)
    extra_col = _make_collection(extra_results)

    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = default_col
    synth._named_collections["autobot_synthesis_architecture"] = extra_col

    ctx = await synth.get_relevant_context("architecture", collection_names=["autobot_synthesis_architecture"])

    assert "Default summary." in ctx
    assert "Architecture summary." in ctx


@pytest.mark.asyncio
async def test_get_relevant_context_deduplicates_default_collection() -> None:
    """Passing the default collection name twice must not query it twice."""
    default_results = {
        "ids": [["id1"]],
        "documents": [["Default summary."]],
        "metadatas": [[{}]],
    }
    col = _make_collection(default_results)
    synth = KBSynthesizer(llm_service=_make_llm())
    synth._collection = col

    # Pass default name explicitly — should be deduplicated.
    await synth.get_relevant_context("topic", collection_names=[_kb_synth_mod._KB_SYNTHESIS_COLLECTION])

    # Default collection queried exactly once (not twice).
    assert col.query.await_count == 1


# ---------------------------------------------------------------------------
# Tests: synthesis_model override (#4688)
# ---------------------------------------------------------------------------


def _make_collection_config_with_model(
    name: str = "test_col",
    prompt_template: str = "Custom prompt: {documents}",
    synthesis_target: str = "",
    synthesis_model: str | None = None,
):
    """Return a CollectionConfig-like mock with synthesis_model support."""
    cfg = MagicMock()
    cfg.name = name
    cfg.prompt_template = prompt_template
    cfg.synthesis_target = synthesis_target
    cfg.paths = ["docs/test"]
    cfg.synthesis_model = synthesis_model
    return cfg


@pytest.mark.asyncio
async def test_synthesize_docs_passes_model_override_to_llm(tmp_path) -> None:
    """When synthesis_model is set, llm.chat() receives model= kwarg."""
    f = tmp_path / "doc.md"
    f.write_text("Architecture notes.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    cfg = _make_collection_config_with_model(
        name="hq_col",
        synthesis_model="claude-opus-4-6",
    )

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    llm.chat.assert_awaited_once()
    call_kwargs = llm.chat.call_args.kwargs
    assert call_kwargs.get("model") == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_synthesize_docs_no_model_override_omits_model_kwarg(tmp_path) -> None:
    """When synthesis_model is None, llm.chat() is NOT passed a model= kwarg."""
    f = tmp_path / "doc.md"
    f.write_text("Some content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    cfg = _make_collection_config_with_model(name="default_col", synthesis_model=None)

    await synth.synthesize_docs([str(f)], collection_config=cfg)

    llm.chat.assert_awaited_once()
    call_kwargs = llm.chat.call_args.kwargs
    assert "model" not in call_kwargs


@pytest.mark.asyncio
async def test_synthesize_docs_no_collection_config_omits_model_kwarg(tmp_path) -> None:
    """When collection_config is None, llm.chat() is NOT passed a model= kwarg."""
    f = tmp_path / "doc.md"
    f.write_text("Content.", encoding="utf-8")

    col = _make_collection()
    llm = _make_llm("Summary")
    synth = KBSynthesizer(llm_service=llm)
    synth._collection = col

    await synth.synthesize_docs([str(f)], collection_config=None)

    llm.chat.assert_awaited_once()
    call_kwargs = llm.chat.call_args.kwargs
    assert "model" not in call_kwargs
