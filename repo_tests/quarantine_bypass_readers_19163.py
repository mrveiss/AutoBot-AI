# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Readers that bypass ``KB.search`` and carry no quarantine filter, each with the proof they need none (#19163).

A reader that can put KB content in an LLM prompt or a user/API response applies
``knowledge.quarantine.without_quarantine`` (or ``servable_unquarantined``). A reader listed here is
proven unable to see a research-quarantined chunk: it reads a collection that the research path never
writes, and ``repo_tests/quarantine_bypass_readers_19163_test.py`` re-checks the proof from source.
"""

from __future__ import annotations

PROVEN_NO_QUARANTINED_ROWS: dict[str, str] = {
    "autobot-backend/services/knowledge/doc_indexer.py": (
        "DocIndexerService.search reads the 'autobot_docs' collection. Its only writer is "
        "DocIndexerService._index_chunk (the metadata dict literal), which indexes files under docs/ "
        "with a fixed key set that has no 'collection' key; research findings land in the KB fact store "
        "(ResearchOrchestrator), never in 'autobot_docs'. A row without the marker is not quarantined."
    ),
    "autobot-backend/knowledge/rag_benchmarks.py": (
        "The benchmark reads chromadb.EphemeralClient() collections seeded in-process from the static "
        "_TOPIC_DOCS corpus; it never opens the KB store, so no KB fact (quarantined or not) can be in it."
    ),
}
