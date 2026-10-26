# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fake knowledge base with one private fact per user, for the #16665 read-path tests.

The ownership manager is the real :class:`KnowledgeOwnership`, so a test exercises the one
canonical visibility decision rather than a stand-in for it.
"""

from knowledge.ownership import KnowledgeOwnership

PRIVATE_A = "alice private fact"
PRIVATE_B = "bob private fact"
SHARED = "platform wide fact"


def _fact(fact_id: str, content: str, **meta) -> dict:
    metadata = {"source": "doc", "category": "AGENT_DIARY", **meta}
    return {
        "id": fact_id,
        "fact_id": fact_id,
        "content": content,
        "score": 0.9,
        "similarity_score": 0.95,
        "metadata": metadata,
    }


def all_facts() -> list[dict]:
    return [
        _fact("f-a", PRIVATE_A, owner_id="alice", visibility="private"),
        _fact("f-b", PRIVATE_B, owner_id="bob", visibility="private"),
        _fact("f-s", SHARED, owner_id="admin", visibility="system"),
    ]


class FakeKB:
    """Returns every fact for any query, as a vector search does before visibility is applied."""

    def __init__(self):
        self.ownership_manager = KnowledgeOwnership(None)
        self.llm = None
        self.vector_store = object()

    async def search(self, *args, **kwargs):
        return all_facts()

    async def get_all_facts(self, limit=None):
        return all_facts()

    def get_fact(self, fact_id):
        return next((f for f in all_facts() if f["id"] == fact_id), None)

    async def record_fact_access(self, ids):
        return None


def text_of(value) -> str:
    """Every string reachable in *value*, joined, so an assertion cannot miss a nested copy."""
    return repr(value)
