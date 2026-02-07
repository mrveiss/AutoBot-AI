"""
API Endpoint Performance Benchmarks

Benchmark tests for AutoBot REST API endpoints measuring
response times, throughput, and scalability.

Issue #58 - Performance Benchmarking Suite
Author: mrveiss
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants.network_constants import NetworkConstants
from tests.benchmarks.benchmark_base import BenchmarkRunner, assert_performance

# Build URLs from centralized configuration
BASE_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


class TestAPIEndpointBenchmarks:
    """Benchmark tests for API endpoints"""

    @pytest.fixture
    def runner(self):
        """Create benchmark runner"""
        return BenchmarkRunner(warmup_iterations=2, default_iterations=10)

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock HTTP client for benchmarking without actual network calls"""
        with patch("httpx.AsyncClient") as mock:
            client_instance = AsyncMock()
            mock.return_value.__aenter__.return_value = client_instance

            # Configure mock responses
            health_response = AsyncMock()
            health_response.json.return_value = {"status": "healthy", "uptime": 1000}
            health_response.status_code = 200

            client_instance.get.return_value = health_response
            client_instance.post.return_value = health_response

            yield client_instance

    @pytest.mark.asyncio
    async def test_health_endpoint_benchmark(self, runner, mock_httpx_client):
        """Benchmark health check endpoint performance"""
        import httpx

        async def health_check():
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BASE_URL}/api/health")
                return response.json()

        result = await runner.run_async_benchmark(
            name="api_health_endpoint",
            func=health_check,
            iterations=20,
            metadata={"endpoint": "/api/health", "method": "GET"},
        )

        print("\nHealth Endpoint Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # Health checks should be very fast (< 100ms avg for mock)
        assert_performance(result, max_avg_ms=100, max_p95_ms=200)

    @pytest.mark.asyncio
    async def test_chat_endpoint_benchmark(self, runner, mock_httpx_client):
        """Benchmark chat message processing endpoint"""
        import httpx

        async def send_chat():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{BASE_URL}/api/chat/message",
                    json={"message": "Test message", "session_id": "bench_001"},
                )
                return response.json()

        result = await runner.run_async_benchmark(
            name="api_chat_endpoint",
            func=send_chat,
            iterations=15,
            metadata={"endpoint": "/api/chat/message", "method": "POST"},
        )

        print("\nChat Endpoint Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed

    @pytest.mark.asyncio
    async def test_mcp_tools_list_benchmark(self, runner, mock_httpx_client):
        """Benchmark MCP tools listing endpoint"""
        import httpx

        async def list_tools():
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BASE_URL}/api/mcp/tools")
                return response.json()

        result = await runner.run_async_benchmark(
            name="api_mcp_tools_list",
            func=list_tools,
            iterations=20,
            metadata={"endpoint": "/api/mcp/tools", "method": "GET"},
        )

        print("\nMCP Tools List Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")

        assert result.passed

    @pytest.mark.asyncio
    async def test_knowledge_search_benchmark(self, runner, mock_httpx_client):
        """Benchmark knowledge base search endpoint"""
        import httpx

        async def search_knowledge():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{BASE_URL}/api/knowledge/query",
                    json={"query": "test query", "top_k": 5},
                )
                return response.json()

        result = await runner.run_async_benchmark(
            name="api_knowledge_search",
            func=search_knowledge,
            iterations=10,
            metadata={"endpoint": "/api/knowledge/query", "method": "POST", "top_k": 5},
        )

        print("\nKnowledge Search Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")

        assert result.passed

    @pytest.mark.asyncio
    async def test_concurrent_requests_benchmark(self, runner, mock_httpx_client):
        """Benchmark concurrent request handling"""
        import httpx

        async def concurrent_health_checks():
            async with httpx.AsyncClient() as client:
                tasks = [client.get(f"{BASE_URL}/api/health") for _ in range(5)]
                responses = await asyncio.gather(*tasks)
                return [r.json() for r in responses]

        result = await runner.run_async_benchmark(
            name="api_concurrent_requests",
            func=concurrent_health_checks,
            iterations=10,
            metadata={"concurrent_requests": 5, "endpoint": "/api/health"},
        )

        print("\nConcurrent Requests Benchmark (5 concurrent):")
        print(f"  Avg: {result.avg_time_ms:.2f}ms")
        print(f"  P95: {result.p95_time_ms:.2f}ms")

        assert result.passed

    def test_json_serialization_benchmark(self, runner):
        """Benchmark JSON serialization performance"""
        import json

        test_data = {
            "agents": [
                {"id": f"agent_{i}", "status": "active", "tasks": [1, 2, 3]}
                for i in range(100)
            ],
            "metrics": {"cpu": 45.2, "memory": 67.8, "requests": 1000},
            "config": {"debug": False, "log_level": "INFO", "max_workers": 4},
        }

        def serialize():
            return json.dumps(test_data)

        result = runner.run_benchmark(
            name="json_serialization_100_agents",
            func=serialize,
            iterations=100,
            metadata={"data_size": "100 agents"},
        )

        print("\nJSON Serialization Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # JSON serialization should be very fast
        assert_performance(result, max_avg_ms=1.0, min_ops_per_second=1000)

    def test_json_deserialization_benchmark(self, runner):
        """Benchmark JSON deserialization performance"""
        import json

        test_json = json.dumps(
            {
                "agents": [
                    {"id": f"agent_{i}", "status": "active", "tasks": [1, 2, 3]}
                    for i in range(100)
                ],
                "metrics": {"cpu": 45.2, "memory": 67.8, "requests": 1000},
            }
        )

        def deserialize():
            return json.loads(test_json)

        result = runner.run_benchmark(
            name="json_deserialization_100_agents",
            func=deserialize,
            iterations=100,
            metadata={"data_size": "100 agents"},
        )

        print("\nJSON Deserialization Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        assert_performance(result, max_avg_ms=1.0, min_ops_per_second=1000)


class TestAPIResponseTimeBenchmarks:
    """Test API response time requirements"""

    @pytest.fixture
    def runner(self):
        return BenchmarkRunner()

    def test_pydantic_validation_benchmark(self, runner):
        """Benchmark Pydantic model validation"""
        from typing import List, Optional

        from pydantic import BaseModel

        class AgentModel(BaseModel):
            id: str
            name: str
            status: str
            tasks: List[int]
            metadata: Optional[dict] = None

        test_data = {
            "id": "agent_001",
            "name": "Test Agent",
            "status": "active",
            "tasks": [1, 2, 3, 4, 5],
            "metadata": {"created": "2025-01-01"},
        }

        def validate():
            return AgentModel(**test_data)

        result = runner.run_benchmark(
            name="pydantic_model_validation",
            func=validate,
            iterations=100,
            metadata={"model": "AgentModel"},
        )

        print("\nPydantic Validation Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.4f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # Pydantic validation should be fast
        assert_performance(result, max_avg_ms=0.5, min_ops_per_second=2000)

    def test_uuid_generation_benchmark(self, runner):
        """Benchmark UUID generation performance"""
        import uuid

        def generate_uuid():
            return str(uuid.uuid4())

        result = runner.run_benchmark(
            name="uuid_generation",
            func=generate_uuid,
            iterations=1000,
            metadata={"type": "uuid4"},
        )

        print("\nUUID Generation Benchmark:")
        print(f"  Avg: {result.avg_time_ms:.6f}ms")
        print(f"  Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        # UUID generation is very fast
        assert_performance(result, max_avg_ms=0.1, min_ops_per_second=10000)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
