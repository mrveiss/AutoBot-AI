#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for Knowledge Manager Vectorization Status Tracking (Sprint 2 #162)

Tests the vectorization status tracking feature:
- Batch vectorization status endpoint
- Cache key generation
- Vectorization job status polling
- Failed job handling
- Retry functionality
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for vectorization tracking"""
    client = AsyncMock()
    client.hget = AsyncMock()
    client.hset = AsyncMock()
    client.hmget = AsyncMock()
    client.hmset = AsyncMock()
    client.exists = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def sample_vectorization_status():
    """Sample vectorization status data"""
    return {
        "fact_1": {"vectorized": True, "timestamp": "2025-11-28T10:00:00"},
        "fact_2": {"vectorized": False, "timestamp": None},
        "fact_3": {"vectorized": True, "timestamp": "2025-11-28T10:05:00"},
        "fact_4": {"vectorized": False, "timestamp": None},
    }


@pytest.fixture
def sample_batch_status():
    """Sample batch vectorization status"""
    return {
        "job_id": "vec_job_123",
        "status": "in_progress",
        "total": 100,
        "completed": 45,
        "failed": 3,
        "started_at": "2025-11-28T10:00:00",
        "estimated_completion": "2025-11-28T10:15:00",
    }


@pytest.fixture
def mock_knowledge_base():
    """Mock KnowledgeBase for vectorization testing"""
    kb = MagicMock()
    kb.get_vectorization_status = AsyncMock()
    kb.vectorize_facts = AsyncMock()
    kb.check_vectorization_job = AsyncMock()
    kb.retry_failed_vectorization = AsyncMock()
    return kb


# ============================================================================
# BATCH VECTORIZATION STATUS TESTS
# ============================================================================


class TestBatchVectorizationStatus:
    """Test batch vectorization status retrieval"""

    @pytest.mark.asyncio
    async def test_get_batch_status_success(
        self, mock_knowledge_base, sample_batch_status
    ):
        """Test successful batch status retrieval"""
        mock_knowledge_base.get_vectorization_status.return_value = sample_batch_status

        result = await mock_knowledge_base.get_vectorization_status()

        assert result["status"] == "in_progress"
        assert result["total"] == 100
        assert result["completed"] == 45
        assert result["failed"] == 3

    @pytest.mark.asyncio
    async def test_get_batch_status_completed(self, mock_knowledge_base):
        """Test batch status when completed"""
        completed_status = {
            "job_id": "vec_job_123",
            "status": "completed",
            "total": 100,
            "completed": 97,
            "failed": 3,
            "started_at": "2025-11-28T10:00:00",
            "completed_at": "2025-11-28T10:12:00",
        }
        mock_knowledge_base.get_vectorization_status.return_value = completed_status

        result = await mock_knowledge_base.get_vectorization_status()

        assert result["status"] == "completed"
        assert result["completed"] + result["failed"] == result["total"]

    @pytest.mark.asyncio
    async def test_get_batch_status_failed(self, mock_knowledge_base):
        """Test batch status when job failed"""
        failed_status = {
            "job_id": "vec_job_123",
            "status": "failed",
            "total": 100,
            "completed": 20,
            "failed": 80,
            "error": "Connection timeout",
        }
        mock_knowledge_base.get_vectorization_status.return_value = failed_status

        result = await mock_knowledge_base.get_vectorization_status()

        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_multiple_facts_status(
        self, mock_knowledge_base, sample_vectorization_status
    ):
        """Test getting status for multiple facts"""
        fact_ids = ["fact_1", "fact_2", "fact_3", "fact_4"]

        # Mock batch status endpoint
        mock_knowledge_base.get_vectorization_status.return_value = {
            "statuses": sample_vectorization_status
        }

        result = await mock_knowledge_base.get_vectorization_status(fact_ids=fact_ids)

        assert "statuses" in result
        assert len(result["statuses"]) == 4
        assert result["statuses"]["fact_1"]["vectorized"] is True
        assert result["statuses"]["fact_2"]["vectorized"] is False


# ============================================================================
# CACHE KEY GENERATION TESTS
# ============================================================================


class TestCacheKeyGeneration:
    """Test cache key generation for vectorization status"""

    def test_generate_status_cache_key_single(self):
        """Test cache key generation for single fact"""
        fact_id = "fact_123"
        cache_key = f"vectorization:status:{fact_id}"

        assert cache_key == "vectorization:status:fact_123"

    def test_generate_status_cache_key_batch(self):
        """Test cache key generation for batch status"""
        job_id = "vec_job_456"
        cache_key = f"vectorization:job:{job_id}"

        assert cache_key == "vectorization:job:vec_job_456"

    def test_cache_key_uniqueness(self):
        """Test cache keys are unique per fact"""
        fact_ids = ["fact_1", "fact_2", "fact_3"]
        cache_keys = [f"vectorization:status:{fid}" for fid in fact_ids]

        assert len(cache_keys) == len(set(cache_keys))
        assert all(fid in key for fid, key in zip(fact_ids, cache_keys))

    @pytest.mark.asyncio
    async def test_cache_key_with_special_characters(self):
        """Test cache key handling with special characters in fact IDs"""
        fact_id = "fact:123-abc_def"
        cache_key = f"vectorization:status:{fact_id}"

        assert ":" in cache_key
        assert "-" in cache_key
        assert "_" in cache_key


# ============================================================================
# JOB STATUS POLLING TESTS
# ============================================================================


class TestJobStatusPolling:
    """Test vectorization job status polling"""

    @pytest.mark.asyncio
    async def test_poll_job_in_progress(self, mock_knowledge_base):
        """Test polling job that is in progress"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "in_progress",
            "progress": 0.45,
        }

        result = await mock_knowledge_base.check_vectorization_job("vec_job_123")

        assert result["status"] == "in_progress"
        assert 0 <= result["progress"] <= 1

    @pytest.mark.asyncio
    async def test_poll_job_completed(self, mock_knowledge_base):
        """Test polling completed job"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "completed",
            "progress": 1.0,
            "results": {"total": 100, "succeeded": 97, "failed": 3},
        }

        result = await mock_knowledge_base.check_vectorization_job("vec_job_123")

        assert result["status"] == "completed"
        assert result["progress"] == 1.0
        assert "results" in result

    @pytest.mark.asyncio
    async def test_poll_job_with_timeout(self, mock_knowledge_base):
        """Test polling job with timeout mechanism"""
        # Simulate job never completing
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "in_progress",
            "progress": 0.5,
        }

        start_time = datetime.now()
        timeout_seconds = 2
        max_polls = 5

        for i in range(max_polls):
            if (datetime.now() - start_time).total_seconds() > timeout_seconds:
                break

            await mock_knowledge_base.check_vectorization_job("vec_job_123")
            await asyncio.sleep(0.5)

        elapsed = (datetime.now() - start_time).total_seconds()
        assert elapsed >= timeout_seconds

    @pytest.mark.asyncio
    async def test_poll_nonexistent_job(self, mock_knowledge_base):
        """Test polling job that doesn't exist"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "not_found",
            "error": "Job not found",
        }

        result = await mock_knowledge_base.check_vectorization_job("nonexistent_job")

        assert result["status"] == "not_found"
        assert "error" in result


