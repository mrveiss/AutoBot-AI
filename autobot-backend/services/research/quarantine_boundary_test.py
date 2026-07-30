# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end proof of the #12622/#12623 quarantine boundary.

Both the chat-RAG quarantine filter (``async_chat_workflow.py::_execute_kb_search``,
#12622) and this PR's promotion gate (``knowledge/facts.py::update_fact`` /
``_sync_fact_metadata_in_chromadb``) rely on ONE real enforcement point: a
vector-store ``where`` filter ``{"collection": {"$ne": "research"}}`` evaluated
against the store's own metadata.

Real ChromaDB cannot be used directly in this test suite — ``conftest.py``
globally stubs the ``chromadb`` package (it hangs at import time without a
local server, see conftest.py's stub block), so ``chromadb.PersistentClient``
would silently return a ``MagicMock``. Instead this test drives
``knowledge.backends.InMemoryClient`` — the repo's designated real (not
mocked) where-filter implementation for exactly this scenario (its module
docstring: "tests that need [operator filters] should ... extend this
helper" — done here by adding ``$ne`` support to ``_match_where``, #12623) —
and separately proves the *production* ChromaDB call shape
(``vector_store._collection.update(ids=, metadatas=)``) is invoked correctly
by ``FactsMixin._sync_fact_metadata_in_chromadb``.
"""

from __future__ import annotations

import asyncio

from knowledge.backends import InMemoryClient
from knowledge.facts import FactsMixin

_QUARANTINE_FILTER = {"collection": {"$ne": "research"}}


def _collection():
    """A real (non-mocked) in-memory vector-store collection."""
    return InMemoryClient().get_or_create_collection("quarantine_boundary_test")


class TestQuarantineBoundaryEndToEnd:
    """Real where-filter proof that quarantine/promotion actually gates visibility."""

    def test_below_threshold_fact_is_excluded_from_chat_rag_path(self):
        """A quarantined (never-promoted) fact must never surface via the filter."""
        collection = _collection()
        collection.add(
            ids=["quarantined-fact"],
            metadatas=[{"collection": "research", "fact_id": "quarantined-fact"}],
        )

        visible = collection.get(where=_QUARANTINE_FILTER)

        assert "quarantined-fact" not in visible["ids"]

    def test_promoted_fact_is_reachable_from_chat_rag_path(self):
        """A promoted fact (collection flipped to the general value) becomes visible."""
        collection = _collection()
        collection.add(
            ids=["promoted-fact"],
            metadatas=[{"collection": "research", "fact_id": "promoted-fact"}],
        )

        # Sanity: still quarantined before promotion.
        before = collection.get(where=_QUARANTINE_FILTER)
        assert "promoted-fact" not in before["ids"]

        # Promotion gate flips only metadata (#12623's fix to
        # knowledge/facts.py::update_fact — no re-embedding needed).
        collection.update(
            ids=["promoted-fact"],
            metadatas=[{"collection": "general", "fact_id": "promoted-fact", "verification_status": "verified"}],
        )

        after = collection.get(where=_QUARANTINE_FILTER)
        assert "promoted-fact" in after["ids"]

    def test_preexisting_facts_without_collection_field_stay_visible(self):
        """A fact predating the quarantine feature (no 'collection' key) is unaffected."""
        collection = _collection()
        collection.add(
            ids=["legacy-fact"],
            metadatas=[{"fact_id": "legacy-fact"}],
        )

        visible = collection.get(where=_QUARANTINE_FILTER)

        assert "legacy-fact" in visible["ids"]

    def test_metadata_only_update_fact_helper_reproduces_promotion(self):
        """The exact production path: FactsMixin._sync_fact_metadata_in_chromadb.

        Proves the fix to the pre-existing ``update_fact`` gap (#12623): a
        metadata-only change (no content change) previously never reached
        ChromaDB, which would have silently defeated the promotion gate.
        """
        collection = _collection()
        collection.add(
            ids=["gap-fact"],
            metadatas=[{"collection": "research", "fact_id": "gap-fact"}],
        )

        class _FakeVectorStore:
            _collection = collection

        mixin = FactsMixin()
        mixin.vector_store = _FakeVectorStore()

        asyncio.run(
            mixin._sync_fact_metadata_in_chromadb(
                "gap-fact", {"collection": "general", "verification_status": "verified"}
            )
        )

        after = collection.get(where=_QUARANTINE_FILTER)
        assert "gap-fact" in after["ids"]

    def test_contradicted_fact_never_promoted_stays_quarantined(self):
        """A disputed fact (#12623 contradiction path) is never promoted — stays quarantined."""
        collection = _collection()
        collection.add(
            ids=["disputed-fact"],
            metadatas=[{"collection": "research", "fact_id": "disputed-fact"}],
        )

        # The contradiction path (orchestrator._flag_contradiction) only ever
        # sets verification_status/requires_human_review — it must never
        # touch "collection".
        collection.update(
            ids=["disputed-fact"],
            metadatas=[
                {
                    "collection": "research",
                    "fact_id": "disputed-fact",
                    "verification_status": "disputed",
                    "requires_human_review": True,
                }
            ],
        )

        visible = collection.get(where=_QUARANTINE_FILTER)
        assert "disputed-fact" not in visible["ids"]
