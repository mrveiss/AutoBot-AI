# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read the company's agent-capability collection for ``GET /agent/peers/search``.

Extracted from ``agent_api.search_peer_agents`` unchanged, to keep ``agent_api`` under the
file-size ceiling (#16016). The knowledge-base imports stay lazy, inside the function, so
patching ``knowledge.get_knowledge_base`` still reaches it.
"""

from typing import Any, Dict, List, Optional, Tuple


async def fetch_peer_rows(company_id: str, q: str, limit: int) -> Optional[List[Tuple[Dict[str, Any], str]]]:
    """Return ``(metadata, document)`` per match, or ``None`` when the company has no collection."""
    from knowledge import get_knowledge_base

    from ..kb import AgentCapabilityIndexer

    indexer = AgentCapabilityIndexer()
    kb = await get_knowledge_base()
    collection_name = indexer._collection_name(company_id)

    try:
        collection = await kb._async_chroma_client.get_collection(collection_name)
    except Exception:
        return None

    results = await collection.query(
        query_texts=[q],
        n_results=min(limit, 50),
        include=["documents", "metadatas"],
    )

    rows: List[Tuple[Dict[str, Any], str]] = []
    if results.get("ids") and len(results["ids"]) > 0:
        docs = results.get("documents", [[]])[0] if results.get("documents") else []
        metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
        for idx, (_doc_id, metadata) in enumerate(zip(results["ids"][0], metadatas)):
            rows.append((metadata, docs[idx] if idx < len(docs) else ""))
    return rows
