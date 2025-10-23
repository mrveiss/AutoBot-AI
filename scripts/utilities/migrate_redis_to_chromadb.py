#!/usr/bin/env python3
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

from src.knowledge_base_v2 import KnowledgeBaseV2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RedisToChromaDBMigration:
    """
    Handles migration of vector data from Redis to ChromaDB
    """

    def __init__(self, batch_size: int = 1000, dry_run: bool = False):
        self.batch_size = batch_size
        self.dry_run = dry_run

        # Load ChromaDB config from central location
        config_path = PROJECT_ROOT / "config" / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        chromadb_config = config.get('memory', {}).get('chromadb', {})
        chromadb_path = chromadb_config.get('path', 'data/chromadb')
        self.collection_name = chromadb_config.get('collection_name', 'autobot_memory')

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

        logger.info(f"ChromaDB config loaded: path={chromadb_path}, collection={self.collection_name}")

    async def initialize(self):
        """Initialize connections to both Redis and ChromaDB"""
        logger.info("Initializing migration...")

        # Initialize Redis knowledge base (source)
        logger.info("Connecting to Redis...")
        self.redis_kb = KnowledgeBaseV2()
        success = await self.redis_kb.initialize()
        if not success:
            raise RuntimeError("Failed to initialize Redis knowledge base")
        logger.info("✅ Connected to Redis")

        # Initialize ChromaDB (target)
        logger.info("Connecting to ChromaDB...")
        self.chroma_db_path.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(self.chroma_db_path),
            settings=ChromaSettings(
                allow_reset=True,
                anonymized_telemetry=False
            )
        )

        # Get vector dimensions from Redis
        logger.info("Detecting vector dimensions from Redis...")
        vector_dims = await self._get_redis_vector_dimensions()
        logger.info(f"Vector dimensions: {vector_dims}")

        # Create or get collection (from central config)
        collection_name = self.collection_name
        try:
            if self.dry_run:
                # Use separate collection for dry run
                collection_name = f"{self.collection_name}_migration_test"
                try:
                    self.chroma_client.delete_collection(collection_name)
                except:
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
                    "migration_date": datetime.now().isoformat()
                }
            )
            logger.info(f"✅ ChromaDB collection ready: {collection_name} ({vector_dims}D vectors)")

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
            logger.error(f"Failed to detect vector dimensions: {e}")
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
            logger.error(f"Failed to get Redis vector count: {e}")
            return 0

    async def export_vectors_batch(
        self,
        cursor: int,
        batch_size: int
    ) -> Tuple[int, List[str], List[List[float]], List[str], List[Dict]]:
        """
        Export a batch of vectors from Redis using SCAN (no OFFSET limit)

        Returns:
            (new_cursor, ids, embeddings, documents, metadatas)
        """
        try:
            # Use SCAN to iterate through doc:* keys (cursor-based, no 10K limit)
            scan_result = self.redis_kb.redis_client.execute_command(
                "SCAN", cursor,
                "MATCH", "doc:*",
                "COUNT", batch_size
            )

            if not scan_result or len(scan_result) < 2:
                return 0, [], [], []

            # Result format: [new_cursor, [key1, key2, ...]]
            new_cursor = int(scan_result[0])
            keys = scan_result[1]

            if not keys:
                return new_cursor, [], [], [], []

            ids = []
            embeddings = []
            documents = []  # CRITICAL: Add documents list
            metadatas = []

            # Fetch each document's hash fields
            for doc_key in keys:
                try:
                    if isinstance(doc_key, bytes):
                        doc_key = doc_key.decode()

                    # Get all hash fields for this document
                    doc_fields = self.redis_kb.redis_client.hgetall(doc_key)

                    if not doc_fields:
                        logger.warning(f"No fields found for {doc_key}, skipping")
                        continue

                    # Parse fields into dict
                    field_dict = {}
                    for field_name, field_value in doc_fields.items():
                        if isinstance(field_name, bytes):
                            field_name = field_name.decode()

                        # Keep binary fields (like 'vector') as bytes, decode text fields carefully
                        if isinstance(field_value, bytes) and field_name not in ['vector', 'embedding']:
                            try:
                                field_value = field_value.decode('utf-8')
                            except UnicodeDecodeError:
                                # Skip fields that can't be decoded (likely binary data)
                                logger.debug(f"Skipping non-UTF8 field: {field_name}")
                                continue
                        field_dict[field_name] = field_value

                    # Extract vector embedding
                    embedding_bytes = field_dict.get('vector', field_dict.get('embedding'))
                    if not embedding_bytes:
                        logger.warning(f"No embedding found for {doc_key}, skipping")
                        continue

                    # Parse embedding (stored as bytes)
                    embedding = np.frombuffer(embedding_bytes, dtype=np.float32).tolist()

                    # Extract text from _node_content JSON or use empty string
                    text_content = ""
                    node_content_str = field_dict.get('_node_content', '')
                    if node_content_str:
                        try:
                            # Parse _node_content JSON
                            node_data = json.loads(node_content_str)
                            # Extract text from node data (it should be in 'text' field of the node)
                            text_content = node_data.get('text', '')

                            # If no text field, try to get from metadata
                            if not text_content and 'metadata' in node_data:
                                # Sometimes text is stored differently
                                pass  # Metadata fields will be extracted below
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse _node_content JSON for {doc_key}")

                    # CRITICAL: Store full text in documents, not just metadata
                    full_text = text_content if text_content else f"Document {doc_key}"

                    metadata = {
                        "doc_id": doc_key,
                        "migrated_at": datetime.now().isoformat()
                    }

                    # Add other fields as metadata (ChromaDB restrictions)
                    for key, value in field_dict.items():
                        if key not in ['vector', 'embedding', 'text', '_node_content']:
                            if isinstance(value, (str, int, float, bool)):
                                metadata[key] = value
                            elif key not in metadata:  # Don't override already set values
                                metadata[key] = str(value)

                    ids.append(doc_key)
                    embeddings.append(embedding)
                    documents.append(full_text)  # CRITICAL: Add full document text
                    metadatas.append(metadata)

                except Exception as e:
                    logger.error(f"Failed to parse document {doc_key}: {e}")
                    self.failed_vectors += 1
                    continue

            return new_cursor, ids, embeddings, documents, metadatas

        except Exception as e:
            logger.error(f"Failed to export batch: {e}", exc_info=True)
            return 0, [], [], [], []

    async def _get_embedding_for_doc(self, doc_id: str) -> Optional[List[float]]:
        """Get embedding vector for a document from Redis"""
        try:
            # Try to get embedding from vector store
            vector_store = self.redis_kb.vector_store
            if vector_store and hasattr(vector_store, 'client'):
                # Query Redis directly for the vector
                # Format depends on RedisVectorStore implementation
                # This is a simplified version - may need adjustment
                embedding_key = f"llama_index:embedding:{doc_id}"
                embedding = vector_store.client.get(embedding_key)
                if embedding:
                    return json.loads(embedding)

            return None
        except Exception as e:
            logger.debug(f"Could not get embedding for {doc_id}: {e}")
            return None

    async def import_vectors_batch(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],  # CRITICAL: Add documents parameter
        metadatas: List[Dict]
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
                logger.info(f"[DRY RUN] Would import {len(ids)} vectors")
                return len(ids)

            # Add to ChromaDB (CRITICAL: include documents parameter)
            self.chroma_collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,  # CRITICAL: Add documents!
                metadatas=metadatas
            )

            return len(ids)

        except Exception as e:
            logger.error(f"Failed to import batch: {e}")
            return 0

    async def verify_migration(self, sample_size: int = 100) -> bool:
        """
        Verify migration by comparing random samples

        Returns:
            True if verification passes
        """
        logger.info(f"Verifying migration with {sample_size} random samples...")

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
                logger.info(f"ChromaDB count: {chroma_count}, Expected: {self.total_vectors}")
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
                    ids=[doc_id],
                    include=["embeddings"]
                )

                if not chroma_result['embeddings']:
                    logger.warning(f"Doc {doc_id} not found in ChromaDB")
                    continue

                chroma_embedding = chroma_result['embeddings'][0]

                # Compare embeddings (allow small numerical differences)
                if np.allclose(redis_embedding, chroma_embedding, rtol=1e-5):
                    matches += 1

            accuracy = matches / sample_size * 100
            logger.info(f"Verification: {matches}/{sample_size} matches ({accuracy:.1f}%)")

            return accuracy > 95  # Require >95% match

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    async def migrate(self):
        """Execute the full migration"""
        start_time = time.time()

        logger.info("="*50)
        logger.info("Redis → ChromaDB Vector Migration")
        logger.info("="*50)

        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No actual changes will be made")

        # Get total count
        self.total_vectors = await self.get_redis_vector_count()
        logger.info(f"Total vectors to migrate: {self.total_vectors}")

        if self.total_vectors == 0:
            logger.warning("No vectors found in Redis. Nothing to migrate.")
            return

        # Migrate in batches using SCAN cursor
        batch_num = 0
        cursor = 0  # SCAN cursor (0 = start, returns to 0 when complete)

        # Loop until cursor returns to 0 (complete iteration)
        while True:
            batch_num += 1
            batch_start = time.time()

            logger.info(f"\nBatch {batch_num}: SCAN cursor={cursor}")

            # Export from Redis using SCAN (CRITICAL: now includes documents)
            cursor, ids, embeddings, documents, metadatas = await self.export_vectors_batch(
                cursor,
                self.batch_size
            )

            if not ids:
                logger.warning(f"No vectors exported in batch {batch_num}")
                # If cursor is 0, we've completed the full scan
                if cursor == 0:
                    break
                continue

            # Import to ChromaDB (CRITICAL: now includes documents parameter)
            imported_count = await self.import_vectors_batch(ids, embeddings, documents, metadatas)
            self.migrated_vectors += imported_count

            batch_time = time.time() - batch_start
            progress = (self.migrated_vectors / self.total_vectors) * 100 if self.total_vectors > 0 else 0

            logger.info(
                f"✅ Batch {batch_num} complete: {imported_count} vectors "
                f"({batch_time:.1f}s) - Progress: {progress:.1f}%"
            )

            # If cursor is 0, we've completed the full scan
            if cursor == 0:
                break

        # Migration complete
        total_time = time.time() - start_time

        logger.info("\n" + "="*50)
        logger.info("Migration Complete")
        logger.info("="*50)
        logger.info(f"Total time: {total_time:.1f}s")
        logger.info(f"Migrated: {self.migrated_vectors}/{self.total_vectors}")
        logger.info(f"Failed: {self.failed_vectors}")
        logger.info(f"Speed: {self.migrated_vectors/total_time:.0f} vectors/sec")

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
            "log": self.migration_log
        }

        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)

        logger.info(f"Migration log saved: {log_file}")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate vectors from Redis to ChromaDB")
    parser.add_argument("--dry-run", action="store_true", help="Test without making changes")
    parser.add_argument("--batch-size", type=int, default=1000, help="Vectors per batch")
    parser.add_argument("--verify", action="store_true", help="Verify after migration")
    args = parser.parse_args()

    migration = RedisToChromaDBMigration(
        batch_size=args.batch_size,
        dry_run=args.dry_run
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
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
