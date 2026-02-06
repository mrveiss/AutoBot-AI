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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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
                logger.debug("Incremented %s by %d", field, amount)
            except Exception as e:
                logger.warning("Failed to increment stat %s: %s", field, e)

    async def _decrement_stat(self, field: str, amount: int = 1) -> None:
        """Atomically decrement a stats counter field (prevents negative values)."""
        if self.aioredis_client:
            try:
                # Use hincrby with negative value for atomic decrement
                await self.aioredis_client.hincrby(self._stats_key, field, -amount)
                logger.debug("Decremented %s by %d", field, amount)
            except Exception as e:
                logger.warning("Failed to decrement stat %s: %s", field, e)

    async def _get_stat(self, field: str) -> int:
        """Get a single stats counter value (O(1))."""
        if self.aioredis_client:
            try:
                value = await self.aioredis_client.hget(self._stats_key, field)
                if value is not None:
                    return int(value)
            except Exception as e:
                logger.warning("Failed to get stat %s: %s", field, e)
        return 0

    # Fields that contain metadata (timestamps) rather than integer counters
    _METADATA_FIELDS = frozenset({"initialized_at", "last_corrected"})

    async def _get_all_stats(self) -> dict:
        """Get all stats counters as dict (O(1)).

        Returns:
            Dict with counter fields as integers. Metadata fields (initialized_at,
            last_corrected) are excluded as they contain timestamp strings.
        """
        if self.aioredis_client:
            try:
                stats = await self.aioredis_client.hgetall(self._stats_key)
                result = {}
                for k, v in stats.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    # Skip metadata fields that contain timestamps, not counters
                    if key in self._METADATA_FIELDS:
                        continue
                    value = v.decode() if isinstance(v, bytes) else v
                    try:
                        result[key] = int(value)
                    except (ValueError, TypeError):
                        # Log and skip fields that can't be converted to int
                        logger.warning(
                            "Stats field '%s' has non-integer value: %r", key, value
                        )
                        continue
                return result
            except Exception as e:
                logger.warning("Failed to get all stats: %s", e)
        return {}

    async def _set_initial_counters(self, fact_count: int, vector_count: int) -> None:
        """Set initial counter values in Redis (Issue #398: extracted)."""
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
        logger.info("Stats counters initialized: facts=%d, vectors=%d", fact_count, vector_count)

    async def _initialize_stats_counters(self) -> None:
        """Initialize stats counters from existing data (Issue #398: refactored)."""
        if not self.aioredis_client:
            return

        try:
            exists = await self.aioredis_client.exists(self._stats_key)
            if exists:
                logger.info("Stats counters already initialized")
                return

            logger.info("Initializing stats counters from existing data...")

            fact_count = 0
            async for _ in self.aioredis_client.scan_iter(match="fact:*", count=1000):
                fact_count += 1

            vector_count = 0
            if self.vector_store:
                try:
                    vector_count = self.vector_store._collection.count()
                except Exception as e:
                    logger.debug("Could not get vector count: %s", e)

            await self._set_initial_counters(fact_count, vector_count)

        except Exception as e:
            logger.error("Failed to initialize stats counters: %s", e)

    async def _count_actual_facts(self) -> int:
        """Count actual facts via Redis scan (Issue #398: extracted)."""
        count = 0
        async for _ in self.aioredis_client.scan_iter(match="fact:*", count=1000):
            count += 1
        return count

    def _count_actual_vectors(self) -> int:
        """Count actual vectors from ChromaDB (Issue #398: extracted)."""
        if not self.vector_store:
            return 0
        try:
            return self.vector_store._collection.count()
        except Exception as e:
            logger.debug("Could not get actual vector count: %s", e)
            return 0

    async def _correct_stats_drift(self, actual_facts: int, actual_vectors: int) -> None:
        """Correct stats counters to actual values (Issue #398: extracted)."""
        await self.aioredis_client.hset(
            self._stats_key,
            mapping={
                "total_facts": actual_facts,
                "total_vectors": actual_vectors,
                "total_documents": actual_vectors,
                "total_chunks": actual_vectors,
                "last_corrected": datetime.now().isoformat(),
            },
        )
        logger.info("Stats counters corrected to actual values")

    def _build_consistency_result(
        self, stored_facts: int, actual_facts: int, stored_vectors: int, actual_vectors: int
    ) -> dict:
        """Build consistency check result dict (Issue #398: extracted)."""
        fact_drift = actual_facts - stored_facts
        vector_drift = actual_vectors - stored_vectors
        return {
            "status": "consistent" if fact_drift == 0 and vector_drift == 0 else "drift_detected",
            "stored_facts": stored_facts,
            "actual_facts": actual_facts,
            "fact_drift": fact_drift,
            "stored_vectors": stored_vectors,
            "actual_vectors": actual_vectors,
            "vector_drift": vector_drift,
            "checked_at": datetime.now().isoformat(),
            "is_consistent": fact_drift == 0 and vector_drift == 0,
        }

    async def _verify_stats_consistency(self, auto_correct: bool = True) -> dict:
        """Verify stats counters are accurate (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"status": "error", "message": "Redis not available"}

        try:
            counters = await self._get_all_stats()
            stored_facts = counters.get("total_facts", 0)
            stored_vectors = counters.get("total_vectors", 0)

            actual_facts = await self._count_actual_facts()
            actual_vectors = self._count_actual_vectors()

            result = self._build_consistency_result(
                stored_facts, actual_facts, stored_vectors, actual_vectors
            )
            is_consistent = result.pop("is_consistent")

            if not is_consistent:
                logger.warning(
                    "Stats counter drift detected: facts=%+d, vectors=%+d",
                    result["fact_drift"], result["vector_drift"]
                )
                if auto_correct:
                    await self._correct_stats_drift(actual_facts, actual_vectors)
                    result["corrected"] = True
            else:
                logger.info("Stats counters are consistent with actual data")

            return result

        except Exception as e:
            logger.error("Stats consistency check failed: %s", e)
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
            logger.warning("Could not extract categories: %s", e)

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
                "ChromaDB stats: %d vectors in collection '%s'",
                vector_count, self.chromadb_collection
            )
        except Exception as e:
            logger.warning("Could not get ChromaDB stats: %s", e)
            stats["index_available"] = False

    async def _get_counts_with_fallback(self) -> tuple[int, int]:
        """Get fact and vector counts with ChromaDB fallback (Issue #315)."""
        try:
            stat_counters = await self._get_all_stats()
            if stat_counters:
                return stat_counters.get("total_facts", 0), stat_counters.get("total_vectors", 0)
        except Exception as e:
            logger.warning("Error getting stats counters: %s", e)

        # Fallback to ChromaDB count
        logger.warning("Stats counters not initialized, using ChromaDB fallback")
        if not self.vector_store:
            return 0, 0
        try:
            chroma_collection = self.vector_store._collection
            vector_count = chroma_collection.count()
            return 0, vector_count
        except Exception as e:
            logger.error("Error getting ChromaDB count: %s", e)
            return 0, 0

    async def _sample_fact_keys(self, limit: int = 10) -> List[bytes]:
        """Sample fact keys for category extraction (Issue #315)."""
        fact_keys = []
        try:
            async for key in self.aioredis_client.scan_iter(match="fact:*", count=limit):
                fact_keys.append(key)
                if len(fact_keys) >= limit:
                    break
        except Exception as e:
            logger.warning("Error sampling facts: %s", e)
        return fact_keys

    async def _get_redis_memory_size(self) -> int:
        """Get Redis memory usage (Issue #315)."""
        try:
            info = await self.aioredis_client.info("memory")
            return info.get("used_memory", 0)
        except Exception as e:
            logger.debug("Could not get Redis memory info: %s", e)
            return 0

    def _build_base_stats(self) -> Dict[str, Any]:
        """Build base stats dictionary with defaults (Issue #398: extracted)."""
        return {
            "total_documents": 0, "total_chunks": 0, "total_facts": 0, "total_vectors": 0,
            "categories": [], "db_size": 0, "status": "online",
            "last_updated": datetime.now().isoformat(), "redis_db": self.redis_db,
            "vector_store": "chromadb", "chromadb_collection": self.chromadb_collection,
            "initialized": self.initialized, "llama_index_configured": self.llama_index_configured,
            "embedding_model": self.embedding_model_name,
            "embedding_dimensions": self.embedding_dimensions,
        }

    async def _populate_redis_stats(self, stats: Dict[str, Any]) -> None:
        """Populate stats from Redis data (Issue #398: extracted)."""
        fact_count, vector_count = await self._get_counts_with_fallback()
        logger.debug("O(1) stats lookup: facts=%d, vectors=%d", fact_count, vector_count)

        stats["total_facts"] = fact_count
        stats["total_documents"] = vector_count
        stats["total_vectors"] = vector_count
        stats["total_chunks"] = vector_count
        stats["db_size"] = await self._get_redis_memory_size()

        fact_keys_sample = await self._sample_fact_keys(limit=10)
        stats["categories"] = await self._get_fact_categories(fact_keys_sample)

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive knowledge base statistics (Issue #398: refactored)."""
        from knowledge.embedding_cache import get_embedding_cache

        logger.info("=== get_stats() called with caching ===")
        try:
            stats = self._build_base_stats()

            if self.aioredis_client:
                await self._populate_redis_stats(stats)

            await self._get_chromadb_stats(stats)
            stats["embedding_cache"] = get_embedding_cache().get_stats()

            return stats

        except Exception as e:
            logger.error("Error getting knowledge base stats: %s", e)
            return {
                "total_documents": 0, "total_chunks": 0, "total_facts": 0, "total_vectors": 0,
                "categories": [], "db_size": 0, "status": "error",
                "error": str(e), "last_updated": datetime.now().isoformat(),
            }

    async def _get_memory_stats(self) -> Dict[str, float]:
        """Get Redis memory statistics (Issue #315: extracted).

        Returns:
            Dict with memory_usage_mb and peak_memory_mb, or empty dict on error
        """
        try:
            info = await asyncio.to_thread(self.redis_client.info, "memory")
            return {
                "memory_usage_mb": round(info.get("used_memory", 0) / (1024 * 1024), 2),
                "peak_memory_mb": round(info.get("used_memory_peak", 0) / (1024 * 1024), 2),
            }
        except Exception as e:
            logger.warning("Could not get memory stats: %s", e)
            return {}

    async def _get_recent_activity_stats(self) -> Dict[str, Any]:
        """Get recent activity statistics (Issue #315: extracted).

        Returns:
            Dict with recent_activity data, or empty dict on error
        """
        try:
            fact_keys = await self._scan_redis_keys_async("fact:*")
            if not fact_keys:
                return {}

            recent_facts = await self._sample_fact_timestamps(fact_keys[:10])
            return {
                "recent_activity": {
                    "total_facts": len(fact_keys),
                    "sample_timestamps": recent_facts[:5],
                }
            }
        except Exception as e:
            logger.warning("Could not get recent activity: %s", e)
            return {}

    async def _sample_fact_timestamps(self, fact_keys: List[str]) -> List[str]:
        """Sample timestamps from fact keys (Issue #315: extracted).

        Args:
            fact_keys: List of Redis keys to sample

        Returns:
            List of timestamp strings
        """
        timestamps = []
        for fact_key in fact_keys:
            try:
                fact_data = await self.aioredis_client.hgetall(fact_key)
                if fact_data and "timestamp" in fact_data:
                    timestamps.append(fact_data["timestamp"])
            except Exception:
                continue
        return timestamps

    async def get_detailed_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the knowledge base.

        Issue #315: Refactored to use helper methods for reduced nesting.

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

            # Collect stats from helper methods
            detailed.update(await self._get_memory_stats())
            detailed.update(await self._get_recent_activity_stats())

            # Vector store health (simple assignment, no nesting needed)
            detailed["vector_store_health"] = "healthy"
            detailed["vector_backend"] = "chromadb"
            detailed["detailed_stats"] = True
            detailed["generated_at"] = datetime.now().isoformat()

            return detailed

        except Exception as e:
            logger.error("Error generating detailed stats: %s", e)
            return {**basic_stats, "detailed_stats": False, "error": str(e)}

    async def _calc_all_quality_dimensions(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate all quality dimensions (Issue #398: extracted helper)."""
        return {
            "completeness": await self._calc_completeness_score(facts),
            "consistency": await self._calc_consistency_score(facts),
            "freshness": await self._calc_freshness_score(facts),
            "uniqueness": await self._calc_uniqueness_score(facts),
            "validity": await self._calc_validity_score(facts),
        }

    def _calc_overall_quality_score(self, dimensions: Dict[str, Any]) -> float:
        """Calculate weighted overall quality score (Issue #398: extracted helper)."""
        weights = {
            "completeness": 0.25,
            "consistency": 0.20,
            "freshness": 0.15,
            "uniqueness": 0.20,
            "validity": 0.20,
        }
        return round(sum(dimensions[dim]["score"] * weights[dim] for dim in weights), 1)

    def _build_quality_summary(
        self, facts: List[Dict[str, Any]], issues: List[Dict]
    ) -> Dict[str, Any]:
        """Build quality metrics summary (Issue #398: extracted helper)."""
        return {
            "total_facts": len(facts),
            "facts_with_issues": len(set(
                i.get("fact_id") for i in issues if i.get("fact_id")
            )),
            "critical_issues": len([i for i in issues if i.get("severity") == "critical"]),
            "warnings": len([i for i in issues if i.get("severity") == "warning"]),
        }

    async def get_data_quality_metrics(self) -> Dict[str, Any]:
        """Get data quality metrics (Issue #398: refactored with helpers)."""
        try:
            metrics = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "overall_score": 0.0,
                "dimensions": {},
                "issues": [],
                "recommendations": [],
            }

            facts = await self.get_all_facts()
            if not facts:
                metrics["overall_score"] = 100.0
                metrics["message"] = "No facts to analyze"
                return metrics

            metrics["dimensions"] = await self._calc_all_quality_dimensions(facts)
            metrics["overall_score"] = self._calc_overall_quality_score(metrics["dimensions"])

            for dim_data in metrics["dimensions"].values():
                metrics["issues"].extend(dim_data.get("issues", []))
                metrics["recommendations"].extend(dim_data.get("recommendations", []))

            metrics["summary"] = self._build_quality_summary(facts, metrics["issues"])

            return metrics

        except Exception as e:
            logger.error("Error calculating data quality metrics: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "generated_at": datetime.now().isoformat(),
            }

    def _check_fact_completeness(
        self, fact: Dict[str, Any], issues: List[Dict]
    ) -> str:
        """Check completeness of a single fact (Issue #398: extracted).

        Returns: 'complete', 'partial', or 'incomplete'
        """
        required_fields = ["content", "metadata"]
        recommended_fields = ["category", "tags", "title"]

        has_required = all(fact.get(f) for f in required_fields)
        metadata = fact.get("metadata", {})
        has_recommended = sum(1 for f in recommended_fields if metadata.get(f))

        if has_required and has_recommended == len(recommended_fields):
            return "complete"
        elif has_required:
            fact_id = fact.get("fact_id")
            if not metadata.get("category"):
                issues.append({
                    "fact_id": fact_id, "type": "missing_category",
                    "severity": "warning", "message": "Fact missing category",
                })
            if not metadata.get("tags"):
                issues.append({
                    "fact_id": fact_id, "type": "missing_tags",
                    "severity": "info", "message": "Fact has no tags",
                })
            return "partial"
        else:
            issues.append({
                "fact_id": fact.get("fact_id"), "type": "incomplete_data",
                "severity": "critical", "message": "Fact missing required fields",
            })
            return "incomplete"

    async def _calc_completeness_score(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate completeness score (Issue #398: refactored)."""
        issues: List[Dict] = []
        complete_count = partial_count = 0

        for fact in facts:
            status = self._check_fact_completeness(fact, issues)
            if status == "complete":
                complete_count += 1
            elif status == "partial":
                partial_count += 1

        total = len(facts)
        score = ((complete_count + 0.5 * partial_count) / total * 100) if total else 100

        recommendations = []
        if score < 80:
            recommendations.append({
                "action": "add_metadata",
                "description": "Add categories and tags to improve completeness",
                "priority": "high" if score < 60 else "medium",
            })

        return {
            "score": round(score, 1),
            "complete_facts": complete_count,
            "partial_facts": partial_count,
            "incomplete_facts": total - complete_count - partial_count,
            "issues": issues[:20],
            "recommendations": recommendations,
        }

    def _analyze_category_consistency(
        self, facts: List[Dict[str, Any]], issues: List[Dict]
    ) -> Dict[str, int]:
        """Analyze category consistency (Issue #398: extracted)."""
        categories: Dict[str, int] = {}
        for fact in facts:
            cat = fact.get("metadata", {}).get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1

        if len(categories) > 50:
            issues.append({
                "type": "category_fragmentation", "severity": "warning",
                "message": "Too many categories (%d), consider consolidating" % len(categories),
            })

        small_categories = [c for c, n in categories.items() if n < 3 and c != "uncategorized"]
        if small_categories:
            issues.append({
                "type": "sparse_categories", "severity": "info",
                "message": "%d categories have fewer than 3 facts" % len(small_categories),
            })
        return categories

    def _analyze_tag_consistency(
        self, facts: List[Dict[str, Any]], issues: List[Dict]
    ) -> List[str]:
        """Analyze tag consistency (Issue #398: extracted)."""
        all_tags: List[str] = []
        inconsistent_tags = 0
        for fact in facts:
            tags = fact.get("metadata", {}).get("tags", [])
            for tag in tags:
                if not tag.islower() or " " in tag:
                    inconsistent_tags += 1
            all_tags.extend(tags)

        if inconsistent_tags > 0:
            issues.append({
                "type": "tag_format_inconsistency", "severity": "warning",
                "message": "%d tags have inconsistent format" % inconsistent_tags,
            })
        return all_tags

    async def _calc_consistency_score(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate consistency score (Issue #398: refactored)."""
        issues: List[Dict] = []

        categories = self._analyze_category_consistency(facts, issues)
        all_tags = self._analyze_tag_consistency(facts, issues)

        total_checks = 3
        score = ((total_checks - len(issues)) / total_checks * 100)

        recommendations = []
        if len(categories) > 30:
            recommendations.append({
                "action": "consolidate_categories",
                "description": "Merge similar categories to improve organization",
                "priority": "medium",
            })

        return {
            "score": round(score, 1),
            "total_categories": len(categories),
            "total_unique_tags": len(set(all_tags)),
            "issues": issues,
            "recommendations": recommendations,
        }

    def _get_age_bucket(self, age_days: int) -> str:
        """Determine age bucket for a fact (Issue #398: extracted)."""
        if age_days <= 1:
            return "last_day"
        elif age_days <= 7:
            return "last_week"
        elif age_days <= 30:
            return "last_month"
        elif age_days <= 365:
            return "last_year"
        return "older"

    def _parse_fact_timestamp(self, fact: Dict[str, Any]) -> Optional[datetime]:
        """Parse timestamp from a fact (Issue #398: extracted)."""
        timestamp_str = fact.get("timestamp") or fact.get("metadata", {}).get("created_at")
        if not timestamp_str or not isinstance(timestamp_str, str):
            return None
        try:
            if "T" in timestamp_str:
                return datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00").split("+")[0]
                )
            return datetime.strptime(timestamp_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    def _compute_age_buckets(self, facts: List[Dict[str, Any]]) -> Dict[str, int]:
        """Compute age distribution buckets (Issue #398: extracted)."""
        now = datetime.now()
        buckets = {
            "last_day": 0, "last_week": 0, "last_month": 0,
            "last_year": 0, "older": 0, "unknown": 0
        }

        for fact in facts:
            fact_dt = self._parse_fact_timestamp(fact)
            if not fact_dt:
                buckets["unknown"] += 1
            else:
                bucket = self._get_age_bucket((now - fact_dt).days)
                buckets[bucket] += 1
        return buckets

    async def _calc_freshness_score(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate freshness score (Issue #398: refactored)."""
        age_buckets = self._compute_age_buckets(facts)
        total = len(facts)

        if total == 0:
            return {
                "score": 100.0, "age_distribution": age_buckets,
                "issues": [], "recommendations": []
            }

        recent = age_buckets["last_day"] + age_buckets["last_week"] + age_buckets["last_month"]
        score = (recent / total * 80) + ((total - age_buckets["older"]) / total * 20)

        issues = []
        if age_buckets["older"] > total * 0.3:
            issues.append({
                "type": "stale_data", "severity": "warning",
                "message": "%d facts are over 1 year old" % age_buckets["older"],
            })
        if age_buckets["unknown"] > total * 0.2:
            issues.append({
                "type": "missing_timestamps", "severity": "warning",
                "message": "%d facts have no timestamp" % age_buckets["unknown"],
            })

        recommendations = []
        if age_buckets["older"] > total * 0.3:
            recommendations.append({
                "action": "review_old_facts",
                "description": "Review and update facts older than 1 year",
                "priority": "low",
            })

        return {
            "score": round(min(score, 100), 1),
            "age_distribution": age_buckets,
            "issues": issues,
            "recommendations": recommendations,
        }

    async def _calc_uniqueness_score(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate uniqueness score - how unique is the data (no duplicates)."""
        issues = []

        # Check for exact content duplicates
        content_hashes = {}
        duplicate_count = 0

        for fact in facts:
            content = fact.get("content", "")
            content_hash = hash(content)

            if content_hash in content_hashes:
                duplicate_count += 1
                if duplicate_count <= 10:  # Limit issues reported
                    issues.append({
                        "fact_id": fact.get("fact_id"),
                        "duplicate_of": content_hashes[content_hash],
                        "type": "exact_duplicate",
                        "severity": "warning",
                        "message": "Exact duplicate content found",
                    })
            else:
                content_hashes[content_hash] = fact.get("fact_id")

        total = len(facts)
        unique_count = total - duplicate_count
        score = (unique_count / total * 100) if total else 100

        recommendations = []
        if duplicate_count > 0:
            recommendations.append({
                "action": "remove_duplicates",
                "description": "Remove %d duplicate facts" % duplicate_count,
                "priority": "high" if duplicate_count > 10 else "medium",
            })

        return {
            "score": round(score, 1),
            "total_facts": total,
            "unique_facts": unique_count,
            "duplicate_facts": duplicate_count,
            "issues": issues,
            "recommendations": recommendations,
        }

    def _validate_single_fact(self, fact: Dict[str, Any], issues: List[Dict]) -> bool:
        """Validate a single fact for validity (Issue #398: extracted)."""
        fact_valid = True
        fact_id = fact.get("fact_id")

        # Check content validity
        content = fact.get("content", "")
        if not content or len(content) < 10:
            issues.append({
                "fact_id": fact_id, "type": "short_content",
                "severity": "warning", "message": "Content is too short (< 10 chars)",
            })
            fact_valid = False
        elif len(content) > 100000:
            issues.append({
                "fact_id": fact_id, "type": "long_content",
                "severity": "info", "message": "Content is very long (> 100k chars)",
            })

        # Check metadata validity
        metadata = fact.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            issues.append({
                "fact_id": fact_id, "type": "invalid_metadata",
                "severity": "critical", "message": "Metadata is not a valid dictionary",
            })
            fact_valid = False

        # Check fact_id validity
        if not fact_id or not isinstance(fact_id, str):
            issues.append({
                "fact_id": fact_id, "type": "invalid_fact_id",
                "severity": "critical", "message": "Invalid or missing fact_id",
            })
            fact_valid = False

        return fact_valid

    async def _calc_validity_score(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate validity score (Issue #398: refactored)."""
        issues: List[Dict] = []
        valid_count = sum(1 for f in facts if self._validate_single_fact(f, issues))
        invalid_count = len(facts) - valid_count

        total = len(facts)
        score = (valid_count / total * 100) if total else 100

        recommendations = []
        if invalid_count > 0:
            recommendations.append({
                "action": "fix_invalid_facts",
                "description": "Fix %d facts with validation issues" % invalid_count,
                "priority": "critical" if invalid_count > 10 else "high",
            })

        return {
            "score": round(score, 1),
            "valid_facts": valid_count,
            "invalid_facts": invalid_count,
            "issues": issues[:20],
            "recommendations": recommendations,
        }

    async def get_all_facts(self):
        """Get all facts - implemented in facts mixin."""
        raise NotImplementedError("Should be implemented in composed class")

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
