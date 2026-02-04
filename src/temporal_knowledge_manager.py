#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Temporal Knowledge Management System
Handles automatic knowledge invalidation and freshness tracking

Features:
- Time-based knowledge expiry with configurable TTL
- Content freshness scoring based on modification patterns
- Intelligent cache invalidation without blocking operations
- Priority-based refresh scheduling for critical knowledge
- Temporal analytics for knowledge usage patterns
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.constants.threshold_constants import TimingConstants
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("temporal_knowledge_manager")

# Performance optimization: O(1) lookup for priority classification (Issue #326)
CRITICAL_CATEGORY_KEYWORDS = {"security", "system", "critical"}
CRITICAL_PATH_KEYWORDS = {"security", "auth", "claude.md"}
HIGH_CATEGORY_KEYWORDS = {"api", "user-guide", "architecture"}
HIGH_PATH_KEYWORDS = {"api", "guide", "readme"}
MEDIUM_CATEGORY_KEYWORDS = {"developer", "documentation"}
LOW_CATEGORY_KEYWORDS = {"reports", "logs", "archive"}


class KnowledgePriority(Enum):
    """Priority levels for knowledge content."""

    CRITICAL = "critical"  # Core system docs, security
    HIGH = "high"  # User guides, API docs
    MEDIUM = "medium"  # Developer docs, tutorials
    LOW = "low"  # Reports, logs, archived content


class FreshnessStatus(Enum):
    """Freshness status of knowledge content."""

    FRESH = "fresh"  # Recently updated, high confidence
    AGING = "aging"  # Older but still valid
    STALE = "stale"  # Needs review/refresh
    EXPIRED = "expired"  # Should be invalidated


@dataclass
class TemporalMetadata:
    """Temporal metadata for knowledge content."""

    content_id: str
    created_time: float
    last_modified: float
    last_accessed: float
    access_count: int = 0
    priority: KnowledgePriority = KnowledgePriority.MEDIUM
    ttl_hours: float = 168.0  # 1 week default
    freshness_score: float = 1.0
    update_frequency: float = 0.0  # Updates per day
    invalidation_time: Optional[float] = None

    def is_expired(self) -> bool:
        """Check if content has exceeded its TTL."""
        if self.invalidation_time:
            return time.time() > self.invalidation_time
        return time.time() > (self.last_modified + self.ttl_hours * 3600)

    def get_age_hours(self) -> float:
        """Get age in hours since last modification."""
        return (time.time() - self.last_modified) / 3600

    def get_freshness_status(self) -> FreshnessStatus:
        """Determine freshness status based on age and priority."""
        age_hours = self.get_age_hours()
        ttl_ratio = age_hours / self.ttl_hours

        if ttl_ratio > 1.0:
            return FreshnessStatus.EXPIRED
        elif ttl_ratio > 0.8:
            return FreshnessStatus.STALE
        elif ttl_ratio > 0.5:
            return FreshnessStatus.AGING
        else:
            return FreshnessStatus.FRESH


@dataclass
class InvalidationJob:
    """Job for invalidating expired knowledge."""

    content_ids: List[str]
    priority: KnowledgePriority
    scheduled_time: float
    job_type: str = "expiry"  # expiry, manual, dependency
    estimated_duration: float = 0.0


