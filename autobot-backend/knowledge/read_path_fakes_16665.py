# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fake knowledge base with one private fact per user, for the #16665 read-path tests.

The ownership manager is the real :class:`KnowledgeOwnership`, so a test exercises the one
canonical visibility decision rather than a stand-in for it.
"""

from autobot_shared.ssot_config import config
from knowledge.ownership import KnowledgeOwnership
from knowledge.quarantine import apply_quarantine, gate_response

PRIVATE_A = "alice private fact"
PRIVATE_B = "bob private fact"
SHARED = "platform wide fact"
RESEARCH = "quarantined research finding"


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


def quarantined_fact() -> dict:
    """A platform-wide fact held in the research quarantine: only the quarantine can hide it."""
    return _fact(
        "f-q", RESEARCH, owner_id="admin", visibility="system", collection=config.research_quarantine_collection
    )


class QuarantineGatedKB(FakeKB):
    """A KB holding one quarantined fact, read through the real quarantine gate ``KB.search`` ends with.

    A route that asks for the default read gets the gated answer; one that opted out would get the fact.
    ``dict_results`` shapes ``search`` like the enhanced mode (``{"results": [...]}``);
    ``only_quarantined`` makes the quarantined fact the sole fact, so a leak has nothing else to hide behind.
    """

    def __init__(self, dict_results: bool = False, only_quarantined: bool = False):
        super().__init__()
        self.dict_results = dict_results
        self.only_quarantined = only_quarantined

    def _held(self) -> list[dict]:
        return [quarantined_fact()] if self.only_quarantined else all_facts() + [quarantined_fact()]

    async def search(self, *args, include_unservable=False, include_quarantined=False, audit_actor=None, **kwargs):
        hits = await gate_response(self._held(), include_unservable, include_quarantined, audit_actor)
        return {"results": hits} if self.dict_results else hits

    async def get_all_facts(self, limit=None, include_quarantined=False, audit_actor=None):
        return await apply_quarantine(self._held(), include_quarantined, audit_actor)
