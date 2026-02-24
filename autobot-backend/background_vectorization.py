# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Background Vectorization Service

Automatically vectorizes new facts in the background without blocking operations.
Uses FastAPI background tasks and periodic checks.

Issue #285: Integrated with Embedding Pattern Analyzer for cost tracking.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from constants.threshold_constants import TimingConstants

# Embedding analytics integration (Issue #285)
try:
    from api.analytics_embedding_patterns import (
        EmbeddingUsageRequest,
        get_embedding_analyzer,
    )

    EMBEDDING_ANALYTICS_AVAILABLE = True
except ImportError:
    EMBEDDING_ANALYTICS_AVAILABLE = False
    EmbeddingUsageRequest = None
    logger = logging.getLogger(__name__)
    logger.debug("Embedding analytics not available - usage tracking disabled")

logger = logging.getLogger(__name__)


class BackgroundVectorizer:
    """Background service for automatic fact vectorization"""

    def __init__(self):
        """Initialize background vectorizer with default settings."""
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.check_interval = 300  # 5 minutes
        self.batch_size = 50
        self.batch_delay = 0.5
        # Embedding model used (from config or default)
        self.embedding_model = "nomic-embed-text:latest"

    async def _track_embedding_usage(
        self,
        document_count: int,
        token_count: int,
        processing_time: float,
        success: bool,
        batch_size: int,
    ):
        """Track embedding usage for analytics (Issue #285)."""
        if not EMBEDDING_ANALYTICS_AVAILABLE:
            return

        try:
            analyzer = get_embedding_analyzer()
            request = EmbeddingUsageRequest(
                operation_type="batch_vectorization",
                model=self.embedding_model,
                provider="ollama",
                token_count=token_count,
                document_count=document_count,
                batch_size=batch_size,
                processing_time=processing_time,
                success=success,
                source="background_vectorizer",
            )
            # Fire-and-forget async tracking
            asyncio.create_task(analyzer.record_usage(request))
        except Exception as e:
            logger.debug("Embedding usage tracking failed (non-critical): %s", e)

    def _decode_bytes(self, value: bytes, default: str = "") -> str:
        """Decode bytes to string (Issue #336 - extracted helper)."""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value) if value else default

    async def _get_vectorization_status(self, kb, batch: list) -> list:
        """Get vectorization status for a batch (Issue #336 - extracted helper)."""
        async with kb.aioredis_client.pipeline() as pipe:
            for fact_key in batch:
                await pipe.hget(fact_key, "vectorization_status")
            return await pipe.execute()

    def _filter_pending_facts(self, batch: list, all_status: list) -> tuple:
        """Filter out completed facts (Issue #336 - extracted helper)."""
        facts_to_process = []
        skipped = 0
        for fact_key, status_bytes in zip(batch, all_status):
            if status_bytes:
                status = self._decode_bytes(status_bytes)
                if status == "completed":
                    skipped += 1
                    continue
            facts_to_process.append(fact_key)
        return facts_to_process, skipped

    async def _fetch_fact_data(self, kb, facts_to_process: list) -> list:
        """Batch fetch fact data (Issue #336 - extracted helper)."""
        if not facts_to_process:
            return []
        async with kb.aioredis_client.pipeline() as pipe:
            for fact_key in facts_to_process:
                await pipe.hgetall(fact_key)
            return await pipe.execute()

    def _extract_fact_content(self, fact_data: dict) -> tuple:
        """Extract content and metadata from fact data (Issue #336 - extracted helper)."""
        import json

        content_bytes = fact_data.get(b"content", b"")
        content = self._decode_bytes(content_bytes)
        metadata_str = fact_data.get(b"metadata", b"{}")
        metadata = json.loads(self._decode_bytes(metadata_str, "{}"))
        return content, metadata

    async def _mark_vectorization_complete(self, kb, fact_key: str) -> None:
        """Mark fact as vectorized (Issue #336 - extracted helper)."""
        try:
            await kb.aioredis_client.hset(
                fact_key,
                mapping={
                    "vectorization_status": "completed",
                    "vectorized_at": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            logger.debug("Status update failed (non-critical): %s", e)

    async def _vectorize_single_fact(self, kb, fact_key: str, fact_data: dict) -> dict:
        """Vectorize a single fact (Issue #336 - extracted helper)."""
        result = {"success": False, "skipped": False, "tokens": 0}

        if not fact_data:
            return result

        content, metadata = self._extract_fact_content(fact_data)
        fact_id = fact_key.split(":")[-1] if ":" in fact_key else fact_key

        if not kb.vector_index:
            logger.warning("Vector index not available")
            return result

        try:
            from llama_index.core import Document

            document = Document(text=content, metadata=metadata, doc_id=fact_id)
            await asyncio.to_thread(kb.vector_index.insert, document)
            result["success"] = True
            result["tokens"] = int(len(content.split()) * 1.3)
            logger.debug("Vectorized fact %s", fact_id)
            await self._mark_vectorization_complete(kb, fact_key)
        except Exception as doc_error:
            if "already exists" in str(doc_error).lower():
                result["skipped"] = True
                await self._mark_vectorization_complete(kb, fact_key)
            else:
                logger.error("Failed to vectorize %s: %s", fact_id, doc_error)

        return result

    async def _process_batch(self, kb, batch: list) -> dict:
        """Process a batch of facts (Issue #336 - extracted helper)."""
        batch_start_time = time.time()
        stats = {"success": 0, "skipped": 0, "failed": 0, "tokens": 0}

        all_status = await self._get_vectorization_status(kb, batch)
        facts_to_process, already_skipped = self._filter_pending_facts(
            batch, all_status
        )
        stats["skipped"] += already_skipped

        all_fact_data = await self._fetch_fact_data(kb, facts_to_process)

        for fact_key, fact_data in zip(facts_to_process, all_fact_data):
            try:
                result = await self._vectorize_single_fact(kb, fact_key, fact_data)
                if result["success"]:
                    stats["success"] += 1
                    stats["tokens"] += result["tokens"]
                elif result["skipped"]:
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.error("Error vectorizing fact %s: %s", fact_key, e)

        stats["processing_time"] = time.time() - batch_start_time
        return stats

    async def vectorize_pending_facts(self, kb):
        """Background task to vectorize all pending facts"""
        if self.is_running:
            logger.info("Vectorization already running, skipping...")
            return

        try:
            self.is_running = True
            self.last_run = datetime.now()

            logger.info("Starting background vectorization...")

            fact_keys = await kb._scan_redis_keys_async("fact:*")
            if not fact_keys:
                logger.info("No facts found for vectorization")
                return

            total_batches = (len(fact_keys) + self.batch_size - 1) // self.batch_size
            logger.info(
                "Processing %s facts in %s batches", len(fact_keys), total_batches
            )

            total_stats = {"success": 0, "skipped": 0, "failed": 0, "tokens": 0}

            for batch_num in range(total_batches):
                start_idx = batch_num * self.batch_size
                end_idx = min(start_idx + self.batch_size, len(fact_keys))
                batch = fact_keys[start_idx:end_idx]

                batch_stats = await self._process_batch(kb, batch)
                total_stats["success"] += batch_stats["success"]
                total_stats["skipped"] += batch_stats["skipped"]
                total_stats["failed"] += batch_stats["failed"]
                total_stats["tokens"] += batch_stats["tokens"]

                if batch_stats["success"] > 0:
                    await self._track_embedding_usage(
                        document_count=batch_stats["success"],
                        token_count=batch_stats["tokens"],
                        processing_time=batch_stats["processing_time"],
                        success=True,
                        batch_size=len(batch),
                    )

                if batch_num < total_batches - 1:
                    await asyncio.sleep(self.batch_delay)

            logger.info(
                f"Background vectorization complete: {total_stats['success']} vectorized, "
                f"{total_stats['skipped']} skipped, {total_stats['failed']} failed, "
                f"{total_stats['tokens']} tokens processed"
            )

        except Exception as e:
            logger.error("Background vectorization error: %s", e)
        finally:
            self.is_running = False

    async def periodic_check(self, kb):
        """Periodic check for unvectorized facts"""
        while True:
            try:
                await asyncio.sleep(self.check_interval)

                # Check if we should run
                if self.is_running:
                    continue

                if (
                    self.last_run
                    and (datetime.now() - self.last_run).seconds < self.check_interval
                ):
                    continue

                logger.info("Periodic check: Looking for unvectorized facts...")
                await self.vectorize_pending_facts(kb)

            except Exception as e:
                logger.error("Periodic check error: %s", e)
                # Error recovery delay before retry
                await asyncio.sleep(TimingConstants.STANDARD_TIMEOUT)


# Global instance (thread-safe)
import threading

_background_vectorizer: Optional[BackgroundVectorizer] = None
_background_vectorizer_lock = threading.Lock()


def get_background_vectorizer() -> BackgroundVectorizer:
    """Get or create the global background vectorizer (thread-safe)."""
    global _background_vectorizer
    if _background_vectorizer is None:
        with _background_vectorizer_lock:
            # Double-check after acquiring lock
            if _background_vectorizer is None:
                _background_vectorizer = BackgroundVectorizer()
    return _background_vectorizer
