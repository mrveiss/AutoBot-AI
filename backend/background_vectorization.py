# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Background Vectorization Service

Automatically vectorizes new facts in the background without blocking operations.
Uses FastAPI background tasks and periodic checks.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional


logger = logging.getLogger(__name__)


class BackgroundVectorizer:
    """Background service for automatic fact vectorization"""

    def __init__(self):
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.check_interval = 300  # 5 minutes
        self.batch_size = 50
        self.batch_delay = 0.5

    async def vectorize_pending_facts(self, kb):
        """Background task to vectorize all pending facts"""
        if self.is_running:
            logger.info("Vectorization already running, skipping...")
            return

        try:
            self.is_running = True
            self.last_run = datetime.now()

            logger.info("Starting background vectorization...")

            # Get all fact keys
            fact_keys = await kb._scan_redis_keys_async("fact:*")

            if not fact_keys:
                logger.info("No facts found for vectorization")
                return

            success_count = 0
            skipped_count = 0
            failed_count = 0

            total_batches = (len(fact_keys) + self.batch_size - 1) // self.batch_size

            logger.info(f"Processing {len(fact_keys)} facts in {total_batches} batches")

            # Process in batches
            for batch_num in range(total_batches):
                start_idx = batch_num * self.batch_size
                end_idx = min(start_idx + self.batch_size, len(fact_keys))
                batch = fact_keys[start_idx:end_idx]

                for fact_key in batch:
                    try:
                        # Check vectorization status FIRST - O(1) field lookup
                        # This avoids loading entire fact data for already-vectorized facts
                        status_bytes = await kb.aioredis_client.hget(
                            fact_key, "vectorization_status"
                        )
                        if status_bytes:
                            status = (
                                status_bytes.decode("utf-8")
                                if isinstance(status_bytes, bytes)
                                else str(status_bytes)
                            )
                            if status == "completed":
                                skipped_count += 1
                                continue  # Skip already-vectorized fact

                        # Get fact data only if vectorization needed
                        fact_data = await kb.aioredis_client.hgetall(fact_key)

                        if not fact_data:
                            failed_count += 1
                            continue

                        # Extract content and metadata
                        content_bytes = fact_data.get(b"content", b"")
                        content = (
                            content_bytes.decode("utf-8")
                            if isinstance(content_bytes, bytes)
                            else str(content_bytes)
                        )

                        metadata_str = fact_data.get(b"metadata", b"{}")
                        import json

                        metadata = json.loads(
                            metadata_str.decode("utf-8")
                            if isinstance(metadata_str, bytes)
                            else metadata_str
                        )

                        # Extract fact ID
                        fact_id = (
                            fact_key.split(":")[-1] if ":" in fact_key else fact_key
                        )

                        # Check if already indexed in vector store
                        # Try to query the vector index for this fact_id
                        try:
                            # Check if this fact is already in vector index
                            if kb.vector_index:
                                # Use LlamaIndex to check if document exists
                                from llama_index.core import Document

                                # Create document for vectorization
                                document = Document(
                                    text=content, metadata=metadata, doc_id=fact_id
                                )

                                # Insert into vector index
                                await asyncio.to_thread(
                                    kb.vector_index.insert, document
                                )
                                success_count += 1
                                logger.debug(f"Vectorized fact {fact_id}")

                                # Persist vectorization status to Redis
                                try:
                                    await kb.aioredis_client.hset(
                                        fact_key,
                                        mapping={
                                            "vectorization_status": "completed",
                                            "vectorized_at": datetime.now().isoformat(),
                                        },
                                    )
                                except Exception as status_error:
                                    # Don't let status persistence failure mask successful vectorization
                                    logger.warning(
                                        f"Failed to persist vectorization status for {fact_id}: {status_error}"
                                    )
                            else:
                                logger.warning("Vector index not available")
                                failed_count += 1
                        except Exception as doc_error:
                            # If document already exists or other error, skip
                            if "already exists" in str(doc_error).lower():
                                skipped_count += 1
                                # Mark as completed so we skip on future runs
                                try:
                                    await kb.aioredis_client.hset(
                                        fact_key,
                                        mapping={
                                            "vectorization_status": "completed",
                                            "vectorized_at": datetime.now().isoformat(),
                                        },
                                    )
                                except Exception:
                                    pass  # Best effort, non-critical
                            else:
                                failed_count += 1
                                logger.error(
                                    f"Failed to vectorize {fact_id}: {doc_error}"
                                )

                    except Exception as e:
                        failed_count += 1
                        logger.error(f"Error vectorizing fact {fact_key}: {e}")

                # Delay between batches
                if batch_num < total_batches - 1:
                    await asyncio.sleep(self.batch_delay)

            logger.info(
                f"Background vectorization complete: {success_count} vectorized, {skipped_count} skipped, {failed_count} failed"
            )

        except Exception as e:
            logger.error(f"Background vectorization error: {e}")
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
                logger.error(f"Periodic check error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error


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