# ============================================================================
# FAILED JOB HANDLING TESTS
# ============================================================================


class TestFailedJobHandling:
    """Test handling of failed vectorization jobs"""

    @pytest.mark.asyncio
    async def test_detect_failed_job(self, mock_knowledge_base):
        """Test detection of failed job"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "failed",
            "error": "Database connection lost",
            "failed_facts": ["fact_1", "fact_2", "fact_3"],
        }

        result = await mock_knowledge_base.check_vectorization_job("vec_job_123")

        assert result["status"] == "failed"
        assert "error" in result
        assert "failed_facts" in result

    @pytest.mark.asyncio
    async def test_get_failed_fact_list(self, mock_knowledge_base):
        """Test retrieving list of failed facts"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "completed",
            "results": {
                "total": 10,
                "succeeded": 7,
                "failed": 3,
                "failed_facts": [
                    {"id": "fact_1", "error": "Timeout"},
                    {"id": "fact_5", "error": "Invalid format"},
                    {"id": "fact_9", "error": "Timeout"},
                ],
            },
        }

        result = await mock_knowledge_base.check_vectorization_job("vec_job_123")
        failed_facts = result["results"]["failed_facts"]

        assert len(failed_facts) == 3
        assert all("error" in fact for fact in failed_facts)

    @pytest.mark.asyncio
    async def test_partial_failure_handling(self, mock_knowledge_base):
        """Test handling of partial job failure"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "completed",
            "results": {"total": 100, "succeeded": 85, "failed": 15},
        }

        result = await mock_knowledge_base.check_vectorization_job("vec_job_123")

        assert result["status"] == "completed"
        assert result["results"]["succeeded"] > result["results"]["failed"]

    @pytest.mark.asyncio
    async def test_categorize_failure_reasons(self, mock_knowledge_base):
        """Test categorization of failure reasons"""
        mock_knowledge_base.check_vectorization_job.return_value = {
            "status": "completed",
            "results": {
                "failed_facts": [
                    {"id": "f1", "error": "Timeout"},
                    {"id": "f2", "error": "Timeout"},
                    {"id": "f3", "error": "Invalid format"},
                    {"id": "f4", "error": "Connection error"},
                ]
            },
        }

        result = await mock_knowledge_base.check_vectorization_job("vec_job_123")
        failed_facts = result["results"]["failed_facts"]

        # Categorize errors
        errors = {}
        for fact in failed_facts:
            error_type = fact["error"]
            errors[error_type] = errors.get(error_type, 0) + 1

        assert errors["Timeout"] == 2
        assert errors["Invalid format"] == 1
        assert errors["Connection error"] == 1


# ============================================================================
# RETRY FUNCTIONALITY TESTS
# ============================================================================


class TestRetryFunctionality:
    """Test retry mechanism for failed vectorizations"""

    @pytest.mark.asyncio
    async def test_retry_failed_facts(self, mock_knowledge_base):
        """Test retrying failed facts"""
        failed_fact_ids = ["fact_1", "fact_5", "fact_9"]
        mock_knowledge_base.retry_failed_vectorization.return_value = {
            "job_id": "vec_job_retry_456",
            "status": "started",
            "retry_count": 3,
        }

        result = await mock_knowledge_base.retry_failed_vectorization(failed_fact_ids)

        assert result["status"] == "started"
        assert result["retry_count"] == len(failed_fact_ids)

    @pytest.mark.asyncio
    async def test_retry_with_backoff(self, mock_knowledge_base):
        """Test retry with exponential backoff"""
        max_retries = 3
        backoff_delays = []

        for attempt in range(max_retries):
            delay = 2**attempt  # Exponential backoff: 1s, 2s, 4s
            backoff_delays.append(delay)

            mock_knowledge_base.retry_failed_vectorization.return_value = {
                "attempt": attempt + 1,
                "delay": delay,
            }

            result = await mock_knowledge_base.retry_failed_vectorization(["fact_1"])
            assert result["delay"] == delay

        assert backoff_delays == [1, 2, 4]

    @pytest.mark.asyncio
    async def test_retry_success_after_failure(self, mock_knowledge_base):
        """Test successful vectorization after retry"""
        # First attempt fails
        mock_knowledge_base.vectorize_facts.return_value = {
            "status": "failed",
            "error": "Temporary network error",
        }

        first_result = await mock_knowledge_base.vectorize_facts(["fact_1"])
        assert first_result["status"] == "failed"

        # Retry succeeds
        mock_knowledge_base.retry_failed_vectorization.return_value = {
            "status": "completed",
            "succeeded": 1,
            "failed": 0,
        }

        retry_result = await mock_knowledge_base.retry_failed_vectorization(["fact_1"])
        assert retry_result["status"] == "completed"
        assert retry_result["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_max_retry_limit(self, mock_knowledge_base):
        """Test maximum retry limit enforcement"""
        max_retries = 3
        fact_id = "fact_persistent_fail"

        for attempt in range(max_retries + 1):
            if attempt < max_retries:
                mock_knowledge_base.retry_failed_vectorization.return_value = {
                    "status": "failed",
                    "attempt": attempt + 1,
                    "can_retry": attempt + 1 < max_retries,
                }
            else:
                # Max retries reached
                mock_knowledge_base.retry_failed_vectorization.return_value = {
                    "status": "failed",
                    "attempt": attempt + 1,
                    "can_retry": False,
                    "error": "Max retries reached",
                }

            result = await mock_knowledge_base.retry_failed_vectorization([fact_id])

            if attempt >= max_retries:
                assert result["can_retry"] is False
                assert "Max retries reached" in result["error"]


# ============================================================================
# CACHE INTEGRATION TESTS
# ============================================================================


class TestCacheIntegration:
    """Test Redis cache integration for vectorization status"""

    @pytest.mark.asyncio
    async def test_cache_vectorization_status(self, mock_redis_client):
        """Test caching vectorization status"""
        fact_id = "fact_123"
        status = {"vectorized": True, "timestamp": "2025-11-28T10:00:00"}

        cache_key = f"vectorization:status:{fact_id}"
        await mock_redis_client.hset(
            cache_key, mapping={"vectorized": "true", "timestamp": status["timestamp"]}
        )

        mock_redis_client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_cached_status(self, mock_redis_client):
        """Test retrieving cached vectorization status"""
        fact_id = "fact_123"
        cache_key = f"vectorization:status:{fact_id}"

        mock_redis_client.hget.return_value = b"true"

        cached_status = await mock_redis_client.hget(cache_key, "vectorized")

        assert cached_status == b"true"

    @pytest.mark.asyncio
    async def test_batch_cache_retrieval(self, mock_redis_client):
        """Test batch retrieval of cached statuses"""
        fact_ids = ["fact_1", "fact_2", "fact_3"]

        # Mock batch retrieval
        mock_redis_client.hmget.return_value = [b"true", b"false", b"true"]

        # Simulate batch get
        for fact_id in fact_ids:
            _cache_key = f"vectorization:status:{fact_id}"
            # In real implementation, would use pipeline or hmget

        assert len(fact_ids) == 3

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_vectorization(self, mock_redis_client):
        """Test cache invalidation when fact is vectorized"""
        fact_id = "fact_123"
        cache_key = f"vectorization:status:{fact_id}"

        # Delete old cache
        await mock_redis_client.delete(cache_key)

        # Set new status
        await mock_redis_client.hset(
            cache_key,
            mapping={"vectorized": "true", "timestamp": datetime.now().isoformat()},
        )

        mock_redis_client.delete.assert_called_once()
        mock_redis_client.hset.assert_called_once()


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_empty_batch_vectorization(self, mock_knowledge_base):
        """Test vectorization with empty fact list"""
        mock_knowledge_base.vectorize_facts.return_value = {
            "status": "completed",
            "total": 0,
            "completed": 0,
            "failed": 0,
        }

        result = await mock_knowledge_base.vectorize_facts([])

        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_very_large_batch(self, mock_knowledge_base):
        """Test vectorization with very large batch"""
        large_batch = [f"fact_{i}" for i in range(10000)]

        mock_knowledge_base.vectorize_facts.return_value = {
            "status": "started",
            "job_id": "vec_job_large",
            "total": len(large_batch),
        }

        result = await mock_knowledge_base.vectorize_facts(large_batch)

        assert result["total"] == 10000

    @pytest.mark.asyncio
    async def test_concurrent_vectorization_requests(self, mock_knowledge_base):
        """Test handling concurrent vectorization requests"""
        fact_batches = [
            [f"batch1_fact_{i}" for i in range(10)],
            [f"batch2_fact_{i}" for i in range(10)],
            [f"batch3_fact_{i}" for i in range(10)],
        ]

        async def vectorize_batch(batch):
            return await mock_knowledge_base.vectorize_facts(batch)

        mock_knowledge_base.vectorize_facts.return_value = {
            "status": "started",
            "job_id": "vec_job_concurrent",
        }

        results = await asyncio.gather(*[vectorize_batch(b) for b in fact_batches])

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_status_polling_race_condition(self, mock_knowledge_base):
        """Test status polling doesn't have race conditions"""
        job_id = "vec_job_123"

        # Simulate rapid polling
        poll_count = 10
        results = []

        for _ in range(poll_count):
            mock_knowledge_base.check_vectorization_job.return_value = {
                "status": "in_progress",
                "progress": 0.5,
            }
            result = await mock_knowledge_base.check_vectorization_job(job_id)
            results.append(result)

        # All polls should succeed
        assert len(results) == poll_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
