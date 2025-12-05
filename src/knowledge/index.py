# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Index Management Module

Contains the IndexMixin class for index rebuild operations and ChromaDB management.
Implements Issue #72 - Optimized HNSW parameters for 545K+ vectors.
"""

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

    async def rebuild_chromadb_index(
        self, new_collection_name: Optional[str] = None
    ) -> dict:
        """
        Rebuild ChromaDB collection with optimized HNSW parameters.

        Issue #72: This method creates a new collection with optimized parameters
        and migrates all vectors from the existing collection.

        Args:
            new_collection_name: Optional new collection name. If None, uses
                                 "{current_name}_optimized"

        Returns:
            Dict with migration status and statistics
        """
        if not self.initialized:
            return {"status": "error", "message": "Knowledge base not initialized"}

        try:
            from src.utils.chromadb_client import (
                get_chromadb_client as create_chromadb_client,
            )

            logger.info("Starting ChromaDB index rebuild with optimized HNSW params...")

            # Get the ChromaDB client
            chroma_path = Path(self.chromadb_path)
            chroma_client = create_chromadb_client(
                db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
            )

            # Get current collection
            old_collection = chroma_client.get_collection(name=self.chromadb_collection)
            old_count = old_collection.count()

            if old_count == 0:
                return {
                    "status": "skipped",
                    "message": "No vectors to migrate",
                    "old_count": 0,
                }

            # Create new collection name
            target_name = new_collection_name or f"{self.chromadb_collection}_optimized"

            # Optimized HNSW parameters for 545K+ vectors
            hnsw_metadata = {
                "hnsw:space": self.hnsw_space,
                "hnsw:construction_ef": self.hnsw_construction_ef,
                "hnsw:search_ef": self.hnsw_search_ef,
                "hnsw:M": self.hnsw_m,
            }

            logger.info(
                f"Creating new collection '{target_name}' with HNSW params: "
                f"construction_ef={self.hnsw_construction_ef}, "
                f"search_ef={self.hnsw_search_ef}, M={self.hnsw_m}"
            )

            # Delete target collection if it exists
            try:
                chroma_client.delete_collection(name=target_name)
                logger.info(f"Deleted existing collection: {target_name}")
            except Exception as e:
                logger.debug(
                    f"Collection {target_name} does not exist or could not be deleted: {e}"
                )

            # Create new collection with optimized parameters
            new_collection = chroma_client.create_collection(
                name=target_name,
                metadata=hnsw_metadata,
            )

            # Migrate vectors in batches
            batch_size = 1000
            migrated = 0
            offset = 0

            while offset < old_count:
                # Get batch from old collection
                results = old_collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["documents", "embeddings", "metadatas"],
                )

                if not results["ids"]:
                    break

                # Add to new collection
                new_collection.add(
                    ids=results["ids"],
                    embeddings=results["embeddings"],
                    documents=results["documents"],
                    metadatas=results["metadatas"],
                )

                migrated += len(results["ids"])
                offset += batch_size

                if migrated % 10000 == 0:
                    logger.info(f"Migration progress: {migrated}/{old_count} vectors")

            logger.info(
                f"Migration complete: {migrated} vectors migrated to '{target_name}'"
            )

            return {
                "status": "success",
                "old_collection": self.chromadb_collection,
                "new_collection": target_name,
                "old_count": old_count,
                "migrated_count": migrated,
                "hnsw_params": hnsw_metadata,
                "message": (
                    f"Successfully migrated {migrated} vectors. "
                    f"To switch, update AUTOBOT_CHROMADB_COLLECTION={target_name}"
                ),
            }

        except Exception as e:
            logger.error(f"ChromaDB index rebuild failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    async def get_chromadb_index_info(self) -> dict:
        """
        Get information about the current ChromaDB collection and HNSW parameters.

        Issue #72: Useful for verifying current index configuration.

        Returns:
            Dict with collection info and HNSW parameters
        """
        if not self.initialized:
            return {"status": "error", "message": "Knowledge base not initialized"}

        try:
            from src.utils.chromadb_client import (
                get_chromadb_client as create_chromadb_client,
            )

            chroma_path = Path(self.chromadb_path)
            chroma_client = create_chromadb_client(
                db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
            )

            collection = chroma_client.get_collection(name=self.chromadb_collection)
            metadata = collection.metadata or {}

            return {
                "status": "success",
                "collection_name": self.chromadb_collection,
                "vector_count": collection.count(),
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

        except Exception as e:
            logger.error(f"Failed to get ChromaDB index info: {e}")
            return {"status": "error", "message": str(e)}

    async def rebuild_search_index(self) -> Dict[str, Any]:
        """
        Rebuild the search index to sync with actual vectors (V1 compatibility).

        For ChromaDB, this is mostly a no-op since ChromaDB manages its own indices.
        """
        try:
            if not self.vector_store:
                return {"status": "error", "message": "Vector store not available"}

            # For ChromaDB, just verify the collection is accessible
            chroma_collection = self.vector_store._collection
            vector_count = chroma_collection.count()

            return {
                "status": "success",
                "message": "ChromaDB index verified successfully",
                "vectors_found": vector_count,
                "indexed_documents": vector_count,
                "sync_status": "synced",
            }

        except Exception as e:
            logger.error(f"Failed to rebuild search index: {e}")
            return {"status": "error", "message": str(e)}

    def ensure_initialized(self):
        """
        Ensure the knowledge base is initialized.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")
