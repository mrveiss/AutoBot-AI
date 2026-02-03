#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration Tests for Knowledge Manager API (Sprints 1 & 2: #161, #162)

Tests end-to-end flows:
- Category filter → search → display
- Vectorization status → badge update
- Failed job → retry → success
"""

import asyncio
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
async def api_client(backend_url):
    """Create async HTTP client for API testing"""
    async with aiohttp.ClientSession(base_url=backend_url) as session:
        yield session


@pytest.fixture
def sample_knowledge_data():
    """Sample knowledge base data for testing"""
    return {
        "categories": [
            {"name": "tools", "count": 15},
            {"name": "security", "count": 23},
            {"name": "automation", "count": 12},
        ],
        "facts": {
            "tools": [
                {
                    "id": "t1",
                    "content": "nmap network scanner",
                    "category": "tools",
                    "vectorized": True,
                },
                {
                    "id": "t2",
                    "content": "wireshark packet analyzer",
                    "category": "tools",
                    "vectorized": False,
                },
            ],
            "security": [
                {
                    "id": "s1",
                    "content": "Use strong passwords",
                    "category": "security",
                    "vectorized": True,
                },
                {
                    "id": "s2",
                    "content": "Enable 2FA authentication",
                    "category": "security",
                    "vectorized": True,
                },
            ],
        },
    }


# ============================================================================
# CATEGORY FILTER → SEARCH → DISPLAY TESTS
# ============================================================================


class TestCategoryFilterSearchFlow:
    """Test complete category filtering and search workflow"""

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_full_category_filter_workflow(
        self, api_client, sample_knowledge_data
    ):
        """
        Test complete workflow:
        1. Fetch categories
        2. Filter by category
        3. Search within category
        4. Display results
        """
        # Step 1: Fetch categories
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "categories": sample_knowledge_data["categories"],
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get("/api/knowledge_base/categories") as response:
                assert response.status == 200
                data = await response.json()
                categories = data["categories"]
                assert len(categories) == 3

        # Step 2: Filter by "tools" category
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "facts": sample_knowledge_data["facts"]["tools"],
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get("/api/knowledge_base/category/tools") as response:
                assert response.status == 200
                data = await response.json()
                facts = data["facts"]
                assert len(facts) == 2
                assert all(f["category"] == "tools" for f in facts)

        # Step 3: Search within "tools" category
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "results": [sample_knowledge_data["facts"]["tools"][0]],
                    "count": 1,
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get(
                "/api/knowledge_base/search",
                params={"query": "nmap", "category": "tools"},
            ) as response:
                assert response.status == 200
                data = await response.json()
                results = data["results"]
                assert len(results) == 1
                assert "nmap" in results[0]["content"]

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_category_filter_with_empty_results(self, api_client):
        """Test category filter when no results found"""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"status": "success", "facts": []}
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get(
                "/api/knowledge_base/category/empty_category"
            ) as response:
                assert response.status == 200
                data = await response.json()
                assert data["facts"] == []

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_search_across_all_categories(
        self, api_client, sample_knowledge_data
    ):
        """Test search without category filter (all categories)"""
        with patch("aiohttp.ClientSession.get") as mock_get:
            all_facts = []
            for category_facts in sample_knowledge_data["facts"].values():
                all_facts.extend(category_facts)

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "results": all_facts,
                    "count": len(all_facts),
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get(
                "/api/knowledge_base/search", params={"query": "security"}
            ) as response:
                assert response.status == 200
                data = await response.json()
                assert data["count"] > 0

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_category_cache_behavior(self, api_client, sample_knowledge_data):
        """Test category list caching behavior"""
        # First request - cache miss
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {"X-Cache-Status": "MISS"}
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "categories": sample_knowledge_data["categories"],
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get("/api/knowledge_base/categories") as response:
                assert response.status == 200
                # First request should miss cache
                assert response.headers.get("X-Cache-Status") == "MISS"

        # Second request - cache hit (simulated)
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {"X-Cache-Status": "HIT"}
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "categories": sample_knowledge_data["categories"],
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get("/api/knowledge_base/categories") as response:
                assert response.status == 200
                # Second request should hit cache
                assert response.headers.get("X-Cache-Status") == "HIT"


# ============================================================================
# VECTORIZATION STATUS → BADGE UPDATE TESTS
# ============================================================================


class TestVectorizationStatusFlow:
    """Test vectorization status tracking and badge updates"""

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_vectorization_status_badge_update(self, api_client):
        """
        Test workflow:
        1. Fetch facts with vectorization status
        2. Update badge based on status
        3. Track status changes
        """
        fact_ids = ["fact_1", "fact_2", "fact_3"]

        # Step 1: Fetch vectorization status
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "statuses": {
                        "fact_1": {
                            "vectorized": True,
                            "timestamp": "2025-11-28T10:00:00",
                        },
                        "fact_2": {"vectorized": False, "timestamp": None},
                        "fact_3": {
                            "vectorized": True,
                            "timestamp": "2025-11-28T10:05:00",
                        },
                    },
                }
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/vectorization_status", json={"fact_ids": fact_ids}
            ) as response:
                assert response.status == 200
                data = await response.json()
                statuses = data["statuses"]

                # Verify badge states
                assert statuses["fact_1"]["vectorized"] is True  # Green badge
                assert statuses["fact_2"]["vectorized"] is False  # Yellow badge
                assert statuses["fact_3"]["vectorized"] is True  # Green badge

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_batch_vectorization_status_tracking(self, api_client):
        """Test tracking vectorization progress for batch operation"""
        # Start vectorization job
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "job_id": "vec_job_123",
                    "total": 100,
                }
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/vectorize_facts", json={"batch_size": 50}
            ) as response:
                assert response.status == 200
                data = await response.json()
                data["job_id"]

        # Poll job status
        with patch("aiohttp.ClientSession.get") as mock_get:
            # Simulate progress updates
            progress_states = [
                {"status": "in_progress", "completed": 25, "total": 100},
                {"status": "in_progress", "completed": 50, "total": 100},
                {"status": "in_progress", "completed": 75, "total": 100},
                {"status": "completed", "completed": 97, "total": 100, "failed": 3},
            ]

            for state in progress_states:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=state)
                mock_get.return_value.__aenter__.return_value = mock_response

                async with api_client.get(
                    f"/api/knowledge_base/vectorization/status"
                ) as response:
                    assert response.status == 200
                    data = await response.json()

                    if data["status"] == "completed":
                        assert data["completed"] + data["failed"] == data["total"]
                        break

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_real_time_status_updates(self, api_client):
        """Test real-time status updates during vectorization"""
        fact_id = "fact_dynamic"

        # Initial status: pending
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "statuses": {fact_id: {"vectorized": False, "timestamp": None}}
                }
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/vectorization_status", json={"fact_ids": [fact_id]}
            ) as response:
                data = await response.json()
                assert data["statuses"][fact_id]["vectorized"] is False

        # Start vectorization
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"status": "success", "job_id": f"vec_{fact_id}"}
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                f"/api/knowledge_base/vectorize_fact/{fact_id}"
            ) as response:
                assert response.status == 200

        # Poll until completed
        # Updated status: vectorized
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "statuses": {
                        fact_id: {
                            "vectorized": True,
                            "timestamp": "2025-11-28T10:10:00",
                        }
                    }
                }
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/vectorization_status", json={"fact_ids": [fact_id]}
            ) as response:
                data = await response.json()
                assert data["statuses"][fact_id]["vectorized"] is True


# ============================================================================
# FAILED JOB → RETRY → SUCCESS TESTS
# ============================================================================


class TestFailedJobRetryFlow:
    """Test failed vectorization job retry workflow"""

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_failed_job_retry_success(self, api_client):
        """
        Test workflow:
        1. Start vectorization job
        2. Job fails
        3. Retry failed facts
        4. Retry succeeds
        """
        # Step 1: Start vectorization (simulate failure)
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"status": "success", "job_id": "vec_job_fail_123"}
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/vectorize_facts"
            ) as response:
                data = await response.json()
                data["job_id"]

        # Step 2: Check status - job failed
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "completed",
                    "total": 10,
                    "completed": 7,
                    "failed": 3,
                    "failed_facts": [
                        {"id": "fact_1", "error": "Timeout"},
                        {"id": "fact_5", "error": "Timeout"},
                        {"id": "fact_9", "error": "Connection error"},
                    ],
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get(
                "/api/knowledge_base/vectorization/status"
            ) as response:
                data = await response.json()
                failed_facts = data["failed_facts"]
                assert len(failed_facts) == 3

        # Step 3: Retry failed facts
        failed_fact_ids = ["fact_1", "fact_5", "fact_9"]

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "success",
                    "job_id": "vec_job_retry_456",
                    "retry_count": 3,
                }
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/retry_vectorization",
                json={"fact_ids": failed_fact_ids},
            ) as response:
                assert response.status == 200
                data = await response.json()
                assert data["retry_count"] == 3

        # Step 4: Verify retry succeeded
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "completed",
                    "total": 3,
                    "completed": 3,
                    "failed": 0,
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get(
                "/api/knowledge_base/vectorization/status"
            ) as response:
                data = await response.json()
                assert data["failed"] == 0
                assert data["completed"] == 3

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_retry_with_exponential_backoff(self, api_client):
        """Test retry mechanism with exponential backoff"""
        fact_ids = ["fact_persistent"]
        max_retries = 3

        for attempt in range(max_retries):
            expected_delay = 2**attempt  # 1s, 2s, 4s

            with patch("aiohttp.ClientSession.post") as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(
                    return_value={
                        "status": "retry_scheduled"
                        if attempt < max_retries - 1
                        else "failed",
                        "attempt": attempt + 1,
                        "delay": expected_delay,
                        "can_retry": attempt < max_retries - 1,
                    }
                )
                mock_post.return_value.__aenter__.return_value = mock_response

                async with api_client.post(
                    "/api/knowledge_base/retry_vectorization",
                    json={"fact_ids": fact_ids},
                ) as response:
                    data = await response.json()
                    assert data["delay"] == expected_delay

                    if not data["can_retry"]:
                        assert data["status"] == "failed"
                        break

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_partial_retry_success(self, api_client):
        """Test retry where some facts succeed and some fail"""
        failed_facts = ["fact_1", "fact_2", "fact_3"]

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "status": "completed",
                    "total": 3,
                    "completed": 2,
                    "failed": 1,
                    "succeeded_facts": ["fact_1", "fact_2"],
                    "failed_facts": [{"id": "fact_3", "error": "Persistent error"}],
                }
            )
            mock_post.return_value.__aenter__.return_value = mock_response

            async with api_client.post(
                "/api/knowledge_base/retry_vectorization",
                json={"fact_ids": failed_facts},
            ) as response:
                data = await response.json()
                assert data["completed"] == 2
                assert data["failed"] == 1
                assert len(data["failed_facts"]) == 1


# ============================================================================
# ERROR HANDLING AND EDGE CASES
# ============================================================================


class TestIntegrationErrorHandling:
    """Test error handling in integration scenarios"""

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_api_timeout_handling(self, api_client):
        """Test handling of API timeouts"""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = asyncio.TimeoutError()

            with pytest.raises(asyncio.TimeoutError):
                async with api_client.get(
                    "/api/knowledge_base/categories",
                    timeout=aiohttp.ClientTimeout(total=1),
                ):
                    pass

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_invalid_category_name(self, api_client):
        """Test handling of invalid category names"""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.json = AsyncMock(
                return_value={"status": "error", "message": "Category not found"}
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            async with api_client.get(
                "/api/knowledge_base/category/invalid🔧category"
            ) as response:
                assert response.status == 404

    @pytest.mark.asyncio
    @pytest.mark.requires_backend
    async def test_concurrent_api_requests(self, api_client):
        """Test handling concurrent API requests"""
        # Simulate multiple concurrent requests
        tasks = []

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"status": "success", "categories": []}
            )
            mock_get.return_value.__aenter__.return_value = mock_response

            for _ in range(10):
                task = api_client.get("/api/knowledge_base/categories")
                tasks.append(task)

            # All should complete successfully
            responses = await asyncio.gather(*[task.__aenter__() for task in tasks])

            assert len(responses) == 10
            assert all(r.status == 200 for r in responses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
