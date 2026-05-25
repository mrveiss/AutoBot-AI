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

    def __init__(self, rag_assembler: LLCRAGAssembler):
        """Initialize resolver with RAG assembler.

        Args:
            rag_assembler: RAG service for KB queries
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
            from user_management.models.organization import Organization
            from sqlalchemy import select

            # Fetch company
            company_uuid = uuid.UUID(company_id)
            stmt = select(Organization).where(Organization.id == company_uuid)
            result = await session.execute(stmt)
            company = result.scalar_one_or_none()

            if not company:
                raise ValueError(f"Company {company_id} not found")

            # Walk parent chain from company to root
            collections = []
            current = company
            weight = 1.0
            visited: set[uuid.UUID] = {company_uuid}

            while current:
                weight_multiplier = current.kb_inheritance_weight
                collections.append((f"{str(current.id)}:company", weight))

                # Move to parent if exists
                if current.parent_org_id:
                    # Cycle detection: break if we've seen this org before
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

    async def search_with_inheritance(
        self,
        session: AsyncSession,
        company_id: str,
        query_text: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search KB across company hierarchy and re-rank by weight.

        Issues parallel RAG queries across all collections in the inheritance
        chain, then merges and re-ranks results by score * weight.

        Args:
            session: DB session
            company_id: Company UUID to search from
            query_text: Query text for similarity search
            top_k: Number of top results to return

        Returns:
            List of merged KbResult-like dicts with source_company_id annotation,
            sorted by weighted score (descending).
        """
        try:
            # Get collections with weights
            collections = await self.get_query_collections(session, company_id)

            if not collections:
                logger.warning("No KB collections found for company %s", company_id)
                return []

            # Issue parallel queries across all collections
            tasks = []
            for collection_name, weight in collections:
                # Extract company_id from collection_name (format: "comp-uuid:company")
                source_company_id = collection_name.split(":")[0]

                task = asyncio.create_task(
                    self.rag_assembler.assemble(
                        company_id=source_company_id,
                        profile=AssemblerProfile.HEARTBEAT,
                        query_text=query_text,
                    )
                )
                tasks.append((task, source_company_id, weight))

            # Gather results
            results = await asyncio.gather(
                *[task for task, _, _ in tasks],
                return_exceptions=True,
            )

            # Merge and re-rank by weighted score
            merged = {}  # doc_id -> {score, weight, source_company_id, ...}

            for (task, source_company_id, weight), result in zip(tasks, results):
                if isinstance(result, Exception):
                    logger.warning(
                        "Query failed for collection %s: %s",
                        source_company_id,
                        result,
                    )
                    continue

                # Extract chunks from result (result is LLCContext)
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

                    # Use similarity_score from production (fallback to score for tests)
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

            # Sort by weighted_score descending and return top_k
            sorted_results = sorted(
                merged.values(),
                key=lambda x: x["weighted_score"],
                reverse=True,
            )[:top_k]

            logger.debug(
                "Merged %d results from %d collections for company %s, returning top %d",
                len(merged),
                len(collections),
                company_id,
                len(sorted_results),
            )
            return sorted_results

        except Exception as e:
            logger.error("Failed to search KB with inheritance for company %s: %s", company_id, e)
            raise
