# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""_fetch_all_chunks reads the knowledge base's real collection handle (#16707).

No production code ever defined `chroma_collection` on the knowledge base;
`_fetch_all_chunks` read it anyway, so `/knowledge-maintenance/lint` raised
AttributeError the moment it tried to load chunks. The double here exposes
only `vector_store._collection` -- the real attribute knowledge/search.py's
own ChromaDB access uses -- and nothing named `chroma_collection`, so a
regression back to the old attribute fails loudly instead of silently
passing because a Mock auto-vivifies whatever is asked of it.
"""

import pytest

from api.knowledge_maintenance import _fetch_all_chunks


class _FakeChromaCollection:
    """A plain object, not a Mock -- accessing an attribute that doesn't
    exist here raises AttributeError instead of returning another Mock."""

    def __init__(self, documents, metadatas):
        self._documents = documents
        self._metadatas = metadatas

    def get(self, include=None):
        return {"documents": self._documents, "metadatas": self._metadatas}


class _FakeVectorStore:
    def __init__(self, collection: _FakeChromaCollection):
        self._collection = collection


class _FakeKnowledgeBase:
    """Exposes only the attributes a real KnowledgeBase has -- no
    `chroma_collection`, so the pre-fix code would AttributeError here too."""

    def __init__(self, collection: _FakeChromaCollection):
        self.vector_store = _FakeVectorStore(collection)


@pytest.mark.asyncio
async def test_fetch_all_chunks_reads_the_real_collection_handle():
    collection = _FakeChromaCollection(
        documents=["first chunk", "second chunk"],
        metadatas=[{"source": "a"}, {"source": "b"}],
    )
    kb = _FakeKnowledgeBase(collection)

    chunks = await _fetch_all_chunks(kb)

    assert chunks == [
        {"text": "first chunk", "metadata": {"source": "a"}},
        {"text": "second chunk", "metadata": {"source": "b"}},
    ]


@pytest.mark.asyncio
async def test_fetch_all_chunks_defaults_missing_metadata_to_empty_dicts():
    collection = _FakeChromaCollection(documents=["only chunk"], metadatas=None)
    kb = _FakeKnowledgeBase(collection)

    chunks = await _fetch_all_chunks(kb)

    assert chunks == [{"text": "only chunk", "metadata": {}}]


def test_the_double_has_no_chroma_collection_attribute():
    """Control: proves the double would have caught the original bug."""
    kb = _FakeKnowledgeBase(_FakeChromaCollection([], []))
    assert not hasattr(kb, "chroma_collection")
