# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Work item KB ingestion and retrieval (GH#8232).

Each work item has a dedicated ChromaDB collection ``work_item:{work_item_id}``.
Human notes, attachment text (text/markdown/code only), and any other
human-authored context are stored here so the agent that picks up the item
can retrieve them via ``get_context()``.

Binary files are NOT indexed — only text/markdown/code content is ingested.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml")
_TEXT_EXTENSIONS = {".md", ".txt", ".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".rb", ".sh", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sql", ".html", ".css", ".jsx", ".tsx"}


def _collection_name(work_item_id: str) -> str:
    return f"work_item:{work_item_id}"


def _is_text_indexable(filename: Optional[str], mime_type: Optional[str]) -> bool:
    """Return True if the file content should be indexed into the KB."""
    if mime_type:
        for prefix in _TEXT_MIME_PREFIXES:
            if mime_type.startswith(prefix):
                return True
    if filename:
        import os
        ext = os.path.splitext(filename)[1].lower()
        if ext in _TEXT_EXTENSIONS:
            return True
    return False


class WorkItemKB:
    """Manages the per-work-item ChromaDB knowledge collection."""

    async def ingest_notes(
        self,
        work_item_id: str,
        notes: str,
        source_user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Index human notes into the work item KB collection.

        Returns:
            The document ID inserted into ChromaDB (stable: ``notes:{work_item_id}``).
        """
        doc_id = f"notes:{work_item_id}"
        meta = {
            "work_item_id": work_item_id,
            "source": "human_notes",
            "source_user_id": source_user_id,
            **(metadata or {}),
        }
        await self._upsert(work_item_id, doc_id, notes, meta)
        return doc_id

    async def ingest_attachment(
        self,
        work_item_id: str,
        attachment_id: str,
        filename: str,
        content: str,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Index a text attachment into the work item KB.

        Returns:
            The document ID if indexed, or None if the file type is binary.
        """
        if not _is_text_indexable(filename, mime_type):
            logger.debug(
                "Skipping binary attachment %s (mime=%s) for work_item %s",
                filename,
                mime_type,
                work_item_id,
            )
            return None

        doc_id = f"attachment:{attachment_id}"
        meta = {
            "work_item_id": work_item_id,
            "source": "attachment",
            "filename": filename,
            "attachment_id": attachment_id,
            **(metadata or {}),
        }
        await self._upsert(work_item_id, doc_id, content, meta)
        return doc_id

    async def get_context(
        self,
        work_item_id: str,
        query: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve KB chunks for a work item.

        When ``query`` is provided, performs similarity search; otherwise returns
        all stored documents (up to ``n_results``).

        Returns:
            List of dicts with ``id``, ``document``, and ``metadata`` keys.
        """
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            collection_name = _collection_name(work_item_id)
            try:
                collection = await client.get_collection(collection_name)
            except Exception:
                return []

            count = await collection.count()
            if count == 0:
                return []

            n = min(n_results, count)
            if query:
                results = await collection.query(
                    query_texts=[query],
                    n_results=n,
                    include=["documents", "metadatas"],
                )
                ids = results.get("ids", [[]])[0]
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
            else:
                results = await collection.get(
                    limit=n,
                    include=["documents", "metadatas"],
                )
                ids = results.get("ids", [])
                docs = results.get("documents", [])
                metas = results.get("metadatas", [])

            return [
                {"id": doc_id, "document": doc, "metadata": meta}
                for doc_id, doc, meta in zip(ids, docs, metas)
            ]
        except Exception:
            logger.exception(
                "Failed to retrieve KB context for work_item %s — returning empty",
                work_item_id,
            )
            return []

    async def _upsert(
        self,
        work_item_id: str,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> None:
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            collection = await client.get_or_create_collection(_collection_name(work_item_id))
            await collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[metadata],
            )
        except Exception:
            logger.exception(
                "Failed to upsert KB entry %s for work_item %s — non-fatal",
                doc_id,
                work_item_id,
            )


__all__ = ["WorkItemKB"]
