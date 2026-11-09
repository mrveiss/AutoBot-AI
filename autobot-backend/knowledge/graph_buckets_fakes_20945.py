# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Real in-memory collections and a fact-listing KB for the knowledge-graph tests (#20945); no mocks."""

from typing import Any, Dict, List

from knowledge.backends.async_memory_adapter import AsyncInMemoryClient
from knowledge.graph_bucket_visibility import Viewer
from knowledge.ownership import KnowledgeOwnership
from knowledge.root_read import AdminReadLedger

ALICE = "alice"
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def manager() -> KnowledgeOwnership:
    """The real access check the facts path uses."""
    return KnowledgeOwnership(redis_client=object())


def viewer(user_id: str = ALICE, company: str | None = TENANT_A, admin: bool = False, superadmin: bool = False):
    return Viewer(user_id, company, (), superadmin, AdminReadLedger() if (admin or superadmin) else False)


async def client_with(records: Dict[str, List[tuple]]) -> AsyncInMemoryClient:
    """``{collection: [(id, metadata), ...]}`` as a real in-memory ChromaDB client; the document is ``doc <id>``."""
    client = AsyncInMemoryClient()
    for name, rows in records.items():
        col = await client.get_or_create_collection(name)
        if rows:
            await col.add(
                ids=[rid for rid, _ in rows],
                documents=[f"doc {rid}" for rid, _ in rows],
                metadatas=[dict(meta) or {"k": "v"} for _, meta in rows],
                embeddings=[[0.1, 0.2]] * len(rows),
            )
    return client


def fact(fact_id: str, owner: str, visibility: str = "private") -> Dict[str, Any]:
    return {"fact_id": fact_id, "content": f"fact {fact_id}", "metadata": {"owner_id": owner, "visibility": visibility}}


class ListingKB:
    """A KB whose listings honour ``limit``/``offset`` like the real ones; ``calls`` records each listing."""

    def __init__(self, facts: List[Dict[str, Any]], chroma_client: Any = None):
        self.facts = facts
        self.ownership_manager = manager()
        self._async_chroma_client = chroma_client
        self.calls: List[tuple] = []

    async def get_all_facts(self, limit=None, offset=0):
        self.calls.append(("all", limit, offset))
        return self.facts[offset : offset + limit if limit else None]

    async def get_facts_in_category(self, category_id, include_descendants=False, limit=50, offset=0):
        self.calls.append(("category", limit, offset))
        page = self.facts[offset : offset + limit]
        return {
            "success": True,
            "facts": [{**f, "id": f["fact_id"]} for f in page],
            "has_more": offset + limit < len(self.facts),
        }

    def get_fact(self, fact_id):
        """The sync lookup the summary visibility pass uses."""
        return next((f for f in self.facts if f["fact_id"] == fact_id), None)