class TemporalKnowledgeManager:
    """
    Manages temporal aspects of knowledge base content.

    Key responsibilities:
    1. Track content freshness and expiry
    2. Automatic invalidation of stale knowledge
    3. Priority-based refresh scheduling
    4. Temporal analytics and insights
    5. Non-blocking background operations
    """

    def __init__(self):
        """Initialize temporal manager with tracking, queues, and analytics."""
        # Temporal tracking
        self.temporal_metadata: Dict[str, TemporalMetadata] = {}
        self.invalidation_queue: List[InvalidationJob] = []

        # Configuration
        self.default_ttl_by_priority = {
            KnowledgePriority.CRITICAL: 24.0,  # 1 day
            KnowledgePriority.HIGH: 72.0,  # 3 days
            KnowledgePriority.MEDIUM: 168.0,  # 1 week
            KnowledgePriority.LOW: 720.0,  # 30 days
        }

        # Background processing
        self.background_task = None
        self.is_running = False
        self.check_interval_minutes = 30

        # Analytics
        self.temporal_analytics = {
            "total_invalidations": 0,
            "total_refreshes": 0,
            "avg_content_lifetime": 0.0,
            "most_accessed_content": [],
            "staleness_distribution": {},
        }

        logger.info("TemporalKnowledgeManager initialized")

    def determine_content_priority(self, metadata: Dict[str, Any]) -> KnowledgePriority:
        """Determine priority level based on content metadata."""
        category = metadata.get("category", "").lower()
        source_path = metadata.get("relative_path", "").lower()

        # Critical content (Issue #326: O(1) lookups)
        if any(keyword in category for keyword in CRITICAL_CATEGORY_KEYWORDS):
            return KnowledgePriority.CRITICAL
        if any(keyword in source_path for keyword in CRITICAL_PATH_KEYWORDS):
            return KnowledgePriority.CRITICAL

        # High priority content (Issue #326: O(1) lookups)
        if any(keyword in category for keyword in HIGH_CATEGORY_KEYWORDS):
            return KnowledgePriority.HIGH
        if any(keyword in source_path for keyword in HIGH_PATH_KEYWORDS):
            return KnowledgePriority.HIGH

        # Medium priority content (Issue #326: O(1) lookups)
        if any(keyword in category for keyword in MEDIUM_CATEGORY_KEYWORDS):
            return KnowledgePriority.MEDIUM

        # Low priority (reports, logs, etc.) (Issue #326: O(1) lookups)
        if any(keyword in category for keyword in LOW_CATEGORY_KEYWORDS):
            return KnowledgePriority.LOW

        return KnowledgePriority.MEDIUM  # Default

    def register_content(
        self, content_id: str, metadata: Dict[str, Any], content_hash: str
    ) -> TemporalMetadata:
        """Register new content with temporal tracking."""
        current_time = time.time()

        # Determine priority
        priority = self.determine_content_priority(metadata)

        # Calculate TTL based on priority
        ttl_hours = self.default_ttl_by_priority.get(priority, 168.0)

        # Create temporal metadata
        temporal_meta = TemporalMetadata(
            content_id=content_id,
            created_time=current_time,
            last_modified=current_time,
            last_accessed=current_time,
            priority=priority,
            ttl_hours=ttl_hours,
        )

        # Store with content hash for change detection
        self.temporal_metadata[content_id] = temporal_meta

        logger.debug(
            f"Registered content: {content_id} (priority: {priority.value}, TTL: {ttl_hours}h)"
        )
        return temporal_meta

    def update_content_access(self, content_id: str):
        """Update access tracking for content."""
        if content_id in self.temporal_metadata:
            meta = self.temporal_metadata[content_id]
            meta.last_accessed = time.time()
            meta.access_count += 1

            # Update freshness score based on access patterns
            self._update_freshness_score(meta)

    def update_content_modification(self, content_id: str, new_hash: str):
        """Update modification tracking when content changes."""
        if content_id in self.temporal_metadata:
            meta = self.temporal_metadata[content_id]
            current_time = time.time()

            # Calculate update frequency
            time_since_last = current_time - meta.last_modified
            if time_since_last > 0:
                # Exponential moving average of update frequency
                new_frequency = 86400 / time_since_last  # Updates per day
                meta.update_frequency = (meta.update_frequency * 0.8) + (
                    new_frequency * 0.2
                )

            meta.last_modified = current_time
            meta.freshness_score = 1.0  # Reset to fresh

            logger.debug(
                f"Updated modification: {content_id} (frequency: {meta.update_frequency:.2f}/day)"
            )

    def _update_freshness_score(self, meta: TemporalMetadata):
        """Update freshness score based on various factors."""
        current_time = time.time()

        # Age factor (decreases with age)
        age_hours = (current_time - meta.last_modified) / 3600
        age_factor = max(0, 1 - (age_hours / meta.ttl_hours))

        # Access factor (increases with recent access)
        time_since_access = (current_time - meta.last_accessed) / 3600
        access_factor = max(0, 1 - (time_since_access / 24))  # 24-hour access window

        # Update frequency factor
        frequency_factor = min(1.0, meta.update_frequency / 2.0)  # Cap at 2 updates/day

        # Combined freshness score
        meta.freshness_score = (
            (age_factor * 0.5) + (access_factor * 0.3) + (frequency_factor * 0.2)
        )

    async def scan_for_expired_content(self) -> List[InvalidationJob]:
        """Scan for expired content and create invalidation jobs."""
        expired_jobs = []
        current_time = time.time()

        # Group by priority for efficient processing
        expired_by_priority = {priority: [] for priority in KnowledgePriority}

        for content_id, meta in self.temporal_metadata.items():
            if meta.is_expired():
                expired_by_priority[meta.priority].append(content_id)

        # Create invalidation jobs
        for priority, content_ids in expired_by_priority.items():
            if content_ids:
                job = InvalidationJob(
                    content_ids=content_ids,
                    priority=priority,
                    scheduled_time=current_time,
                    job_type="expiry",
                    estimated_duration=len(content_ids) * 0.1,  # 0.1s per content
                )
                expired_jobs.append(job)

        if expired_jobs:
            logger.info(
                f"Found {sum(len(job.content_ids) for job in expired_jobs)} expired content items"
            )

        return expired_jobs

    async def process_invalidation_job(self, job: InvalidationJob, kb_instance):
        """Process an invalidation job by removing expired content."""
        try:
            logger.info(
                f"Processing invalidation job: {len(job.content_ids)} items (priority: {job.priority.value})"
            )

            # Delete all facts in parallel - eliminates N+1 sequential deletions
            async def delete_content(content_id: str) -> bool:
                """Delete a single content item and return success status."""
                try:
                    await kb_instance.delete_fact(content_id)
                    return True
                except Exception as e:
                    logger.warning("Failed to invalidate content %s: %s", content_id, e)
                    return False

            results = await asyncio.gather(
                *[delete_content(cid) for cid in job.content_ids],
                return_exceptions=True,
            )

            # Process results and update temporal tracking
            removed_count = 0
            for content_id, result in zip(job.content_ids, results):
                if result is True:
                    # Remove from temporal tracking
                    if content_id in self.temporal_metadata:
                        del self.temporal_metadata[content_id]
                    removed_count += 1

            # Update analytics
            self.temporal_analytics["total_invalidations"] += removed_count

            logger.info(
                f"Invalidation job completed: {removed_count}/{len(job.content_ids)} items removed"
            )

        except Exception as e:
            logger.error("Invalidation job failed: %s", e)

    async def schedule_smart_refresh(self) -> List[str]:
        """Schedule smart refresh for content that's about to expire."""
        refresh_candidates = []

        for content_id, meta in self.temporal_metadata.items():
            status = meta.get_freshness_status()

            # Schedule refresh for stale high-priority content
            if status == FreshnessStatus.STALE and meta.priority in {
                KnowledgePriority.CRITICAL,
                KnowledgePriority.HIGH,
            }:
                refresh_candidates.append(content_id)

            # Schedule refresh for frequently accessed aging content
            elif status == FreshnessStatus.AGING and meta.access_count > 10:
                refresh_candidates.append(content_id)

        if refresh_candidates:
            logger.info(
                f"Scheduled smart refresh for {len(refresh_candidates)} content items"
            )

        return refresh_candidates

    def _collect_distribution_stats(
        self,
    ) -> tuple[Dict[str, int], Dict[str, int], List[float], List[int], List[float]]:
        """Collect status/priority distributions and raw statistics lists.

        Returns:
            Tuple of (status_distribution, priority_distribution, ages,
            access_counts, freshness_scores).

        Issue #620.
        """
        status_distribution = {status.value: 0 for status in FreshnessStatus}
        priority_distribution = {priority.value: 0 for priority in KnowledgePriority}
        ages: List[float] = []
        access_counts: List[int] = []
        freshness_scores: List[float] = []

        for meta in self.temporal_metadata.values():
            status = meta.get_freshness_status()
            status_distribution[status.value] += 1
            priority_distribution[meta.priority.value] += 1
            ages.append(meta.get_age_hours())
            access_counts.append(meta.access_count)
            freshness_scores.append(meta.freshness_score)

        return (
            status_distribution,
            priority_distribution,
            ages,
            access_counts,
            freshness_scores,
        )

    def _build_most_accessed_list(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Build list of most accessed content items.

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of dictionaries with content_id, access_count, age_hours, priority.

        Issue #620.
        """
        most_accessed = sorted(
            self.temporal_metadata.items(),
            key=lambda x: x[1].access_count,
            reverse=True,
        )[:limit]

        return [
            {
                "content_id": content_id,
                "access_count": meta.access_count,
                "age_hours": meta.get_age_hours(),
                "priority": meta.priority.value,
            }
            for content_id, meta in most_accessed
        ]

    async def get_temporal_analytics(self) -> Dict[str, Any]:
        """Get temporal analytics and insights. Issue #620."""
        total_content = len(self.temporal_metadata)
        if total_content == 0:
            return {"total_content": 0, "message": "No temporal metadata available"}

        (
            status_distribution,
            priority_distribution,
            ages,
            access_counts,
            freshness_scores,
        ) = self._collect_distribution_stats()

        avg_age = sum(ages) / len(ages) if ages else 0
        avg_access_count = (
            sum(access_counts) / len(access_counts) if access_counts else 0
        )
        avg_freshness = (
            sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0
        )

        return {
            "total_content": total_content,
            "status_distribution": status_distribution,
            "priority_distribution": priority_distribution,
            "averages": {
                "age_hours": avg_age,
                "access_count": avg_access_count,
                "freshness_score": avg_freshness,
            },
            "most_accessed_content": self._build_most_accessed_list(),
            "analytics": self.temporal_analytics,
            "analysis_timestamp": datetime.now().isoformat(),
        }

    async def start_background_processing(
        self, kb_instance, check_interval_minutes: int = 30
    ):
        """Start background processing for temporal management."""
        if self.is_running:
            logger.warning("Background processing already running")
            return

        self.is_running = True
        self.check_interval_minutes = check_interval_minutes

        logger.info(
            f"Starting temporal background processing (interval: {check_interval_minutes} minutes)"
        )

        try:
            while self.is_running:
                try:
                    # Wait for check interval
                    await asyncio.sleep(check_interval_minutes * 60)

                    if not self.is_running:
                        break

                    # Scan for expired content
                    invalidation_jobs = await self.scan_for_expired_content()

                    # Process invalidation jobs
                    for job in invalidation_jobs:
                        await self.process_invalidation_job(job, kb_instance)

                    # Schedule smart refreshes
                    refresh_candidates = await self.schedule_smart_refresh()

                    if invalidation_jobs or refresh_candidates:
                        logger.info(
                            "Temporal processing: %d invalidations, %d refreshes",
                            len(invalidation_jobs),
                            len(refresh_candidates),
                        )

                except asyncio.CancelledError:
                    logger.info("Temporal background processing cancelled")
                    break
                except Exception as e:
                    logger.error("Temporal background processing error: %s", e)
                    await asyncio.sleep(
                        TimingConstants.STANDARD_TIMEOUT
                    )  # Wait before retry

        finally:
            self.is_running = False
            logger.info("Temporal background processing stopped")

    async def stop_background_processing(self):
        """Stop background processing."""
        if not self.is_running:
            return

        logger.info("Stopping temporal background processing...")
        self.is_running = False

        if self.background_task and not self.background_task.done():
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                logger.debug("Temporal background task cancelled during shutdown")

        logger.info("Temporal background processing stopped")

    def get_content_status(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status for specific content."""
        if content_id not in self.temporal_metadata:
            return None

        meta = self.temporal_metadata[content_id]
        status = meta.get_freshness_status()

        return {
            "content_id": content_id,
            "freshness_status": status.value,
            "age_hours": meta.get_age_hours(),
            "freshness_score": meta.freshness_score,
            "access_count": meta.access_count,
            "priority": meta.priority.value,
            "ttl_hours": meta.ttl_hours,
            "is_expired": meta.is_expired(),
            "last_accessed": datetime.fromtimestamp(meta.last_accessed).isoformat(),
            "last_modified": datetime.fromtimestamp(meta.last_modified).isoformat(),
        }


# Global instance for system integration (thread-safe)
import threading

_temporal_manager_instance = None
_temporal_manager_lock = threading.Lock()


def get_temporal_manager() -> TemporalKnowledgeManager:
    """Get the global temporal knowledge manager instance (thread-safe)."""
    global _temporal_manager_instance

    if _temporal_manager_instance is None:
        with _temporal_manager_lock:
            # Double-check after acquiring lock
            if _temporal_manager_instance is None:
                _temporal_manager_instance = TemporalKnowledgeManager()

    return _temporal_manager_instance
