# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Summary Search Service - Search and navigate hierarchical summaries.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from typing import List
from uuid import UUID

from autobot_shared.logging_manager import get_logger
from knowledge.quarantine import is_quarantined, without_quarantine
from knowledge.where_combine import and_where

logger = get_logger(__name__)


class SummarySearchService:
    """Search and navigate hierarchical document summaries."""

    def __init__(self, chromadb_client) -> None:
        """
        Initialize summary search service.

        Args:
            chromadb_client: ChromaDB client instance
        """
        self.client = chromadb_client
        self.collection_name = "knowledge_summaries"

    async def search_summaries(self, query: str, level: str | None = None, top_k: int = 10) -> List[dict]:
        """
        Vector search on summary embeddings.

        Args:
            query: Search query text
            level: Filter by summary level (chunk, section, document)
            top_k: Number of results to return

        Returns:
            List of matching summaries with scores
        """
        try:
            collection = await self.client.get_collection(name=self.collection_name)

            # #19163: summaries of a research-quarantined fact are never served here.
            where_filter = without_quarantine({"level": level} if level else None)

            results = await collection.query(query_texts=[query], n_results=top_k, where=where_filter)

            summaries = self._format_results(results)
            logger.info("Found %s matching summaries", len(summaries))
            return summaries

        except Exception as e:
            logger.error("Summary search failed: %s", e)
            return []

    async def get_document_overview(self, document_id: UUID) -> dict:
        """
        Get document overview with document and section summaries.

        Args:
            document_id: Source document ID

        Returns:
            Dictionary with document and section summaries
        """
        try:
            collection = await self.client.get_collection(name=self.collection_name)

            # Get document-level summary
            doc_results = await collection.get(where=self._visible_where(str(document_id), "document"))

            # Get section-level summaries
            section_results = await collection.get(where=self._visible_where(str(document_id), "section"))

            overview = {
                "document_id": str(document_id),
                "document_summary": self._format_get_results(doc_results),
                "section_summaries": self._format_get_results(section_results),
            }

            logger.info(
                "Retrieved overview for document %s: %s sections",
                document_id,
                len(overview["section_summaries"]),
            )
            return overview

        except Exception as e:
            logger.error("Document overview retrieval failed: %s", e)
            return {
                "document_id": str(document_id),
                "document_summary": None,
                "section_summaries": [],
            }

    async def drill_down(self, summary_id: UUID) -> dict:
        """
        Navigate from summary to children or source chunks.

        Args:
            summary_id: Summary ID to drill down from

        Returns:
            Dictionary with summary and its children/chunks
        """
        try:
            collection = await self.client.get_collection(name=self.collection_name)

            # Get the summary
            summary_results = await collection.get(ids=[str(summary_id)])

            if not summary_results["ids"] or self._is_withheld(summary_results):
                logger.warning("Summary not found: %s", summary_id)
                return {"summary": None, "children": []}

            summary = self._format_get_results(summary_results)[0]

            # Get child summaries
            parent_id = str(summary_id)
            child_results = await collection.get(where=without_quarantine({"parent_summary_id": parent_id}))

            children = self._format_get_results(child_results)

            result = {
                "summary": summary,
                "children": children,
                "level": summary["metadata"].get("level"),
            }

            logger.info(
                "Drill down from %s: %s children",
                summary_id,
                len(children),
            )
            return result

        except Exception as e:
            logger.error("Drill down failed: %s", e)
            return {"summary": None, "children": []}

    @staticmethod
    def _visible_where(document_id: str, level: str) -> dict:
        """A document's summaries at *level*, minus the research-quarantined ones (#19163)."""
        clauses = ({"document_id": document_id}, {"level": level}, without_quarantine())
        return and_where(*clauses)  # type: ignore[return-value]

    @staticmethod
    def _is_withheld(get_results: dict) -> bool:
        """Whether the one summary a ``get`` returned derives from a quarantined fact (#19163)."""
        metadatas = get_results.get("metadatas") or []
        return any(is_quarantined({"metadata": m or {}}) for m in metadatas)

    def _format_results(self, results: dict) -> List[dict]:
        """Format ChromaDB query results."""
        summaries = []
        if not results or not results.get("ids"):
            return summaries

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results.get("distances", [[]])[0]

        for i, summary_id in enumerate(ids):
            summaries.append(
                {
                    "id": summary_id,
                    "content": documents[i],
                    "metadata": metadatas[i],
                    "score": 1.0 - distances[i] if distances else 1.0,
                }
            )

        return summaries

    def _format_get_results(self, results: dict) -> List[dict]:
        """Format ChromaDB get results."""
        summaries = []
        if not results or not results.get("ids"):
            return summaries

        ids = results["ids"]
        documents = results["documents"]
        metadatas = results["metadatas"]

        for i, summary_id in enumerate(ids):
            summaries.append(
                {
                    "id": summary_id,
                    "content": documents[i],
                    "metadata": metadatas[i],
                }
            )

        return summaries
