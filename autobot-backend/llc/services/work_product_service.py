# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""WorkProductService — CRUD for LLC work products (GH#8242)."""

import uuid
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkProductType
from ..models.work_product import LLCWorkProduct
from . import LLCServiceBase


class WorkProductService(LLCServiceBase):
    """Creates and retrieves work products; indexing is handled by ArtifactIngestor."""

    async def create(
        self,
        session: AsyncSession,
        company_id: str,
        work_item_id: str,
        type: WorkProductType,
        title: str,
        *,
        content_text: Optional[str] = None,
        storage_path: Optional[str] = None,
        url: Optional[str] = None,
        heartbeat_run_id: Optional[str] = None,
    ) -> LLCWorkProduct:
        product = LLCWorkProduct(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            work_item_id=uuid.UUID(work_item_id),
            type=type,
            title=title,
            content_text=content_text,
            storage_path=storage_path,
            url=url,
            heartbeat_run_id=uuid.UUID(heartbeat_run_id) if heartbeat_run_id else None,
        )
        session.add(product)
        await session.flush()
        return product

    async def list_by_work_item(
        self,
        session: AsyncSession,
        work_item_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LLCWorkProduct]:
        result = await session.execute(
            select(LLCWorkProduct)
            .where(LLCWorkProduct.work_item_id == uuid.UUID(work_item_id))
            .order_by(LLCWorkProduct.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def list_indexed_by_project(
        self,
        session: AsyncSession,
        project_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """Return recent KB-indexed artifacts for a project via ChromaDB query.

        Falls back to an empty list if ChromaDB is unavailable.
        """
        collection_name = f"project:{project_id}"
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            try:
                collection = await client.get_collection(collection_name)
            except Exception:
                return []

            count = await collection.count()
            if count == 0:
                return []

            n = min(limit, count)
            results = await collection.get(
                limit=n,
                offset=offset,
                include=["documents", "metadatas"],
            )
            ids = results.get("ids", [])
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            return [{"id": doc_id, "document": doc, "metadata": meta} for doc_id, doc, meta in zip(ids, docs, metas)]
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "WorkProductService.list_indexed_by_project: ChromaDB error for project %s",
                project_id,
            )
            return []
