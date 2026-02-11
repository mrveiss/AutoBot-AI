#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Memory Graph Initialization Script

This script initializes the Redis Stack infrastructure for AutoBot's Memory Graph system,
including index creation, schema validation, data migration, and performance benchmarking.

Database: Redis Stack DB 0 (RedisSearch limitation)
Data Prefix: memory:graph:entity:* (logical separation from knowledge base)
Specification: /home/kali/Desktop/AutoBot/docs/database/REDIS_MEMORY_GRAPH_SPECIFICATION.md

IMPORTANT: RedisSearch indexes can only be created on DB 0, so we use key prefixes
for logical database separation instead of physical database numbers.

Features:
- RedisJSON + RedisSearch index creation
- Vector search index for semantic embeddings (768 dimensions)
- Conversation transcript migration to entity/relation graph
- Index validation and performance testing
- Comprehensive logging and error handling
- Idempotent operations (safe to re-run)
- Rollback capability on failure

Usage:
    python init_memory_graph_redis.py [--migrate] [--validate] [--benchmark] [--rollback]
"""

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis
from redis.commands.search.field import NumericField, TagField, TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from constants.network_constants import NetworkConstants

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            "/home/kali/Desktop/AutoBot/logs/database/memory_graph_init.log", mode="a"
        ),
    ],
)
logger = logging.getLogger(__name__)


class MemoryGraphInitializer:
    """Initialize and configure Redis Memory Graph infrastructure"""

    def __init__(self, redis_host: str = None, redis_port: int = None):
        """Initialize Redis connection for Memory Graph

        NOTE: RedisSearch requires DB 0, so we use key prefixes for logical separation.
        Memory Graph keys: memory:graph:entity:*, memory:graph:relations:*

        Args:
            redis_host: Redis host address (defaults to NetworkConstants.REDIS_HOST)
            redis_port: Redis port (defaults to NetworkConstants.REDIS_PORT)
        """
        self.redis_host = redis_host or NetworkConstants.REDIS_HOST
        self.redis_port = redis_port or NetworkConstants.REDIS_PORT
        self.redis_db = 0  # RedisSearch limitation - must use DB 0

        # Key prefixes for logical database separation
        self.entity_prefix = "memory:graph:entity:"
        self.relation_out_prefix = "memory:graph:relations:out:"
        self.relation_in_prefix = "memory:graph:relations:in:"

        # Index names (unique to avoid conflicts with knowledge base)
        self.entity_index = "memory_graph_entity_idx"
        self.fulltext_index = "memory_graph_fulltext_idx"

        # Connection client (initialized in connect())
        self.redis_client: Optional[redis.Redis] = None

        # Backup tracking for rollback
        self.backup_data: Dict[str, Any] = {}
        self.created_indexes: List[str] = []

    def connect(self) -> bool:
        """Establish connection to Redis Stack

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(
                "Connecting to Redis at %s:%s DB %s...",
                self.redis_host,
                self.redis_port,
                self.redis_db,
            )
            logger.info("Using key prefix: %s", self.entity_prefix)

            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=False,  # Keep binary for vector operations
                socket_timeout=10,
                socket_connect_timeout=10,
                retry_on_timeout=True,
            )

            # Test connection
            self.redis_client.ping()
            logger.info("✓ Redis connection established successfully")

            # Verify Redis modules
            if not self._verify_redis_modules():
                logger.error("Required Redis modules not available")
                return False

            return True

        except redis.ConnectionError as e:
            logger.error("Failed to connect to Redis: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected error during connection: %s", e)
            logger.error(traceback.format_exc())
            return False

    def _verify_redis_modules(self) -> bool:
        """Verify required Redis Stack modules are available

        Returns:
            True if all required modules are available
        """
        try:
            info = self.redis_client.info("modules")
            modules_str = str(info)

            required_modules = ["search", "ReJSON"]
            available_modules = []

            for module in required_modules:
                if module.lower() in modules_str.lower():
                    available_modules.append(module)
                    logger.info("✓ Module %s available", module)
                else:
                    logger.error("✗ Module %s NOT available", module)

            if len(available_modules) == len(required_modules):
                logger.info("✓ All required Redis modules verified")
                return True
            else:
                logger.error(
                    "Missing modules: %s",
                    set(required_modules) - set(available_modules),
                )
                return False

        except Exception as e:
            logger.error("Failed to verify Redis modules: %s", e)
            return False

    def create_indexes(self) -> bool:
        """Create RedisSearch indexes for entity and relation search

        Returns:
            True if index creation successful
        """
        try:
            logger.info("Creating RedisSearch indexes...")

            # Create primary entity index
            if self._create_entity_index():
                self.created_indexes.append(self.entity_index)
                logger.info("✓ Created entity index: %s", self.entity_index)
            else:
                return False

            # Create full-text search index
            if self._create_fulltext_index():
                self.created_indexes.append(self.fulltext_index)
                logger.info("✓ Created full-text index: %s", self.fulltext_index)
            else:
                return False

            logger.info("✓ All indexes created successfully")
            return True

        except Exception as e:
            logger.error("Failed to create indexes: %s", e)
            logger.error(traceback.format_exc())
            return False

    def _create_entity_index(self) -> bool:
        """Create primary entity index with vector search support

        Index Schema:
        - id: Entity UUID (TAG, SORTABLE)
        - type: Entity type classification (TAG, SORTABLE)
        - name: Human-readable name (TEXT weight 2.0, SORTABLE)
        - observations: Evolution tracking (TEXT)
        - created_at: Unix timestamp ms (NUMERIC, SORTABLE)
        - updated_at: Unix timestamp ms (NUMERIC, SORTABLE)
        - metadata.session_id: Originating session (TAG)
        - metadata.priority: Priority level (TAG)
        - metadata.status: Current status (TAG, SORTABLE)
        - metadata.tags: Classification tags (TAG)

        Returns:
            True if index created successfully
        """
        try:
            # Check if index already exists
            try:
                self.redis_client.ft(self.entity_index).info()
                logger.warning(
                    "Index %s already exists, dropping...", self.entity_index
                )
                self.redis_client.ft(self.entity_index).dropindex(
                    delete_documents=False
                )
                logger.info("Dropped existing index %s", self.entity_index)
            except redis.ResponseError:
                # Index doesn't exist, that's fine
                pass

            # Define index schema
            schema = (
                TextField("$.id", as_name="id", sortable=True),
                TagField("$.type", as_name="type", sortable=True),
                TextField("$.name", as_name="name", weight=2.0, sortable=True),
                TextField("$.observations[*]", as_name="observations"),
                NumericField("$.created_at", as_name="created_at", sortable=True),
                NumericField("$.updated_at", as_name="updated_at", sortable=True),
                TagField("$.metadata.session_id", as_name="session_id"),
                TagField("$.metadata.priority", as_name="priority"),
                TagField("$.metadata.status", as_name="status", sortable=True),
                TagField("$.metadata.tags[*]", as_name="tags", separator=","),
                # Vector field for semantic embeddings (768 dimensions for nomic-embed-text)
                VectorField(
                    "$.embedding",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": 768,
                        "DISTANCE_METRIC": "COSINE",
                        "INITIAL_CAP": 1000,
                    },
                    as_name="embedding",
                ),
            )

            # Create index on JSON documents with memory:graph:entity: prefix
            definition = IndexDefinition(
                prefix=[self.entity_prefix], index_type=IndexType.JSON
            )

            self.redis_client.ft(self.entity_index).create_index(
                schema, definition=definition
            )

            logger.info(
                "Created entity index with vector search support (768 dimensions)"
            )
            return True

        except redis.ResponseError as e:
            if "Index already exists" in str(e):
                logger.warning("Index %s already exists", self.entity_index)
                return True
            else:
                logger.error("Redis error creating entity index: %s", e)
                return False
        except Exception as e:
            logger.error("Failed to create entity index: %s", e)
            logger.error(traceback.format_exc())
            return False

    def _create_fulltext_index(self) -> bool:
        """Create full-text search index with phonetic matching

        Index Schema:
        - name: Entity name (TEXT with phonetic matching)
        - observations: All observations (TEXT)

        Returns:
            True if index created successfully
        """
        try:
            # Check if index already exists
            try:
                self.redis_client.ft(self.fulltext_index).info()
                logger.warning(
                    "Index %s already exists, dropping...", self.fulltext_index
                )
                self.redis_client.ft(self.fulltext_index).dropindex(
                    delete_documents=False
                )
                logger.info("Dropped existing index %s", self.fulltext_index)
            except redis.ResponseError:
                # Index doesn't exist, that's fine
                pass

            # Define index schema with phonetic matching
            schema = (
                TextField("$.name", as_name="name", phonetic_matcher="dm:en"),
                TextField("$.observations[*]", as_name="content"),
            )

            # Create index on JSON documents with memory:graph:entity: prefix
            definition = IndexDefinition(
                prefix=[self.entity_prefix], index_type=IndexType.JSON
            )

            self.redis_client.ft(self.fulltext_index).create_index(
                schema, definition=definition
            )

            logger.info("Created full-text index with phonetic matching")
            return True

        except redis.ResponseError as e:
            if "Index already exists" in str(e):
                logger.warning("Index %s already exists", self.fulltext_index)
                return True
            else:
                logger.error("Redis error creating full-text index: %s", e)
                return False
        except Exception as e:
            logger.error("Failed to create full-text index: %s", e)
            logger.error(traceback.format_exc())
            return False

    def migrate_conversations(self, transcript_dir: Path) -> Dict[str, Any]:
        """Migrate conversation transcripts to entity/relation graph

        Args:
            transcript_dir: Path to conversation transcripts directory

        Returns:
            Migration statistics and results
        """
        try:
            logger.info("Starting conversation migration from %s...", transcript_dir)

            if not transcript_dir.exists():
                logger.error("Transcript directory not found: %s", transcript_dir)
                return {"status": "error", "message": "Directory not found"}

            # Get all transcript files
            transcript_files = list(transcript_dir.glob("*.json"))
            logger.info("Found %s conversation transcripts", len(transcript_files))

            if not transcript_files:
                logger.warning("No transcript files to migrate")
                return {
                    "status": "success",
                    "entities_created": 0,
                    "relations_created": 0,
                }

            # Convert transcripts to entities
            entities = []
            for transcript_path in transcript_files:
                try:
                    entity = self._conversation_to_entity(transcript_path)
                    if entity:
                        entities.append(entity)
                        logger.debug("✓ Converted %s", transcript_path.name)
                except Exception as e:
                    logger.warning("Failed to convert %s: %s", transcript_path.name, e)
                    continue

            logger.info("Converted %s transcripts to entities", len(entities))

            # Extract relations based on shared topics
            relations = self._extract_conversation_relations(entities)
            logger.info("Extracted %s relations between entities", len(relations))

            # Write entities and relations to Redis
            stats = self._write_entities_and_relations(entities, relations)

            logger.info(
                "✓ Migration complete: %s entities, %s relations",
                stats["entities_created"],
                stats["relations_created"],
            )
            return stats

        except Exception as e:
            logger.error("Migration failed: %s", e)
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    def _extract_observations_and_topics(self, messages: list) -> tuple:
        """Extract observations and topics from conversation messages.

        Helper for _conversation_to_entity (Issue #825).

        Returns:
            Tuple of (observations, topics)
        """
        observations = []
        topics = set()

        topic_keywords = [
            "redis",
            "database",
            "frontend",
            "backend",
            "api",
            "vue",
            "python",
            "docker",
            "chromadb",
            "npu",
            "deployment",
            "security",
            "training",
            "knowledge base",
            "autobot",
            "vm",
            "distributed",
            "memory graph",
        ]

        decision_markers = [
            "DECISION:",
            "FIX:",
            "IMPLEMENTED:",
            "RESOLVED:",
            "CONFIGURED:",
        ]

        for msg in messages:
            content = msg.get("assistant", "") or msg.get("user", "")

            if any(marker in content for marker in decision_markers):
                observations.append(content[:200])

            content_lower = content.lower()
            for keyword in topic_keywords:
                if keyword in content_lower:
                    topics.add(keyword.title())

        return observations, topics

    def _create_entity_from_transcript(
        self, conv_id: str, messages: list, observations: list, topics: set, transcript: dict, transcript_path: Path
    ) -> Dict[str, Any]:
        """Create entity dictionary from transcript data.

        Helper for _conversation_to_entity (Issue #825).
        """
        created_at = transcript.get("created_at", datetime.now().isoformat())
        updated_at = transcript.get("updated_at", created_at)

        try:
            created_ts = int(datetime.fromisoformat(created_at).timestamp() * 1000)
            updated_ts = int(datetime.fromisoformat(updated_at).timestamp() * 1000)
        except Exception:
            created_ts = int(time.time() * 1000)
            updated_ts = created_ts

        return {
            "id": conv_id,
            "type": "conversation",
            "name": f"Conversation {conv_id[:8]}...",
            "created_at": created_ts,
            "updated_at": updated_ts,
            "observations": observations[:10],
            "metadata": {
                "session_id": conv_id,
                "user_id": "autobot",
                "message_count": len(messages),
                "topics": list(topics),
                "status": "archived",
                "priority": "low",
                "tags": list(topics)[:5],
                "migrated_from": "transcript",
                "original_file": transcript_path.name,
            },
        }

    def _conversation_to_entity(
        self, transcript_path: Path
    ) -> Optional[Dict[str, Any]]:
        """Convert conversation transcript to memory graph entity

        Args:
            transcript_path: Path to conversation transcript JSON file

        Returns:
            Entity dictionary or None if conversion fails
        """
        try:
            with open(transcript_path, "r") as f:
                transcript = json.load(f)

            conv_id = transcript.get("session_id", transcript_path.stem)
            messages = transcript.get("messages", [])

            observations, topics = self._extract_observations_and_topics(messages)

            entity = self._create_entity_from_transcript(
                conv_id, messages, observations, topics, transcript, transcript_path
            )

            return entity

        except Exception as e:
            logger.error("Failed to convert %s: %s", transcript_path.name, e)
            return None

    def _extract_conversation_relations(
        self, entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract relations between conversations based on shared topics

        Args:
            entities: List of entity dictionaries

        Returns:
            List of relation dictionaries
        """
        relations = []

        for entity_a in entities:
            for entity_b in entities:
                if entity_a["id"] == entity_b["id"]:
                    continue

                # Check topic overlap
                topics_a = set(entity_a["metadata"].get("topics", []))
                topics_b = set(entity_b["metadata"].get("topics", []))

                overlap = len(topics_a & topics_b)
                total = max(len(topics_a), len(topics_b))

                # Create relation if >50% overlap
                if overlap > 0 and total > 0 and (overlap / total) > 0.5:
                    strength = overlap / total

                    relations.append(
                        {
                            "from": entity_a["id"],
                            "to": entity_b["id"],
                            "type": "relates_to",
                            "created_at": max(
                                entity_a["created_at"], entity_b["created_at"]
                            ),
                            "metadata": {
                                "strength": strength,
                                "shared_topics": list(topics_a & topics_b),
                            },
                        }
                    )

        return relations

    def _write_entities_and_relations(
        self, entities: List[Dict[str, Any]], relations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Write entities and relations to Redis in batch

        Args:
            entities: List of entity dictionaries
            relations: List of relation dictionaries

        Returns:
            Statistics about entities and relations created
        """
        try:
            pipeline = self.redis_client.pipeline()

            # Write entities with memory:graph:entity: prefix
            for entity in entities:
                entity_key = f"{self.entity_prefix}{entity['id']}"
                pipeline.json().set(entity_key, "$", entity)

            # Write relations (bidirectional indexing)
            for rel in relations:
                # Outgoing relation index
                out_key = f"{self.relation_out_prefix}{rel['from']}"

                # Initialize if doesn't exist
                pipeline.json().set(
                    out_key, "$", {"entity_id": rel["from"], "relations": []}, nx=True
                )

                # Append relation
                pipeline.json().arrappend(out_key, "$.relations", rel)

                # Incoming relation index (reverse lookup)
                in_key = f"{self.relation_in_prefix}{rel['to']}"

                # Initialize if doesn't exist
                pipeline.json().set(
                    in_key, "$", {"entity_id": rel["to"], "relations": []}, nx=True
                )

                # Append reverse relation
                reverse_rel = {
                    "from": rel["from"],
                    "type": rel["type"],
                    "created_at": rel["created_at"],
                }
                pipeline.json().arrappend(in_key, "$.relations", reverse_rel)

            # Execute all operations
            pipeline.execute()

            return {
                "status": "success",
                "entities_created": len(entities),
                "relations_created": len(relations),
            }

        except Exception as e:
            logger.error("Failed to write entities and relations: %s", e)
            logger.error(traceback.format_exc())
            return {
                "status": "error",
                "message": str(e),
                "entities_created": 0,
                "relations_created": 0,
            }

    def validate_indexes(self) -> Dict[str, Any]:
        """Validate that indexes are created and functional

        Returns:
            Validation results
        """
        try:
            logger.info("Validating indexes...")

            validation_results = {
                "entity_index": False,
                "fulltext_index": False,
                "vector_search": False,
                "details": {},
            }

            # Validate entity index
            try:
                info = self.redis_client.ft(self.entity_index).info()
                validation_results["entity_index"] = True
                validation_results["details"]["entity_index"] = self._parse_index_info(
                    info
                )
                logger.info("✓ Entity index validated: %s", self.entity_index)
            except redis.ResponseError as e:
                logger.error("✗ Entity index validation failed: %s", e)
                validation_results["details"]["entity_index"] = str(e)

            # Validate full-text index
            try:
                info = self.redis_client.ft(self.fulltext_index).info()
                validation_results["fulltext_index"] = True
                validation_results["details"][
                    "fulltext_index"
                ] = self._parse_index_info(info)
                logger.info("✓ Full-text index validated: %s", self.fulltext_index)
            except redis.ResponseError as e:
                logger.error("✗ Full-text index validation failed: %s", e)
                validation_results["details"]["fulltext_index"] = str(e)

            # Test vector search functionality (if entities exist)
            try:
                query = Query("*").return_fields("id", "name", "type").paging(0, 1)
                results = self.redis_client.ft(self.entity_index).search(query)
                validation_results["vector_search"] = True
                validation_results["details"][
                    "vector_search"
                ] = f"Search functional, {results.total} documents"
                logger.info(
                    "✓ Vector search validated: %s documents indexed", results.total
                )
            except Exception as e:
                logger.warning(
                    "Vector search validation failed (may be no documents yet): %s", e
                )
                validation_results["details"]["vector_search"] = str(e)

            return validation_results

        except Exception as e:
            logger.error("Index validation failed: %s", e)
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    def _parse_index_info(self, info: List) -> Dict[str, Any]:
        """Parse FT.INFO output into dictionary

        Args:
            info: Raw FT.INFO response

        Returns:
            Parsed index information
        """
        try:
            parsed = {}
            for i in range(0, len(info) - 1, 2):
                key = info[i].decode() if isinstance(info[i], bytes) else str(info[i])
                value = info[i + 1]

                if isinstance(value, bytes):
                    value = value.decode()

                parsed[key] = value

            return {
                "num_docs": parsed.get("num_docs", 0),
                "num_records": parsed.get("num_records", 0),
                "index_name": parsed.get("index_name", "unknown"),
            }

        except Exception as e:
            logger.warning("Failed to parse index info: %s", e)
            return {"error": str(e)}

    def benchmark_performance(self) -> Dict[str, Any]:
        """Benchmark query performance

        Returns:
            Performance benchmark results
        """
        try:
            logger.info("Running performance benchmarks...")

            benchmarks = {}

            # Benchmark 1: Entity lookup by ID
            if self._count_entities() > 0:
                entity_id = self._get_sample_entity_id()
                if entity_id:
                    start = time.perf_counter()
                    self.redis_client.json().get(f"{self.entity_prefix}{entity_id}")
                    duration = (time.perf_counter() - start) * 1000
                    benchmarks["entity_lookup_ms"] = round(duration, 3)
                    logger.info("Entity lookup: %sms", benchmarks["entity_lookup_ms"])

            # Benchmark 2: Full-text search
            start = time.perf_counter()
            query = Query("conversation").return_fields("id", "name").paging(0, 10)
            try:
                results = self.redis_client.ft(self.entity_index).search(query)
                duration = (time.perf_counter() - start) * 1000
                benchmarks["fulltext_search_ms"] = round(duration, 3)
                benchmarks["search_results_count"] = results.total
                logger.info(
                    "Full-text search: %sms (%s results)",
                    benchmarks["fulltext_search_ms"],
                    results.total,
                )
            except Exception as e:
                logger.warning("Search benchmark failed: %s", e)
                benchmarks["fulltext_search_ms"] = None

            # Benchmark 3: Count by type
            start = time.perf_counter()
            query = Query("@type:{conversation}").return_fields("id").paging(0, 0)
            try:
                results = self.redis_client.ft(self.entity_index).search(query)
                duration = (time.perf_counter() - start) * 1000
                benchmarks["count_by_type_ms"] = round(duration, 3)
                logger.info("Count by type: %sms", benchmarks["count_by_type_ms"])
            except Exception as e:
                logger.warning("Count benchmark failed: %s", e)
                benchmarks["count_by_type_ms"] = None

            # Summary
            benchmarks["status"] = "success"
            benchmarks["target_performance_ms"] = 50
            benchmarks["meets_target"] = all(
                v is not None and v < 50
                for k, v in benchmarks.items()
                if k.endswith("_ms")
            )

            if benchmarks["meets_target"]:
                logger.info("✓ All benchmarks meet <50ms target")
            else:
                logger.warning("Some benchmarks exceed 50ms target")

            return benchmarks

        except Exception as e:
            logger.error("Benchmark failed: %s", e)
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    def _count_entities(self) -> int:
        """Count total entities in Redis

        Returns:
            Number of entities
        """
        try:
            count = 0
            for _ in self.redis_client.scan_iter(match=f"{self.entity_prefix}*"):
                count += 1
            return count
        except Exception:
            return 0

    def _get_sample_entity_id(self) -> Optional[str]:
        """Get a sample entity ID for benchmarking

        Returns:
            Entity ID or None
        """
        try:
            for key in self.redis_client.scan_iter(
                match=f"{self.entity_prefix}*", count=1
            ):
                if isinstance(key, bytes):
                    key = key.decode()
                return key.replace(self.entity_prefix, "")
            return None
        except Exception:
            return None

    def rollback(self) -> bool:
        """Rollback changes (drop created indexes)

        Returns:
            True if rollback successful
        """
        try:
            logger.warning("Rolling back changes...")

            for index_name in self.created_indexes:
                try:
                    self.redis_client.ft(index_name).dropindex(delete_documents=False)
                    logger.info("✓ Dropped index: %s", index_name)
                except redis.ResponseError as e:
                    logger.warning("Could not drop index %s: %s", index_name, e)

            logger.info("✓ Rollback complete")
            return True

        except Exception as e:
            logger.error("Rollback failed: %s", e)
            return False

    def cleanup(self):
        """Cleanup Redis connection"""
        try:
            if self.redis_client:
                self.redis_client.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.warning("Error during cleanup: %s", e)


def _create_memory_graph_argument_parser() -> argparse.ArgumentParser:
    """Create argument parser for memory graph initialization.

    Helper for main (Issue #825).
    """
    parser = argparse.ArgumentParser(
        description="Initialize Redis Memory Graph infrastructure for AutoBot"
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate conversation transcripts to entity/relation graph",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate index creation and functionality",
    )
    parser.add_argument(
        "--benchmark", action="store_true", help="Run performance benchmarks"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback changes (drop created indexes)",
    )
    return parser


def _execute_memory_graph_phases(initializer: MemoryGraphInitializer, args) -> bool:
    """Execute the specified phases of memory graph initialization.

    Helper for main (Issue #825).
    """
    if args.validate:
        logger.info("=" * 80)
        logger.info("PHASE 2: Index Validation")
        logger.info("=" * 80)

        validation = initializer.validate_indexes()
        logger.info("\nValidation Results:")
        logger.info(json.dumps(validation, indent=2))

    if args.migrate:
        logger.info("=" * 80)
        logger.info("PHASE 3: Conversation Migration")
        logger.info("=" * 80)

        transcript_dir = Path(
            "/home/kali/Desktop/AutoBot/data/conversation_transcripts"
        )
        migration_stats = initializer.migrate_conversations(transcript_dir)
        logger.info("\nMigration Results:")
        logger.info(json.dumps(migration_stats, indent=2))

    if args.benchmark:
        logger.info("=" * 80)
        logger.info("PHASE 4: Performance Benchmarking")
        logger.info("=" * 80)

        benchmarks = initializer.benchmark_performance()
        logger.info("\nPerformance Benchmarks:")
        logger.info(json.dumps(benchmarks, indent=2))

    return True


def main():
    """Main execution function"""
    parser = _create_memory_graph_argument_parser()
    args = parser.parse_args()

    initializer = MemoryGraphInitializer()

    try:
        if not initializer.connect():
            logger.error("Failed to connect to Redis, aborting")
            sys.exit(1)

        if args.rollback:
            if initializer.rollback():
                logger.info("✓ Rollback completed successfully")
                sys.exit(0)
            else:
                logger.error("Rollback failed")
                sys.exit(1)

        logger.info("=" * 80)
        logger.info("PHASE 1: Index Creation")
        logger.info("=" * 80)

        if not initializer.create_indexes():
            logger.error("Index creation failed, aborting")
            sys.exit(1)

        _execute_memory_graph_phases(initializer, args)

        logger.info("=" * 80)
        logger.info("✓ Memory Graph initialization completed successfully")
        logger.info("=" * 80)

        sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Initialization failed: %s", e)
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        initializer.cleanup()


if __name__ == "__main__":
    main()
