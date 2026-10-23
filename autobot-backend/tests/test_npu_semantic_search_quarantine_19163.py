# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19163: the NPU engine's retrieval paths that bypass KB.search withhold research-quarantined facts."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from autobot_shared.ssot_config import config
from npu_semantic_search import NPUSemanticSearch

HELD = {"collection": config.research_quarantine_collection}
CASES = {"good": {}, "held": HELD}


def _engine() -> NPUSemanticSearch:
    obj = NPUSemanticSearch.__new__(NPUSemanticSearch)
    obj.collections, obj.collection_names = {}, {"text": "autobot_text_embeddings"}
    return obj


def test_llamaindex_path_withholds_quarantined():
    obj = _engine()
    nodes = [SimpleNamespace(node=SimpleNamespace(text=n, metadata=m, id_=n), score=0.5) for n, m in CASES.items()]
    engine = MagicMock()
    engine.query.return_value = SimpleNamespace(source_nodes=nodes)
    obj.knowledge_base = SimpleNamespace(vector_index=MagicMock(as_query_engine=MagicMock(return_value=engine)))
    assert [r.doc_id for r in asyncio.run(obj._search_with_llamaindex("q", 5))] == ["good"]


def test_batch_chromadb_path_withholds_quarantined():
    obj = _engine()
    ids = list(CASES)
    batch = {"ids": [ids], "documents": [ids], "metadatas": [[CASES[i] for i in ids]], "distances": [[0.1, 0.2]]}
    obj.collections["text"] = SimpleNamespace(query_batch=AsyncMock(return_value=batch))
    results, _ = asyncio.run(obj._batch_chromadb_search([0], [[0.0]], 5, None, "cpu"))[0]
    assert [r.doc_id for r in results] == ["good"]


def test_basic_fallbacks_pass_filters_by_keyword_not_into_the_wrong_slot():
    obj = _engine()
    obj.knowledge_base = SimpleNamespace(vector_store=None, vector_index=None, search=AsyncMock(return_value=[]))
    asyncio.run(obj._perform_vector_search("q", 7, {"a": 1}))
    call = obj.knowledge_base.search.await_args
    assert call.args == ("q",) and call.kwargs == {"top_k": 7, "filters": {"a": 1}, "mode": "text"}
