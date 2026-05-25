# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC KB inheritance resolver — parent KB read-through with weight decay (GH#8241).

Sub-companies automatically inherit parent company KB collections via read-through.
A subsidiary can use parent LLC standards without duplicating them, while still
prioritizing its own company context through weight decay.
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from .rag_assembler import AssemblerProfile, LLCRAGAssembler

logger = get_logger(__name__)


class KbInheritanceResolver:
    """Resolve KB collections across a company hierarchy with weight decay.

    Walks parent_org_id chain from company to root, returning weighted collections.
    Merges results by score * weight, prioritizing own company (1.0) over parent (0.6),
    grandparent (0.36), etc. (configurable multiplier, default 0.6 per level).
    """

    def __init__(self, rag_assembler: Optional[LLCRAGAssembler] = None):
        """Initialize resolver with optional RAG assembler.

        Args:
            rag_assembler: RAG service for KB queries (required only for search_with_inheritance
                and search_with_collections; not needed for get_query_collections alone).
        """
        self.rag_assembler = rag_assembler

    async def get_query_collections(
        self,
        session: AsyncSession,
        company_id: str,
    ) -> List[Tuple[str, float]]:
        """Get list of collections to query, with weights for inheritance.

        Walks parent_org_id chain from company to root, returning list of
        (collection_name, weight) tuples. Weight starts at 1.0 for own company
        and decays by multiplier for each parent level.

        Args:
            session: DB session
            company_id: Company UUID to start from

        Returns:
            List of (collection_name, weight) tuples, in order from company to root.
            Example: [("comp-123:company", 1.0), ("comp-parent:company", 0.6), ("comp-root:company", 0.36)]

        Raises:
            ValueError: If company_id not found
        """
        try:
            from sqlalchemy import select

            from user_management.models.organization import Organization

            company_uuid = uuid.UUID(company_id)
            stmt = select(Organization).where(Organization.id == company_uuid)
            result = await session.execute(stmt)
            company = result.scalar_one_or_none()

            if not company:
                raise ValueError(f"Company {company_id} not found")

            collections = []
            current = company
            weight = 1.0
            visited: set[uuid.UUID] = {company_uuid}

            while current:
                weight_multiplier = current.kb_inheritance_weight
                collections.append((f"{str(current.id)}:company", weight))

                if current.parent_org_id:
                    if current.parent_org_id in visited:
                        logger.warning(
                            "Circular parent_org_id detected for company %s, stopping traversal",
                            company_id,
                        )
                        break
                    visited.add(current.parent_org_id)

                    stmt = select(Organization).where(Organization.id == current.parent_org_id)
                    result = await session.execute(stmt)
                    current = result.scalar_one_or_none()
                    weight *= weight_multiplier
                else:
                    current = None

            logger.debug(
                "Resolved %d KB collections for company %s: %s",
                len(collections),
                company_id,
                collections,
            )
            return collections

        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to resolve KB collections for company %s: %s", company_id, e)
            raise

    async def search_with_collections(
        self,
        collections: List[Tuple[str, float]],
        query_text: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search KB across pre-fetched collection chain and re-rank by weight.

        Runs parallel RAG queries without a DB session — call get_query_collections()
        first to obtain the list. Uses coroutines directly in asyncio.gather to avoid
        orphaned tasks on cancellation (GH#8569).

        Args:
            collections: List of (collection_name, weight) from get_query_collections()
            query_text: Query text for similarity search
            top_k: Number of top results to return

        Returns:
            List of merged KbResult-like dicts with source_company_id annotation,
            sorted by weighted score (descending).
        """
        if not self.rag_assembler:
            raise RuntimeError("rag_assembler required for search_with_collections")

        if not collections:
            return []

        # Build (coroutine, source_company_id, weight) triples — coroutines, not Tasks,
        # so cancellation of the gather also cancels each query (GH#8569).
        coro_specs = [
            (
                self.rag_assembler.assemble(
                    company_id=collection_name.split(":")[0],
                    profile=AssemblerProfile.HEARTBEAT,
                    query_text=query_text,
                ),
                collection_name.split(":")[0],
                weight,
            )
            for collection_name, weight in collections
        ]

        results = await asyncio.gather(
            *[coro for coro, _, _ in coro_specs],
            return_exceptions=True,
        )

        merged: Dict[str, Any] = {}

        for (_, source_company_id, weight), result in zip(coro_specs, results):
            if isinstance(result, Exception):
                logger.warning("Query failed for collection %s: %s", source_company_id, result)
                continue

            if hasattr(result, "chunks"):
                chunks = result.chunks
            elif isinstance(result, dict) and "chunks" in result:
                chunks = result["chunks"]
            else:
                chunks = []

            for chunk in chunks:
                doc_id = chunk.get("id", chunk.get("metadata", {}).get("id"))
                if not doc_id:
                    continue

                score = chunk.get("similarity_score", chunk.get("score", 0.0))
                weighted_score = score * weight

                if doc_id not in merged or merged[doc_id]["weighted_score"] < weighted_score:
                    merged[doc_id] = {
                        "id": doc_id,
                        "content": chunk.get("content", ""),
                        "score": score,
                        "weight": weight,
                        "weighted_score": weighted_score,
                        "source_company_id": source_company_id,
                        "metadata": chunk.get("metadata", {}),
                    }

        sorted_results = sorted(
            merged.values(),
            key=lambda x: x["weighted_score"],
            reverse=True,
        )[:top_k]

        logger.debug(
            "Merged %d results from %d collections, returning top %d",
            len(merged),
            len(collections),
            len(sorted_results),
        )
        return sorted_results

    async def search_with_inheritance(
        self,
        session: AsyncSession,
        company_id: str,
        query_text: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search KB across company hierarchy and re-rank by weight.

        Resolves the collection chain from DB sequentially, then issues parallel
        RAG queries via search_with_collections. The DB session is not passed to
        any concurrent task (GH#8566 fix).

        Args:
            session: DB session (used only for the sequential collection lookup)
            company_id: Company UUID to search from
            query_text: Query text for similarity search
            top_k: Number of top results to return

        Returns:
            List of merged KbResult-like dicts with source_company_id annotation,
            sorted by weighted score (descending).
        """
        try:
            collections = await self.get_query_collections(session, company_id)

            if not collections:
                logger.warning("No KB collections found for company %s", company_id)
                return []

            return await self.search_with_collections(collections, query_text, top_k)

        except Exception as e:
            logger.error("Failed to search KB with inheritance for company %s: %s", company_id, e)
            raise
