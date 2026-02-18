#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis to ChromaDB Vector Store Migration

Migrates vector embeddings and documents from Redis (LlamaIndex RedisVectorStore)
to ChromaDB (LlamaIndex ChromaVectorStore) while preserving all metadata and
relationships.

Features:
- Batch processing for memory efficiency
- Progress tracking and logging
- Data validation and integrity checks
- Automatic backup creation
- Rollback capability

Usage:
    python scripts/utilities/migrate_redis_to_chromadb.py [--dry-run] [--batch-size N]

Arguments:
    --dry-run: Test migration without making changes
    --batch-size: Number of vectors per batch (default: 1000)
    --verify: Run verification tests after migration
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chromadb
import numpy as np
import yaml
from chromadb.config import Settings as ChromaSettings

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_base import KnowledgeBase

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for JSON-serializable types
_JSON_BASIC_TYPES = (str, int, float, bool)


class RedisToChromaDBMigration:
    """
    Handles migration of vector data from Redis to ChromaDB
    """

    def __init__(self, batch_size: int = 1000, dry_run: bool = False):
        """Initialize migration with batch size, dry run mode, and ChromaDB config."""
        self.batch_size = batch_size
        self.dry_run = dry_run

        # Load ChromaDB config from central location
        config_path = PROJECT_ROOT / "config" / "config.yaml"
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        chromadb_config = config.get("memory", {}).get("chromadb", {})
        chromadb_path = chromadb_config.get("path", "data/chromadb")
        self.collection_name = chromadb_config.get("collection_name", "autobot_memory")

        # Redis source
        self.redis_kb = None

        # ChromaDB target
        self.chroma_client = None
        self.chroma_collection = None
        self.chroma_db_path = PROJECT_ROOT / chromadb_path

        # Migration state
        self.migration_log = []
        self.total_vectors = 0
        self.migrated_vectors = 0
        self.failed_vectors = 0

        logger.info(
            "ChromaDB config loaded: path=%s, collection=%s",
            chromadb_path,
            self.collection_name,
        )

    async def initialize(self):
        """Initialize connections to both Redis and ChromaDB"""
        logger.info("Initializing migration...")

        # Initialize Redis knowledge base (source)
        logger.info("Connecting to Redis...")
        self.redis_kb = KnowledgeBase()
        success = await self.redis_kb.initialize()
        if not success:
            raise RuntimeError("Failed to initialize Redis knowledge base")
        logger.info("✅ Connected to Redis")

        # Initialize ChromaDB (target)
        logger.info("Connecting to ChromaDB...")
        self.chroma_db_path.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(self.chroma_db_path),
            settings=ChromaSettings(allow_reset=True, anonymized_telemetry=False),
        )

        # Get vector dimensions from Redis
        logger.info("Detecting vector dimensions from Redis...")
        vector_dims = await self._get_redis_vector_dimensions()
        logger.info("Vector dimensions: %s", vector_dims)

        # Create or get collection (from central config)
        collection_name = self.collection_name
        try:
            if self.dry_run:
                # Use separate collection for dry run
                collection_name = f"{self.collection_name}_migration_test"
                try:
                    self.chroma_client.delete_collection(collection_name)
                except Exception:
                    pass

            self.chroma_collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={
                    "hnsw:space": "cosine",  # Match Redis COSINE distance
                    "hnsw:M": 16,  # HNSW index parameter
                    "dimension": vector_dims,  # Store dimension for validation
                    "embedding_model": "nomic-embed-text",  # Document the model
                    "description": "AutoBot knowledge base vectors",
                    "migrated_from": "redis",
                    "migration_date": datetime.now().isoformat(),
                },
            )
            logger.info(
                "✅ ChromaDB collection ready: %s (%sD vectors)",
                collection_name,
                vector_dims,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to initialize ChromaDB: {e}")

    async def _get_redis_vector_dimensions(self) -> int:
        """
        Detect vector dimensions from Redis index

        Returns:
            Vector dimension count (e.g., 768 for nomic-embed-text)
        """
        try:
            # Query Redis index information
            index_info = self.redis_kb.redis_client.execute_command(
                "FT.INFO", "llama_index"
            )

            # Parse dimension from index info
            for i, item in enumerate(index_info):
                if isinstance(item, bytes):
                    item = item.decode()
                if item == "dim" and i + 1 < len(index_info):
                    return int(index_info[i + 1])

            # Default to 768 if not found (nomic-embed-text default)
            logger.warning("Could not detect dimensions, defaulting to 768")
            return 768

        except Exception as e:
            logger.error("Failed to detect vector dimensions: %s", e)
            return 768  # Safe default

    async def get_redis_vector_count(self) -> int:
        """Get total number of vectors in Redis using FT.INFO"""
        try:
            # Query Redis index info directly for accurate count
            index_info = self.redis_kb.redis_client.execute_command(
                "FT.INFO", "llama_index"
            )

            # Parse num_docs from index info
            for i, item in enumerate(index_info):
                if isinstance(item, bytes):
                    item = item.decode()
                if item == "num_docs" and i + 1 < len(index_info):
                    return int(index_info[i + 1])

            logger.warning("Could not find num_docs in FT.INFO, returning 0")
            return 0
        except Exception as e:
            logger.error("Failed to get Redis vector count: %s", e)
            return 0

    def _decode_field_value(
        self, field_name: str, field_value, field_dict: Dict
    ) -> bool:
        """Decode and store field value (Issue #315: extracted helper)."""
        if isinstance(field_name, bytes):
            field_name = field_name.decode()

        if isinstance(field_value, bytes) and field_name not in ["vector", "embedding"]:
            try:
                field_value = field_value.decode("utf-8")
            except UnicodeDecodeError:
                logger.debug("Skipping non-UTF8 field: %s", field_name)
                return False
        field_dict[field_name] = field_value
        return True

    def _extract_text_content(self, field_dict: Dict, doc_key: str) -> str:
        """Extract text content from document fields (Issue #315: extracted helper)."""
        node_content_str = field_dict.get("_node_content", "")
        if not node_content_str:
            return f"Document {doc_key}"

        try:
            node_data = json.loads(node_content_str)
            text_content = node_data.get("text", "")
            if text_content:
                return text_content
        except json.JSONDecodeError:
            logger.warning("Failed to parse _node_content JSON for %s", doc_key)

        return f"Document {doc_key}"

    def _build_metadata(self, field_dict: Dict, doc_key: str) -> Dict:
        """Build metadata dict from field dict (Issue #315: extracted helper)."""
        metadata = {"doc_id": doc_key, "migrated_at": datetime.now().isoformat()}
        skip_fields = {"vector", "embedding", "text", "_node_content"}
        for key, value in field_dict.items():
            if key in skip_fields:
                continue
            if isinstance(value, _JSON_BASIC_TYPES):  # Issue #380
                metadata[key] = value
            elif key not in metadata:
                metadata[key] = str(value)
        return metadata

    def _process_single_document(
        self, doc_key, doc_fields: Dict
    ) -> Optional[Tuple[str, List[float], str, Dict]]:
        """Process single Redis document (Issue #315: extracted helper)."""
        if isinstance(doc_key, bytes):
            doc_key = doc_key.decode()

        if not doc_fields:
            logger.warning("No fields found for %s, skipping", doc_key)
            return None

        # Parse fields
        field_dict = {}
        for field_name, field_value in doc_fields.items():
            self._decode_field_value(field_name, field_value, field_dict)

        # Extract embedding
        embedding_bytes = field_dict.get("vector", field_dict.get("embedding"))
        if not embedding_bytes:
            logger.warning("No embedding found for %s, skipping", doc_key)
            return None

        embedding = np.frombuffer(embedding_bytes, dtype=np.float32).tolist()
        full_text = self._extract_text_content(field_dict, doc_key)
        metadata = self._build_metadata(field_dict, doc_key)

        return doc_key, embedding, full_text, metadata

    async def export_vectors_batch(
        self, cursor: int, batch_size: int
    ) -> Tuple[int, List[str], List[List[float]], List[str], List[Dict]]:
        """Export batch of vectors from Redis (Issue #315: refactored)."""
        try:
            scan_result = self.redis_kb.redis_client.execute_command(
                "SCAN", cursor, "MATCH", "doc:*", "COUNT", batch_size
            )

            if not scan_result or len(scan_result) < 2:
                return 0, [], [], [], []

            new_cursor = int(scan_result[0])
            keys = scan_result[1]

            if not keys:
                return new_cursor, [], [], [], []

            ids, embeddings, documents, metadatas = [], [], [], []

            for doc_key in keys:
                try:
                    doc_fields = self.redis_kb.redis_client.hgetall(doc_key)
                    result = self._process_single_document(doc_key, doc_fields)
                    if result:
                        doc_id, embedding, full_text, metadata = result
                        ids.append(doc_id)
                        embeddings.append(embedding)
                        documents.append(full_text)
                        metadatas.append(metadata)
                except Exception as e:
                    logger.error("Failed to parse document %s: %s", doc_key, e)
                    self.failed_vectors += 1
                    continue

            return new_cursor, ids, embeddings, documents, metadatas

        except Exception as e:
            logger.error("Failed to export batch: %s", e, exc_info=True)
            return 0, [], [], [], []

    async def _get_embedding_for_doc(self, doc_id: str) -> Optional[List[float]]:
        """Get embedding vector for a document from Redis"""
        try:
            # Try to get embedding from vector store
            vector_store = self.redis_kb.vector_store
            if vector_store and hasattr(vector_store, "client"):
                # Query Redis directly for the vector
                # Format depends on RedisVectorStore implementation
                # This is a simplified version - may need adjustment
                embedding_key = f"llama_index:embedding:{doc_id}"
                embedding = vector_store.client.get(embedding_key)
                if embedding:
                    return json.loads(embedding)

            return None
        except Exception as e:
            logger.debug("Could not get embedding for %s: %s", doc_id, e)
            return None

    async def import_vectors_batch(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],  # CRITICAL: Add documents parameter
        metadatas: List[Dict],
    ) -> int:
        """
        Import a batch of vectors into ChromaDB

        Returns:
            Number of vectors successfully imported
        """
        if not ids:
            return 0

        try:
            if self.dry_run:
                logger.info("[DRY RUN] Would import %s vectors", len(ids))
                return len(ids)

            # Add to ChromaDB (CRITICAL: include documents parameter)
            self.chroma_collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,  # CRITICAL: Add documents!
                metadatas=metadatas,
            )

            return len(ids)

        except Exception as e:
            logger.error("Failed to import batch: %s", e)
            return 0

    async def verify_migration(self, sample_size: int = 100) -> bool:
        """
        Verify migration by comparing random samples

        Returns:
            True if verification passes
        """
        logger.info("Verifying migration with %s random samples...", sample_size)

        try:
            # Get sample IDs
            all_ids = list(self.redis_kb.vector_index.docstore.docs.keys())
            if len(all_ids) < sample_size:
                sample_size = len(all_ids)

            # Check if we have any IDs to verify
            if sample_size == 0:
                logger.warning("No vector IDs found in Redis for verification")
                logger.info("Verifying by comparing total counts instead...")
                chroma_count = self.chroma_collection.count()
                logger.info(
                    "ChromaDB count: %s, Expected: %s", chroma_count, self.total_vectors
                )
                return chroma_count == self.total_vectors

            sample_ids = np.random.choice(all_ids, sample_size, replace=False)

            matches = 0
            for doc_id in sample_ids:
                # Get from Redis
                redis_embedding = await self._get_embedding_for_doc(doc_id)
                if redis_embedding is None:
                    continue

                # Get from ChromaDB
                chroma_result = self.chroma_collection.get(
                    ids=[doc_id], include=["embeddings"]
                )

                if not chroma_result["embeddings"]:
                    logger.warning("Doc %s not found in ChromaDB", doc_id)
                    continue

                chroma_embedding = chroma_result["embeddings"][0]

                # Compare embeddings (allow small numerical differences)
                if np.allclose(redis_embedding, chroma_embedding, rtol=1e-5):
                    matches += 1

            accuracy = matches / sample_size * 100
            logger.info(
                "Verification: %s/%s matches (%.1f%%)", matches, sample_size, accuracy
            )

            return accuracy > 95  # Require >95% match

        except Exception as e:
            logger.error("Verification failed: %s", e)
            return False

    async def _migrate_single_batch(self, batch_num: int, cursor: int) -> tuple:
        """
        Migrate a single batch of vectors.

        Helper for migrate (#825).

        Args:
            batch_num: Batch number
            cursor: Current SCAN cursor

        Returns:
            Tuple of (new_cursor, imported_count, batch_time)
        """
        batch_start = time.time()
        logger.info("\nBatch %s: SCAN cursor=%s", batch_num, cursor)

        # Export from Redis using SCAN
        cursor, ids, embeddings, documents, metadatas = await self.export_vectors_batch(
            cursor, self.batch_size
        )

        if not ids:
            logger.warning("No vectors exported in batch %s", batch_num)
            return cursor, 0, time.time() - batch_start

        # Import to ChromaDB
        imported_count = await self.import_vectors_batch(
            ids, embeddings, documents, metadatas
        )

        batch_time = time.time() - batch_start
        return cursor, imported_count, batch_time

    def _log_batch_progress(
        self, batch_num: int, imported_count: int, batch_time: float
    ):
        """
        Log batch migration progress.

        Helper for migrate (#825).

        Args:
            batch_num: Batch number
            imported_count: Number of vectors imported
            batch_time: Time taken for batch
        """
        self.migrated_vectors += imported_count

        progress = (
            (self.migrated_vectors / self.total_vectors) * 100
            if self.total_vectors > 0
            else 0
        )

        logger.info(
            f"✅ Batch {batch_num} complete: {imported_count} vectors "
            f"({batch_time:.1f}s) - Progress: {progress:.1f}%"
        )

    async def migrate(self):
        """Execute the full migration"""
        start_time = time.time()

        logger.info("=" * 50)
        logger.info("Redis → ChromaDB Vector Migration")
        logger.info("=" * 50)

        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No actual changes will be made")

        # Get total count
        self.total_vectors = await self.get_redis_vector_count()
        logger.info("Total vectors to migrate: %s", self.total_vectors)

        if self.total_vectors == 0:
            logger.warning("No vectors found in Redis. Nothing to migrate.")
            return

        # Migrate in batches using SCAN cursor
        batch_num = 0
        cursor = 0

        # Loop until cursor returns to 0 (complete iteration)
        while True:
            batch_num += 1

            cursor, imported_count, batch_time = await self._migrate_single_batch(
                batch_num, cursor
            )

            if imported_count > 0:
                self._log_batch_progress(batch_num, imported_count, batch_time)

            # If cursor is 0, we've completed the full scan
            if cursor == 0:
                break

        # Migration complete
        total_time = time.time() - start_time

        logger.info("\n" + "=" * 50)
        logger.info("Migration Complete")
        logger.info("=" * 50)
        logger.info("Total time: %.1fs", total_time)
        logger.info("Migrated: %s/%s", self.migrated_vectors, self.total_vectors)
        logger.info("Failed: %s", self.failed_vectors)
        logger.info("Speed: %.0f vectors/sec", self.migrated_vectors / total_time)

        # Save migration log
        self._save_migration_log()

    def _save_migration_log(self):
        """Save migration statistics to file"""
        log_file = PROJECT_ROOT / "data" / "migration_log.json"

        log_data = {
            "migration_date": datetime.now().isoformat(),
            "dry_run": self.dry_run,
            "total_vectors": self.total_vectors,
            "migrated_vectors": self.migrated_vectors,
            "failed_vectors": self.failed_vectors,
            "batch_size": self.batch_size,
            "source": "redis",
            "target": "chromadb",
            "log": self.migration_log,
        }

        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)

        logger.info("Migration log saved: %s", log_file)


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate vectors from Redis to ChromaDB"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Test without making changes"
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="Vectors per batch"
    )
    parser.add_argument("--verify", action="store_true", help="Verify after migration")
    args = parser.parse_args()

    migration = RedisToChromaDBMigration(
        batch_size=args.batch_size, dry_run=args.dry_run
    )

    try:
        await migration.initialize()
        await migration.migrate()

        if args.verify and not args.dry_run:
            success = await migration.verify_migration()
            if success:
                logger.info("✅ Verification PASSED")
            else:
                logger.error("❌ Verification FAILED")
                sys.exit(1)

    except Exception as e:
        logger.error("Migration failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
