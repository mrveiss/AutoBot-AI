# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""ArtifactIngestor — indexes work product artifacts into the project KB (GH#8242).

Called automatically when a work item transitions to ``done`` via WorkItemService.
Reads ``content_text`` or fetches text from ``storage_path`` (text-only; binary
files are skipped with ``kb_indexed = false``).

Text is split into ≤1000-token chunks (approximated as ≤4000 characters) and
added to the ``project:{project_id}`` ChromaDB collection with metadata that
links each chunk back to the source work item.
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.work_product import LLCWorkProduct

logger = logging.getLogger(__name__)

# Approximate 1 token ≈ 4 chars; target ≤1000 tokens ≈ 4000 chars per chunk.
_CHUNK_SIZE = 4000
_CHUNK_OVERLAP = 200

# Extensions treated as plain text (match WorkItemKB._TEXT_EXTENSIONS).
_TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".rb", ".sh", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".sql", ".html", ".css", ".jsx", ".tsx",
}


def _is_text_path(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in _TEXT_EXTENSIONS


def _split_text(text: str) -> List[str]:
    """Split text into overlapping chunks of ~_CHUNK_SIZE characters."""
    if len(text) <= _CHUNK_SIZE:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


class ArtifactIngestor:
    """Indexes work product text content into the project ChromaDB collection."""

    async def ingest(
        self,
        session: AsyncSession,
        work_product_id: str,
        project_id: Optional[str],
        work_item_identifier: str,
        completed_at: Optional[Any] = None,
    ) -> bool:
        """Read a work product row, chunk its text, index into project KB.

        Args:
            session: Async SQLAlchemy session.
            work_product_id: UUID of the ``llc_work_products`` row.
            project_id: UUID of the project (determines target collection).
            work_item_identifier: Human-readable identifier (e.g. ``MVA-123``).
            completed_at: When the work item was completed (used as metadata).

        Returns:
            True if indexed successfully; False if skipped (binary/no project).
        """
        from sqlalchemy import select

        result = await session.execute(
            select(LLCWorkProduct).where(LLCWorkProduct.id == uuid.UUID(work_product_id))
        )
        product = result.scalar_one_or_none()
        if product is None:
            logger.warning("ArtifactIngestor: work product %s not found", work_product_id)
            return False

        if not project_id:
            logger.info(
                "ArtifactIngestor: work product %s has no project — skipping KB index",
                work_product_id,
            )
            return False

        text = await self._resolve_text(product)
        if text is None:
            product.kb_indexed = False
            await session.flush()
            return False

        chunks = _split_text(text)
        collection_name = f"project:{project_id}"
        meta: Dict[str, Any] = {
            "work_item_id": str(product.work_item_id),
            "work_item_identifier": work_item_identifier,
            "product_type": product.type if isinstance(product.type, str) else product.type.value,
            "completed_at": str(completed_at) if completed_at else "",
            "work_product_id": str(product.id),
            "title": product.title,
        }

        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            collection = await client.get_or_create_collection(collection_name)
            ids = [f"wp:{product.id}:chunk:{i}" for i in range(len(chunks))]
            metadatas = [meta.copy() for _ in chunks]
            await collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
            logger.info(
                "ArtifactIngestor: indexed %d chunk(s) for work product %s into %s",
                len(chunks),
                work_product_id,
                collection_name,
            )
        except Exception:
            logger.exception(
                "ArtifactIngestor: failed to index work product %s — marking kb_indexed=false",
                work_product_id,
            )
            product.kb_indexed = False
            await session.flush()
            return False

        product.kb_indexed = True
        await session.flush()
        return True

    async def ingest_all_pending(
        self,
        session: AsyncSession,
        work_item_id: str,
        project_id: Optional[str],
        work_item_identifier: str,
        completed_at: Optional[Any] = None,
    ) -> int:
        """Ingest all non-indexed products for a work item (called on done transition).

        Returns:
            Number of products successfully indexed.
        """
        from sqlalchemy import select

        result = await session.execute(
            select(LLCWorkProduct).where(
                LLCWorkProduct.work_item_id == uuid.UUID(work_item_id),
                LLCWorkProduct.kb_indexed == False,  # noqa: E712
            )
        )
        products = result.scalars().all()
        count = 0
        for p in products:
            ok = await self.ingest(
                session,
                str(p.id),
                project_id,
                work_item_identifier,
                completed_at,
            )
            if ok:
                count += 1
        return count

    async def _resolve_text(self, product: LLCWorkProduct) -> Optional[str]:
        """Return indexable text from content_text or storage_path, or None to skip."""
        if product.content_text:
            return product.content_text

        if product.storage_path:
            if not _is_text_path(product.storage_path):
                logger.info(
                    "ArtifactIngestor: skipping binary storage_path %s for product %s",
                    product.storage_path,
                    product.id,
                )
                return None
            try:
                with open(product.storage_path, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            except Exception:
                logger.exception(
                    "ArtifactIngestor: could not read storage_path %s for product %s",
                    product.storage_path,
                    product.id,
                )
                return None

        logger.info(
            "ArtifactIngestor: work product %s has no text content — skipping",
            product.id,
        )
        return None


__all__ = ["ArtifactIngestor"]
