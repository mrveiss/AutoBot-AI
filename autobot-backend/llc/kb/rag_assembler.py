# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC RAG assembler interface (GH#8261).

GH#8236 (heartbeat context builder) and GH#8239 (handoff brief generator)
both construct multi-source RAG queries over company/project/agent KB
collections. This module provides a shared assembler with swappable query
profiles so neither issue needs to duplicate ChromaDB call patterns.

Concrete implementation lives in GH#8236. This file provides the interface
stub so dependent issues can import and type-check against it.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class AssemblerProfile(str, Enum):
    """Query profile for RAG context assembly.

    HEARTBEAT: full organisation context for agent heartbeat runs.
    HANDOFF:   transition brief for agent-to-agent handoff.
    SUGGESTION: acceptance-criteria hints during work item creation.
    """

    HEARTBEAT = "heartbeat"
    HANDOFF = "handoff"
    SUGGESTION = "suggestion"


@dataclass
class LLCContext:
    """Assembled RAG context returned by LLCRAGAssembler.assemble()."""

    company_id: str
    profile: AssemblerProfile
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLCRAGAssembler:
    """Assembles multi-source RAG context for LLC operations.

    Both GH#8236 and GH#8239 use this rather than calling ChromaDB directly,
    ensuring consistent collection names, query parameters, and result merging.
    """

    async def assemble(
        self,
        company_id: str,
        profile: AssemblerProfile,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        work_item_id: Optional[str] = None,
        query_text: str = "",
    ) -> LLCContext:
        """Run parallel ChromaDB queries and return merged context (GH#8236).

        Queries ChromaDB collections scoped by company, project, and agent.
        Each query has a ≤800ms timeout target (4 parallel queries → P95 ≤ 2s).

        Args:
            company_id: Tenant company identifier.
            profile: Which query profile to use (HEARTBEAT, HANDOFF, SUGGESTION).
            project_id: Optional project scope filter.
            agent_id: Optional agent scope filter.
            work_item_id: Optional work item context for relevance ranking.
            query_text: Query text for similarity search (e.g., work item title + description).

        Returns:
            LLCContext with merged chunks from all relevant collections.
        """
        try:
            try:
                from utils.async_chromadb_client import get_async_chromadb_client
            except ImportError as e:
                logger.error("ChromaDB client not available: %s", e)
                raise

            client = await get_async_chromadb_client()

            # Determine query parameters based on profile
            query_params = self._get_query_params(profile, project_id, agent_id, query_text)

            # Build ChromaDB collection names (scope: company, project, agent)
            collections_to_query = []
            if project_id:
                collections_to_query.append(f"{company_id}:project:{project_id}")
            if agent_id:
                collections_to_query.append(f"{company_id}:agent:{agent_id}")
            collections_to_query.append(f"{company_id}:company")

            # Query all collections in parallel (each ≤ 800ms target)
            tasks = [
                self._query_collection(client, coll_name, query_params["query_text"], query_params["n_results"])
                for coll_name in collections_to_query
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Merge results from all collections
            all_chunks: List[Dict[str, Any]] = []
            all_sources: List[str] = []

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning("ChromaDB query failed for %s: %s", collections_to_query[i], result)
                    continue

                all_chunks.extend(result.get("chunks", []))
                all_sources.extend(result.get("sources", []))

            return LLCContext(
                company_id=company_id,
                profile=profile,
                chunks=all_chunks,
                sources=list(dict.fromkeys(all_sources)),  # dedup
                metadata={
                    "collections_queried": collections_to_query,
                    "total_results": len(all_chunks),
                },
            )

        except Exception as e:
            logger.exception("LLCRAGAssembler.assemble() failed: %s", e)
            # Return empty context on failure (graceful degradation)
            return LLCContext(
                company_id=company_id,
                profile=profile,
                chunks=[],
                sources=[],
                metadata={"error": str(e)},
            )

    def _get_query_params(
        self,
        profile: AssemblerProfile,
        project_id: Optional[str],
        agent_id: Optional[str],
        query_text: str = "",
    ) -> Dict[str, Any]:
        """Get query parameters based on profile and scope.

        Args:
            profile: Query profile (HEARTBEAT, HANDOFF, SUGGESTION).
            project_id: Optional project scope.
            agent_id: Optional agent scope.
            query_text: Query text for similarity search.

        Returns:
            Dict with query_text and n_results parameters.
        """
        params = {
            "query_text": query_text,
            "n_results": 5,
        }

        if profile == AssemblerProfile.HEARTBEAT:
            # Full context: company=5, project=8, agent=5
            if project_id:
                params["n_results"] = 8
            elif agent_id:
                params["n_results"] = 5
            else:
                params["n_results"] = 5

        elif profile == AssemblerProfile.HANDOFF:
            params["n_results"] = 3

        elif profile == AssemblerProfile.SUGGESTION:
            params["n_results"] = 2

        return params

    async def _query_collection(
        self,
        client: Any,
        collection_name: str,
        query_text: str,
        n_results: int,
    ) -> Dict[str, Any]:
        """Query a single ChromaDB collection (≤ 800ms target).

        Args:
            client: Async ChromaDB client.
            collection_name: Name of collection to query.
            query_text: Query text for similarity search.
            n_results: Number of results to return.

        Returns:
            Dict with chunks and sources from collection.
        """
        try:
            collection = await client.get_or_create_collection(collection_name)
            results = await collection.query(
                query_texts=[query_text],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            chunks = []
            sources = []

            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    metadata = (results.get("metadatas", [[]])[0][i]) if results.get("metadatas") else {}
                    distance = (results.get("distances", [[]])[0][i]) if results.get("distances") else 0.0

                    chunks.append(
                        {
                            "content": doc,
                            "metadata": metadata,
                            "similarity_score": 1.0 - distance,  # Convert distance to similarity
                            "source": collection_name,
                        }
                    )
                    sources.append(collection_name)

            return {"chunks": chunks, "sources": sources}

        except Exception as e:
            logger.warning("Failed to query collection %s: %s", collection_name, e)
            return {"chunks": [], "sources": []}
