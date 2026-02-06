# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Index Management Module

Contains the IndexMixin class for index rebuild operations and ChromaDB management.
Implements Issue #72 - Optimized HNSW parameters for 545K+ vectors.
Issue #369 - All ChromaDB operations wrapped with asyncio.to_thread() to prevent blocking.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


class IndexMixin:
    """
    Index management mixin for knowledge base.

    Provides methods for:
    - ChromaDB index rebuild with optimized HNSW parameters
    - Index information retrieval
    - Search index verification (V1 compatibility)

    Key Features:
    - Batch migration for large vector collections
    - HNSW parameter optimization (Issue #72)
    - V1 API compatibility
    """

    # Type hints for attributes from base class
    initialized: bool
    vector_store: "ChromaVectorStore"
    chromadb_path: str
    chromadb_collection: str
    hnsw_space: str
    hnsw_construction_ef: int
    hnsw_search_ef: int
    hnsw_m: int

    def _get_hnsw_metadata(self) -> Dict[str, Any]:
        """Get optimized HNSW parameters for 545K+ vectors."""
        return {
            "hnsw:space": self.hnsw_space,
            "hnsw:construction_ef": self.hnsw_construction_ef,
            "hnsw:search_ef": self.hnsw_search_ef,
            "hnsw:M": self.hnsw_m,
        }

    async def _prepare_target_collection(
        self, chroma_client: Any, target_name: str, hnsw_metadata: Dict[str, Any]
    ) -> Any:
        """Delete existing and create new collection with HNSW params."""
        logger.info(
            "Creating new collection '%s' with HNSW params: "
            "construction_ef=%d, search_ef=%d, M=%d",
            target_name,
            self.hnsw_construction_ef,
            self.hnsw_search_ef,
            self.hnsw_m,
        )

        # Issue #369: Wrap blocking delete_collection with asyncio.to_thread
        try:
            await asyncio.to_thread(chroma_client.delete_collection, name=target_name)
            logger.info("Deleted existing collection: %s", target_name)
        except Exception as e:
            logger.debug(
                "Collection %s does not exist or could not be deleted: %s",
                target_name,
                e,
            )

        # Issue #369: Wrap blocking create_collection with asyncio.to_thread
        return await asyncio.to_thread(
            chroma_client.create_collection, name=target_name, metadata=hnsw_metadata
        )

    async def _migrate_vectors_batch(
        self, old_collection: Any, new_collection: Any, old_count: int
    ) -> int:
        """Migrate vectors in batches from old to new collection."""
        batch_size = 1000
        migrated = 0
        offset = 0

        while offset < old_count:
            # Issue #369: Wrap blocking get() with asyncio.to_thread
            results = await asyncio.to_thread(
                old_collection.get,
                limit=batch_size,
                offset=offset,
                include=["documents", "embeddings", "metadatas"],
            )

            if not results["ids"]:
                break

            # Issue #369: Wrap blocking add() with asyncio.to_thread
            await asyncio.to_thread(
                new_collection.add,
                ids=results["ids"],
                embeddings=results["embeddings"],
                documents=results["documents"],
                metadatas=results["metadatas"],
            )

            migrated += len(results["ids"])
            offset += batch_size

            if migrated % 10000 == 0:
                logger.info("Migration progress: %d/%d vectors", migrated, old_count)

        return migrated

    def _build_success_result(
        self,
        target_name: str,
        old_count: int,
        migrated: int,
        hnsw_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build success result dictionary."""
        logger.info(
            "Migration complete: %d vectors migrated to '%s'", migrated, target_name
        )
        return {
            "status": "success",
            "old_collection": self.chromadb_collection,
            "new_collection": target_name,
            "old_count": old_count,
            "migrated_count": migrated,
            "hnsw_params": hnsw_metadata,
            "message": (
                "Successfully migrated %d vectors. "
                "To switch, update AUTOBOT_CHROMADB_COLLECTION=%s"
                % (migrated, target_name)
            ),
        }

    async def _get_old_collection_and_count(self, chroma_client: Any) -> tuple:
        """Get old collection and its vector count (Issue #398: extracted)."""
        old_collection = await asyncio.to_thread(
            chroma_client.get_collection, name=self.chromadb_collection
        )
        old_count = await asyncio.to_thread(old_collection.count)
        return old_collection, old_count

    async def _execute_index_migration(
        self, chroma_client: Any, target_name: str, old_collection: Any, old_count: int
    ) -> Dict[str, Any]:
        """Execute the full migration process (Issue #398: extracted)."""
        hnsw_metadata = self._get_hnsw_metadata()
        new_collection = await self._prepare_target_collection(chroma_client, target_name, hnsw_metadata)
        migrated = await self._migrate_vectors_batch(old_collection, new_collection, old_count)
        return self._build_success_result(target_name, old_count, migrated, hnsw_metadata)

    async def rebuild_chromadb_index(
        self, new_collection_name: Optional[str] = None
    ) -> dict:
        """Rebuild ChromaDB collection with optimized HNSW (Issue #398: refactored)."""
        if not self.initialized:
            return {"status": "error", "message": "Knowledge base not initialized"}

        try:
            from utils.chromadb_client import get_chromadb_client as create_chromadb_client

            logger.info("Starting ChromaDB index rebuild with optimized HNSW params...")
            chroma_client = create_chromadb_client(
                db_path=str(Path(self.chromadb_path)), allow_reset=False, anonymized_telemetry=False
            )

            old_collection, old_count = await self._get_old_collection_and_count(chroma_client)
            if old_count == 0:
                return {"status": "skipped", "message": "No vectors to migrate", "old_count": 0}

            target_name = new_collection_name or "%s_optimized" % self.chromadb_collection
            return await self._execute_index_migration(
                chroma_client, target_name, old_collection, old_count
            )

        except Exception as e:
            logger.error("ChromaDB index rebuild failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _build_index_info_result(
        self, chroma_path: Path, vector_count: int, metadata: Dict
    ) -> Dict[str, Any]:
        """Build index info result dictionary (Issue #398: extracted)."""
        return {
            "status": "success",
            "collection_name": self.chromadb_collection,
            "vector_count": vector_count,
            "chromadb_path": str(chroma_path),
            "hnsw_params": {
                "space": metadata.get("hnsw:space", "unknown"),
                "construction_ef": metadata.get("hnsw:construction_ef", "default"),
                "search_ef": metadata.get("hnsw:search_ef", "default"),
                "M": metadata.get("hnsw:M", "default"),
            },
            "configured_params": {
                "space": self.hnsw_space,
                "construction_ef": self.hnsw_construction_ef,
                "search_ef": self.hnsw_search_ef,
                "M": self.hnsw_m,
            },
        }

    async def get_chromadb_index_info(self) -> dict:
        """Get ChromaDB collection and HNSW info (Issue #398: refactored)."""
        if not self.initialized:
            return {"status": "error", "message": "Knowledge base not initialized"}

        try:
            from utils.chromadb_client import get_chromadb_client as create_chromadb_client

            chroma_path = Path(self.chromadb_path)
            chroma_client = create_chromadb_client(
                db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
            )

            collection = await asyncio.to_thread(
                chroma_client.get_collection, name=self.chromadb_collection
            )
            vector_count = await asyncio.to_thread(collection.count)

            return self._build_index_info_result(chroma_path, vector_count, collection.metadata or {})

        except Exception as e:
            logger.error("Failed to get ChromaDB index info: %s", e)
            return {"status": "error", "message": str(e)}

    async def rebuild_search_index(self) -> Dict[str, Any]:
        """
        Rebuild the search index to sync with actual vectors (V1 compatibility).

        For ChromaDB, this is mostly a no-op since ChromaDB manages its own indices.
        Issue #369: All ChromaDB operations wrapped with asyncio.to_thread().
        """
        try:
            if not self.vector_store:
                return {"status": "error", "message": "Vector store not available"}

            # For ChromaDB, just verify the collection is accessible
            chroma_collection = self.vector_store._collection
            # Issue #369: Wrap blocking count() with asyncio.to_thread
            vector_count = await asyncio.to_thread(chroma_collection.count)

            return {
                "status": "success",
                "message": "ChromaDB index verified successfully",
                "vectors_found": vector_count,
                "indexed_documents": vector_count,
                "sync_status": "synced",
            }

        except Exception as e:
            logger.error("Failed to rebuild search index: %s", e)
            return {"status": "error", "message": str(e)}

    def ensure_initialized(self):
        """
        Ensure the knowledge base is initialized.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")
