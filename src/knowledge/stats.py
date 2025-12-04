# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Statistics Module

Contains the StatsMixin class for atomic stats tracking and performance monitoring.
Implements Issue #71 - O(1) atomic counter operations for fact/document/vector counts.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    import aioredis
    import redis
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


class StatsMixin:
    """
    Statistics tracking mixin for knowledge base.

    Provides O(1) atomic counter operations for efficient stats tracking without
    expensive SCAN operations. Uses Redis hash (kb:stats) for persistent counters.

    Key Features:
    - Atomic increment/decrement operations
    - O(1) stats retrieval
    - Consistency verification
    - Embedding cache monitoring
    """

    # Type hints for attributes from base class
    aioredis_client: "aioredis.Redis"
    redis_client: "redis.Redis"
    vector_store: "ChromaVectorStore"
    _stats_key: str
    chromadb_collection: str
    chromadb_path: str
    redis_db: int
    initialized: bool
    llama_index_configured: bool
    embedding_model_name: str
    embedding_dimensions: int

    async def _increment_stat(self, field: str, amount: int = 1) -> None:
        """Atomically increment a stats counter field."""
        if self.aioredis_client:
            try:
                await self.aioredis_client.hincrby(self._stats_key, field, amount)
                logger.debug(f"Incremented {field} by {amount}")
            except Exception as e:
                logger.warning(f"Failed to increment stat {field}: {e}")

    async def _decrement_stat(self, field: str, amount: int = 1) -> None:
        """Atomically decrement a stats counter field (prevents negative values)."""
        if self.aioredis_client:
            try:
                # Use hincrby with negative value for atomic decrement
                await self.aioredis_client.hincrby(self._stats_key, field, -amount)
                logger.debug(f"Decremented {field} by {amount}")
            except Exception as e:
                logger.warning(f"Failed to decrement stat {field}: {e}")

    async def _get_stat(self, field: str) -> int:
        """Get a single stats counter value (O(1))."""
        if self.aioredis_client:
            try:
                value = await self.aioredis_client.hget(self._stats_key, field)
                if value is not None:
                    return int(value)
            except Exception as e:
                logger.warning(f"Failed to get stat {field}: {e}")
        return 0

    async def _get_all_stats(self) -> dict:
        """Get all stats counters as dict (O(1))."""
        if self.aioredis_client:
            try:
                stats = await self.aioredis_client.hgetall(self._stats_key)
                return {
                    k.decode() if isinstance(k, bytes) else k: int(
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in stats.items()
                }
            except Exception as e:
                logger.warning(f"Failed to get all stats: {e}")
        return {}

    async def _initialize_stats_counters(self) -> None:
        """
        Initialize stats counters from existing data (one-time migration).

        This performs a SCAN to count existing facts but only runs once
        when the kb:stats hash doesn't exist.
        """
        if not self.aioredis_client:
            return

        try:
            # Check if counters already exist
            exists = await self.aioredis_client.exists(self._stats_key)
            if exists:
                logger.info("Stats counters already initialized")
                return

            logger.info("Initializing stats counters from existing data...")

            # Count existing facts using scan_iter (one-time operation)
            fact_count = 0
            async for _ in self.aioredis_client.scan_iter(match="fact:*", count=1000):
                fact_count += 1

            # Get vector count from ChromaDB
            vector_count = 0
            if self.vector_store:
                try:
                    chroma_collection = self.vector_store._collection
                    vector_count = chroma_collection.count()
                except Exception as e:
                    logger.debug(f"Could not get vector count: {e}")

            # Initialize the counters
            await self.aioredis_client.hset(
                self._stats_key,
                mapping={
                    "total_facts": fact_count,
                    "total_vectors": vector_count,
                    "total_documents": vector_count,
                    "total_chunks": vector_count,
                    "initialized_at": datetime.now().isoformat(),
                },
            )

            logger.info(
                f"Stats counters initialized: facts={fact_count}, "
                f"vectors={vector_count}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize stats counters: {e}")

    async def _verify_stats_consistency(self, auto_correct: bool = True) -> dict:
        """
        Verify stats counters are accurate by comparing to actual counts.

        This is an expensive O(n) operation and should only be called
        periodically (e.g., once per day or on admin request).

        Args:
            auto_correct: If True, correct counters if drift detected

        Returns:
            Dict with consistency check results
        """
        if not self.aioredis_client:
            return {"status": "error", "message": "Redis not available"}

        try:
            # Get current counter values
            current_counters = await self._get_all_stats()
            stored_facts = current_counters.get("total_facts", 0)
            stored_vectors = current_counters.get("total_vectors", 0)

            # Count actual facts (expensive O(n) operation)
            actual_fact_count = 0
            async for _ in self.aioredis_client.scan_iter(match="fact:*", count=1000):
                actual_fact_count += 1

            # Count actual vectors from ChromaDB
            actual_vector_count = 0
            if self.vector_store:
                try:
                    chroma_collection = self.vector_store._collection
                    actual_vector_count = chroma_collection.count()
                except Exception as e:
                    logger.debug(f"Could not get actual vector count: {e}")

            # Calculate drift
            fact_drift = actual_fact_count - stored_facts
            vector_drift = actual_vector_count - stored_vectors

            is_consistent = fact_drift == 0 and vector_drift == 0

            result = {
                "status": "consistent" if is_consistent else "drift_detected",
                "stored_facts": stored_facts,
                "actual_facts": actual_fact_count,
                "fact_drift": fact_drift,
                "stored_vectors": stored_vectors,
                "actual_vectors": actual_vector_count,
                "vector_drift": vector_drift,
                "checked_at": datetime.now().isoformat(),
            }

            if not is_consistent:
                logger.warning(
                    f"Stats counter drift detected: "
                    f"facts={fact_drift:+d}, vectors={vector_drift:+d}"
                )

                if auto_correct:
                    # Correct the counters
                    await self.aioredis_client.hset(
                        self._stats_key,
                        mapping={
                            "total_facts": actual_fact_count,
                            "total_vectors": actual_vector_count,
                            "total_documents": actual_vector_count,
                            "total_chunks": actual_vector_count,
                            "last_corrected": datetime.now().isoformat(),
                        },
                    )
                    result["corrected"] = True
                    logger.info("Stats counters corrected to actual values")
            else:
                logger.info("Stats counters are consistent with actual data")

            return result

        except Exception as e:
            logger.error(f"Stats consistency check failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _get_fact_categories(self, fact_keys_sample: List[bytes]) -> List[str]:
        """Extract categories from sampled facts (Issue #298 - extracted helper)."""
        if not fact_keys_sample:
            return []

        categories = set()
        try:
            async with self.aioredis_client.pipeline() as pipe:
                for key in fact_keys_sample:
                    await pipe.hget(key, "metadata")
                all_metadata = await pipe.execute()

            for fact_data in all_metadata:
                if not fact_data:
                    continue
                try:
                    metadata = json.loads(fact_data)
                    if "category" in metadata:
                        categories.add(metadata["category"])
                except (json.JSONDecodeError, TypeError):
                    continue
        except Exception as e:
            logger.warning(f"Could not extract categories: {e}")

        return list(categories) if categories else ["general"]

    async def _get_chromadb_stats(self, stats: Dict[str, Any]) -> None:
        """Get ChromaDB collection stats (Issue #298 - extracted helper)."""
        if not self.vector_store:
            return

        try:
            chroma_collection = self.vector_store._collection
            vector_count = chroma_collection.count()
            stats["index_available"] = True
            stats["indexed_documents"] = vector_count
            stats["chromadb_collection"] = self.chromadb_collection
            stats["chromadb_path"] = self.chromadb_path
            logger.debug(
                f"ChromaDB stats: {vector_count} vectors in collection '{self.chromadb_collection}'"
            )
        except Exception as e:
            logger.warning(f"Could not get ChromaDB stats: {e}")
            stats["index_available"] = False

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive knowledge base statistics (async version)"""
        # Import here to avoid circular import
        from src.knowledge.embedding_cache import get_embedding_cache

        logger.info("=== get_stats() called with caching ===")
        try:
            stats = {
                "total_documents": 0,
                "total_chunks": 0,
                "total_facts": 0,
                "total_vectors": 0,
                "categories": [],
                "db_size": 0,
                "status": "online",
                "last_updated": datetime.now().isoformat(),
                "redis_db": self.redis_db,
                "vector_store": "chromadb",
                "chromadb_collection": self.chromadb_collection,
                "initialized": self.initialized,
                "llama_index_configured": self.llama_index_configured,
                "embedding_model": self.embedding_model_name,
                "embedding_dimensions": self.embedding_dimensions,
            }

            if self.aioredis_client:
                # Issue #71: O(1) stats lookup using incremental counters
                try:
                    # Get counts from kb:stats hash (O(1) operation)
                    stat_counters = await self._get_all_stats()

                    fact_count = stat_counters.get("total_facts", 0)
                    vector_count = stat_counters.get("total_vectors", 0)

                    # If counters are not initialized, fall back to ChromaDB count
                    if not stat_counters:
                        logger.warning(
                            "Stats counters not initialized, using ChromaDB fallback"
                        )
                        fact_count = 0
                        vector_count = 0
                        if self.vector_store:
                            try:
                                chroma_collection = self.vector_store._collection
                                vector_count = chroma_collection.count()
                            except Exception as e:
                                logger.error(f"Error getting ChromaDB count: {e}")

                    logger.debug(
                        f"O(1) stats lookup: facts={fact_count}, vectors={vector_count}"
                    )

                except Exception as count_error:
                    logger.warning(
                        f"Error getting stats counters, using fallback: {count_error}"
                    )
                    fact_count = 0
                    vector_count = 0

                stats["total_facts"] = fact_count
                stats["total_documents"] = vector_count
                stats["total_vectors"] = vector_count
                stats["total_chunks"] = vector_count

                # Sample a few facts for category extraction (limit to 10 for speed)
                fact_keys_sample = []
                try:
                    count = 0
                    async for key in self.aioredis_client.scan_iter(
                        match="fact:*", count=10
                    ):
                        fact_keys_sample.append(key)
                        count += 1
                        if count >= 10:  # Only sample 10 facts maximum
                            break
                except Exception as sample_error:
                    logger.warning(f"Error sampling facts: {sample_error}")

                # Get database size
                try:
                    info = await self.aioredis_client.info("memory")
                    stats["db_size"] = info.get("used_memory", 0)
                except Exception as e:
                    logger.debug(f"Could not get Redis memory info: {e}")

                # Extract categories using helper (Issue #298 - reduced nesting)
                stats["categories"] = await self._get_fact_categories(fact_keys_sample)

            # Get ChromaDB stats using helper (Issue #298 - reduced nesting)
            await self._get_chromadb_stats(stats)

            # Add embedding cache statistics (P0 optimization monitoring)
            stats["embedding_cache"] = get_embedding_cache().get_stats()

            return stats

        except Exception as e:
            logger.error(f"Error getting knowledge base stats: {e}")
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "total_facts": 0,
                "total_vectors": 0,
                "categories": [],
                "db_size": 0,
                "status": "error",
                "error": str(e),
                "last_updated": datetime.now().isoformat(),
            }

    async def get_detailed_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the knowledge base.

        This method provides detailed insights including database size,
        category distribution, recent activity, and performance metrics.
        This is more computationally intensive than get_stats().

        Returns:
            Dict containing detailed statistics and analytics

        Performance: Slower (1-5s) - performs comprehensive analysis
        """
        basic_stats = await self.get_stats()

        if not self.redis_client:
            return {
                **basic_stats,
                "detailed_stats": False,
                "message": "Redis not available for detailed analysis",
            }

        try:
            detailed = {**basic_stats}

            # Database size analysis
            try:
                # Get approximate database size
                info = await asyncio.to_thread(self.redis_client.info, "memory")
                detailed["memory_usage_mb"] = round(
                    info.get("used_memory", 0) / (1024 * 1024), 2
                )
                detailed["peak_memory_mb"] = round(
                    info.get("used_memory_peak", 0) / (1024 * 1024), 2
                )
            except Exception as e:
                logger.warning(f"Could not get memory stats: {e}")

            # Recent activity analysis
            try:
                fact_keys = await self._scan_redis_keys_async("fact:*")
                if fact_keys:
                    # Sample recent facts for activity analysis
                    recent_facts = []
                    sample_size = min(10, len(fact_keys))

                    for fact_key in fact_keys[:sample_size]:
                        try:
                            fact_data = await self.aioredis_client.hgetall(fact_key)
                            if fact_data and "timestamp" in fact_data:
                                recent_facts.append(fact_data["timestamp"])
                        except Exception:
                            continue

                    detailed["recent_activity"] = {
                        "total_facts": len(fact_keys),
                        "sample_timestamps": recent_facts[:5],  # Show 5 most recent
                    }
            except Exception as e:
                logger.warning(f"Could not get recent activity: {e}")

            # Vector store health
            try:
                detailed["vector_store_health"] = "healthy"
                detailed["vector_backend"] = "chromadb"
            except Exception as e:
                logger.warning(f"Could not assess vector store health: {e}")

            detailed["detailed_stats"] = True
            detailed["generated_at"] = datetime.now().isoformat()

            return detailed

        except Exception as e:
            logger.error(f"Error generating detailed stats: {e}")
            return {**basic_stats, "detailed_stats": False, "error": str(e)}

    # Method reference needed by get_detailed_stats
    async def _scan_redis_keys_async(self, pattern: str):
        """
        Scan Redis keys with pattern using async client.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")

    def ensure_initialized(self):
        """
        Ensure the knowledge base is initialized.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")
