# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The readers that bypass ``KB.search`` never see a research-quarantined chunk (#19163).

The reindex job and the near-duplicate check apply the canonical ``without_quarantine`` filter; the two
readers proven unable to see a quarantined row are re-checked from source against their written proof.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import knowledge_vectorization
from autobot_shared.ssot_config import config
from knowledge.facts import FactsMixin
from knowledge.platform_docs import PLATFORM_DOCS_GRANT
from knowledge.quarantine import without_quarantine

_REPO = Path(__file__).resolve().parents[2]
_CLAUSE = {"collection": {"$ne": config.research_quarantine_collection}}


@pytest.mark.asyncio
async def test_unenriched_scan_excludes_quarantined_chunks():
    collection = MagicMock()
    collection.get = AsyncMock(return_value={"ids": []})

    await knowledge_vectorization._fetch_unenriched_ids(collection, 10)

    assert collection.get.await_args.kwargs["where"] == without_quarantine({"has_context": {"$ne": True}})
    assert _CLAUSE in collection.get.await_args.kwargs["where"]["$and"]


@pytest.mark.asyncio
async def test_chunk_fetch_by_id_excludes_quarantined_chunks():
    collection = MagicMock()
    collection.get = AsyncMock(return_value={"ids": [], "documents": [], "metadatas": []})

    await knowledge_vectorization._fetch_chunks_by_ids(collection, ["a"])

    assert collection.get.await_args.kwargs["where"] == without_quarantine()


@pytest.mark.asyncio
async def test_near_duplicate_check_excludes_quarantined_facts():
    chroma = MagicMock()
    chroma.query.return_value = {"ids": [[]], "distances": [[]], "metadatas": [[]]}
    kb = FactsMixin.__new__(FactsMixin)
    kb.vector_store = MagicMock(_collection=chroma)

    with patch("knowledge.facts._generate_embedding_with_npu_fallback", AsyncMock(return_value=[0.1])):
        await kb._find_duplicate("text")

    assert chroma.query.call_args.kwargs["where"] == without_quarantine()


def _tree(rel: str) -> ast.Module:
    return ast.parse((_REPO / rel).read_text(encoding="utf-8"))


def test_doc_indexer_has_one_writer_whose_metadata_has_no_collection_key():
    rel = "autobot-backend/services/knowledge/doc_indexer.py"
    tree = _tree(rel)
    writes = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in ("upsert", "add", "update")]
    on_collection = [n for n in writes if isinstance(n.value, ast.Attribute) and n.value.attr == "_collection"]
    assert len(on_collection) == 1

    index_chunk = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_index_chunk")
    literal = next(
        n.value
        for n in ast.walk(index_chunk)
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "metadata"
    )
    keys = {k.value for k in literal.keys if isinstance(k, ast.Constant)}
    spreads = [v.id for k, v in zip(literal.keys, literal.values) if k is None and isinstance(v, ast.Name)]
    assert spreads == ["PLATFORM_DOCS_GRANT"] and None not in [k for k in literal.keys if k is not None]
    assert "collection" not in keys and "collection" not in PLATFORM_DOCS_GRANT


def test_rag_benchmarks_reads_only_in_process_ephemeral_collections():
    source = (_REPO / "autobot-backend/knowledge/rag_benchmarks.py").read_text(encoding="utf-8")
    assert "chromadb.EphemeralClient()" in source
    for opener in ("get_async_default_client", "get_async_chromadb_client", "PersistentClient", "HttpClient"):
        assert opener not in source


def test_every_proof_names_an_existing_reader():
    from repo_tests.quarantine_bypass_readers_19163 import PROVEN_NO_QUARANTINED_ROWS

    assert all((_REPO / path).is_file() for path in PROVEN_NO_QUARANTINED_ROWS)
