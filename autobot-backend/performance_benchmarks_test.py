# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Performance Benchmarking Tests

Comprehensive performance tests for AutoBot components to identify
bottlenecks, measure response times, and validate system performance
under various load conditions.
"""

import asyncio
import shutil
import statistics
import tempfile
import threading
import time
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import psutil
import pytest

from knowledge import KnowledgeBase
from memory import MemoryManager
from memory.enums import MemoryCategory

# Import components to benchmark
from orchestrator import Orchestrator
from services.llm_service import LLMService

# #13162: every test in this module asserts a wall-clock budget
# (``avg_duration``/``total_time``) or an RSS delta — there is not one
# functional-only test here. That makes the module a benchmark suite, so it
# belongs to the ``performance`` selection rather than the unit selection,
# where wall-clock budgets measure the CI runner's contention instead of the
# code. The budgets themselves are unchanged.
pytestmark = pytest.mark.performance


class PerformanceBenchmark:
    """Base class for performance benchmarking utilities"""

    def __init__(self):
        self.metrics = []
        self.start_time = None
        self.end_time = None

    def start_measurement(self):
        """Start performance measurement"""
        self.start_time = time.perf_counter()

    def end_measurement(self):
        """End performance measurement and record metrics"""
        self.end_time = time.perf_counter()
        duration = self.end_time - self.start_time
        self.metrics.append(
            {
                "duration": duration,
                "timestamp": time.time(),
                "memory_usage": psutil.Process().memory_info().rss / 1024 / 1024,  # MB
                "cpu_percent": psutil.Process().cpu_percent(),
            }
        )
        return duration

    def get_statistics(self) -> Dict[str, float]:
        """Get performance statistics"""
        if not self.metrics:
            return {}

        durations = [m["duration"] for m in self.metrics]
        memory_usage = [m["memory_usage"] for m in self.metrics]

        return {
            "avg_duration": statistics.mean(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "median_duration": statistics.median(durations),
            "stdev_duration": statistics.stdev(durations) if len(durations) > 1 else 0,
            "avg_memory_mb": statistics.mean(memory_usage),
            "max_memory_mb": max(memory_usage),
            "total_requests": len(self.metrics),
        }


class TestLLMServicePerformance:
    """Performance tests for LLM Service.

    Renamed from TestLLMInterfacePerformance after #3185 retired LLMInterface.
    LLMService initializes from a ProviderRegistry rather than the legacy
    `global_config_manager`, so the prior `with patch(...)` config-mock
    setup is no longer applicable — LLMService instantiates bare.
    """

    def setup_method(self):
        """Set up test environment"""
        self.benchmark = PerformanceBenchmark()
        self.llm = LLMService()

    async def test_llm_response_time_benchmark(self):
        """Benchmark LLM response times with various prompt lengths"""
        prompts = [
            "Hello",  # Short prompt
            "Explain the concept of artificial intelligence in detail.",  # Medium prompt
            "Write a comprehensive analysis of the impact of artificial intelligence on modern society, including economic, social, and ethical considerations. Discuss both benefits and potential risks."
            * 2,  # Long prompt
        ]

        results = {}

        for i, prompt in enumerate(prompts):
            self.benchmark.metrics = []  # Reset for each test

            # Run multiple iterations for statistical significance
            for _ in range(5):
                self.benchmark.start_measurement()

                # Mock LLMService.chat at the public surface — internal
                # ProviderRegistry routing is out of scope for this benchmark.
                # #13162: chat() is a coroutine function, so the double must be
                # an AsyncMock — a MagicMock returns a value that cannot be
                # awaited.
                with patch.object(self.llm, "chat", new_callable=AsyncMock) as mock_chat:
                    mock_chat.return_value = MagicMock(
                        content=f"Mock response for prompt {i}",
                        error=None,
                        model="llama3.2:1b",
                    )

                    response = await self.llm.chat(messages=[{"role": "user", "content": prompt}])

                self.benchmark.end_measurement()

                # Verify response shape
                assert response is not None
                assert response.content

            stats = self.benchmark.get_statistics()
            results[f"prompt_length_{len(prompt)}"] = stats

            # Performance assertions
            assert stats["avg_duration"] < 2.0, f"LLM response too slow for prompt length {len(prompt)}"
            assert stats["max_memory_mb"] < 500, "Memory usage too high"

        # Log results for analysis
        print("\nLLM Performance Results:")  # noqa: print
        for prompt_type, stats in results.items():
            print(f"{prompt_type}: {stats['avg_duration']:.3f}s avg, {stats['max_duration']:.3f}s max")  # noqa: print

    async def test_concurrent_llm_requests(self):
        """Test LLM performance under concurrent load"""
        concurrent_requests = [5, 10, 20]

        for num_requests in concurrent_requests:
            self.benchmark.metrics = []

            async def make_request():
                self.benchmark.start_measurement()

                with patch.object(self.llm, "chat", new_callable=AsyncMock) as mock_chat:
                    mock_chat.return_value = MagicMock(
                        content="Concurrent mock response",
                        error=None,
                        model="llama3.2:1b",
                    )

                    response = await self.llm.chat(messages=[{"role": "user", "content": "Test concurrent request"}])

                self.benchmark.end_measurement()
                return response

            # Execute concurrent requests
            start_time = time.perf_counter()
            tasks = [make_request() for _ in range(num_requests)]
            responses = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_time

            # Verify all requests completed
            assert len(responses) == num_requests
            assert all(r is not None for r in responses)

            stats = self.benchmark.get_statistics()

            # Performance assertions
            assert total_time < 10.0, f"Concurrent requests took too long: {total_time}s"
            assert stats["avg_duration"] < 5.0, "Individual request time too high under load"

            print(  # noqa: print
                f"\nConcurrent {num_requests} requests: {total_time:.3f}s total, {stats['avg_duration']:.3f}s avg per request"
            )


class TestKnowledgeBasePerformance:
    """Performance tests for Knowledge Base operations"""

    def setup_method(self):
        """Set up test environment"""
        self.benchmark = PerformanceBenchmark()

        # #13112: `KnowledgeBase()` takes no config args and no longer exposes
        # a `global_config_manager` symbol to patch. `__init__` reads from the
        # module-level `knowledge.base.config` singleton via plain
        # `config.get("dotted.key", default)` calls (never `get_redis_config`/
        # `get_llm_config`, which this fixture used to mock) with safe
        # defaults, so bare construction is sufficient — same pattern already
        # exercised by `dependency_injection_test.py::test_knowledge_base_backward_compatibility`.
        self.kb = KnowledgeBase()

    async def test_knowledge_base_search_performance(self):
        """Benchmark knowledge base search operations"""
        # #13162: KnowledgeBase no longer carries a LlamaIndex `index`
        # attribute, so `patch.object(self.kb, "index")` raised AttributeError.
        # The retrieval backend is now reached through
        # `knowledge.search.get_vector_search_engine()`; mocking that is the
        # direct successor of the old index mock and keeps the benchmark
        # measuring the KB's own dispatch (validation, prompt-injection
        # sanitizing, result conversion) rather than a live vector store.
        mock_engine = AsyncMock()
        mock_engine.search.return_value = []

        # `initialized` is what `initialize()` flips once the backing stores are
        # wired; the stores are exactly what the mocked engine stands in for,
        # so the benchmark declares the KB up rather than dialing Redis/Chroma.
        with (
            patch(
                "knowledge.search.get_vector_search_engine",
                new_callable=AsyncMock,
                return_value=mock_engine,
            ),
            patch.object(self.kb, "initialized", True),
        ):
            search_queries = [
                "simple query",
                "more complex search query with multiple terms",
                "very detailed and comprehensive search query that contains many specific terms and concepts that might be present in the knowledge base",
            ]

            for query in search_queries:
                self.benchmark.metrics = []

                # Run multiple searches for statistical analysis
                for _ in range(10):
                    self.benchmark.start_measurement()

                    # top_k (not limit) keeps this on the basic vector path,
                    # which is the path the mocked engine serves.
                    results = await self.kb.search(query, top_k=5)

                    self.benchmark.end_measurement()

                    # Verify search results
                    assert isinstance(results, list)

                stats = self.benchmark.get_statistics()

                # Performance assertions
                assert stats["avg_duration"] < 1.0, f"Search too slow for query: {query[:50]}..."
                assert stats["max_duration"] < 2.0, "Maximum search time exceeded"

                print(f"\nKB Search '{query[:30]}...': {stats['avg_duration']:.3f}s avg")  # noqa: print

    async def test_knowledge_base_indexing_performance(self):
        """Benchmark knowledge base document indexing"""
        documents = [
            {"content": "Short document", "metadata": {"type": "test"}},
            {
                "content": "Medium length document with more content to index and process" * 5,
                "metadata": {"type": "test"},
            },
            {
                "content": "Very long document with extensive content that will test the indexing performance under larger document sizes"
                * 20,
                "metadata": {"type": "test"},
            },
        ]

        # #13162: `index.insert_documents` is gone with the LlamaIndex index.
        # `add_document()` now persists through `store_fact()`, so that is the
        # seam the benchmark mocks — the measured span stays the KB's own
        # provenance-defaulting and timeout wrapper.
        with patch.object(self.kb, "store_fact", new_callable=AsyncMock) as mock_store_fact:
            mock_store_fact.return_value = {"status": "success", "doc_id": "bench"}

            for i, doc in enumerate(documents):
                self.benchmark.metrics = []

                # Test indexing performance
                for _ in range(3):  # Fewer iterations for indexing
                    self.benchmark.start_measurement()

                    await self.kb.add_document(doc["content"], doc["metadata"])

                    self.benchmark.end_measurement()

                stats = self.benchmark.get_statistics()

                # Performance assertions
                assert stats["avg_duration"] < 5.0, f"Indexing too slow for document {i}"

                print(  # noqa: print
                    f"\nIndexing doc {i} ({len(doc['content'])} chars): {stats['avg_duration']:.3f}s avg"
                )


class TestOrchestratorPerformance:
    """Performance tests for Orchestrator operations"""

    def setup_method(self):
        """Set up test environment"""
        self.benchmark = PerformanceBenchmark()

        with patch("orchestrator.config_manager") as mock_config:
            mock_config.get_llm_config.return_value = {"orchestrator_llm": "llama3.2:1b"}
            self.orchestrator = Orchestrator()

    async def test_orchestrator_task_planning_performance(self):
        """Benchmark orchestrator task planning operations"""
        test_requests = [
            "List files in current directory",
            "Find all Python files and check their syntax",
            "Research network security tools, evaluate them, and provide installation recommendations with approval workflow",
        ]

        with patch.object(self.orchestrator, "llm_service") as mock_llm:
            # #13162: llm_service.chat is awaited by the orchestrator, so the
            # double must be an AsyncMock.
            mock_llm.chat = AsyncMock(return_value=MagicMock(content="Mock orchestrator response", error=None))

            for request in test_requests:
                self.benchmark.metrics = []

                for _ in range(5):
                    self.benchmark.start_measurement()

                    # #13162: both planning entry points are coroutine
                    # functions; without await the benchmark measured only how
                    # long it takes to build a coroutine object.
                    complexity = await self.orchestrator.classify_request_complexity(request)
                    steps = await self.orchestrator.plan_workflow_steps(request, complexity)

                    self.benchmark.end_measurement()

                    # Verify planning results
                    assert complexity is not None
                    assert isinstance(steps, list)

                stats = self.benchmark.get_statistics()

                # Performance assertions
                assert stats["avg_duration"] < 3.0, f"Task planning too slow for: {request[:50]}..."

                print(f"\nTask planning '{request[:40]}...': {stats['avg_duration']:.3f}s avg")  # noqa: print

    async def test_orchestrator_concurrent_workflows(self):
        """Test orchestrator performance with concurrent workflows"""
        concurrent_counts = [3, 5, 10]

        for count in concurrent_counts:
            self.benchmark.metrics = []

            async def run_workflow():
                self.benchmark.start_measurement()

                with patch.object(self.orchestrator, "llm_service") as mock_llm:
                    mock_llm.chat = AsyncMock(return_value=MagicMock(content="Mock response", error=None))

                    request = f"Test concurrent workflow {threading.current_thread().ident}"
                    complexity = await self.orchestrator.classify_request_complexity(request)
                    steps = await self.orchestrator.plan_workflow_steps(request, complexity)

                self.benchmark.end_measurement()
                return len(steps)

            # Run concurrent workflows
            start_time = time.perf_counter()
            tasks = [run_workflow() for _ in range(count)]
            results = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_time

            # Verify all workflows completed
            assert len(results) == count
            assert all(isinstance(r, int) for r in results)

            self.benchmark.get_statistics()

            # Performance assertions
            assert total_time < 15.0, f"Concurrent workflows took too long: {total_time}s"

            print(f"\nConcurrent {count} workflows: {total_time:.3f}s total")  # noqa: print  # noqa: print


class TestMemorySystemPerformance:
    """Performance tests for Enhanced Memory Manager"""

    def setup_method(self):
        """Set up test environment"""
        self.benchmark = PerformanceBenchmark()

        # #13162: point the benchmark at a throwaway SQLite file. The default
        # db_path is the repo-relative data/unified_memory.db, so the previous
        # form would have written 65 benchmark rows into the working tree.
        self._db_dir = tempfile.mkdtemp(prefix="autobot-memory-benchmark-")
        self.memory_manager = MemoryManager(db_path=f"{self._db_dir}/unified_memory.db")

    def teardown_method(self):
        """Remove the throwaway memory database"""
        shutil.rmtree(self._db_dir, ignore_errors=True)

    async def test_memory_storage_performance(self):
        """Benchmark memory storage operations"""
        # #13162: store_memory() takes (category, content, metadata, ...) — the
        # `memory_type`/`context` keywords it was called with never existed on
        # this signature. Category is a MemoryCategory; the free-form context
        # travels in metadata, which is where the storage layer keeps it.
        memory_entries = [
            {"content": "Short memory", "context": "test"},
            {
                "content": "Medium length memory entry with more context" * 3,
                "context": "test",
            },
            {
                "content": "Very long memory entry with extensive context and details" * 10,
                "context": "test",
            },
        ]

        for i, entry in enumerate(memory_entries):
            self.benchmark.metrics = []

            for _ in range(5):
                self.benchmark.start_measurement()

                await self.memory_manager.store_memory(
                    category=MemoryCategory.EXECUTION,
                    content=entry["content"],
                    metadata={"test_id": i, "context": entry["context"]},
                )

                self.benchmark.end_measurement()

            stats = self.benchmark.get_statistics()

            # Performance assertions
            assert stats["avg_duration"] < 1.0, f"Memory storage too slow for entry {i}"

            print(  # noqa: print
                f"\nMemory storage {i} ({len(entry['content'])} chars): {stats['avg_duration']:.3f}s avg"
            )

    async def test_memory_retrieval_performance(self):
        """Benchmark memory retrieval operations"""
        # #13162: retrieve_memories() selects by category (plus optional date /
        # reference_path filters) — it has no `query` parameter and never did
        # on this signature. Store across three categories, then benchmark a
        # read of each.
        categories = [
            MemoryCategory.EXECUTION,
            MemoryCategory.STATE,
            MemoryCategory.FACT,
        ]

        # First, store some test memories
        for i in range(50):
            await self.memory_manager.store_memory(
                category=categories[i % len(categories)],
                content=f"Test memory {i}",
                metadata={"test_id": i, "context": "performance_test"},
            )

        for category in categories:
            self.benchmark.metrics = []

            for _ in range(10):
                self.benchmark.start_measurement()

                results = await self.memory_manager.retrieve_memories(category=category, limit=10)

                self.benchmark.end_measurement()

                # Verify retrieval results
                assert isinstance(results, list)
                assert results, f"No memories retrieved for category {category.value}"

            stats = self.benchmark.get_statistics()

            # Performance assertions
            assert stats["avg_duration"] < 1.0, f"Memory retrieval too slow for: {category.value}"

            print(f"\nMemory retrieval '{category.value}': {stats['avg_duration']:.3f}s avg")  # noqa: print


class TestSystemIntegrationPerformance:
    """Performance tests for system integration scenarios"""

    def setup_method(self):
        """Set up test environment"""
        self.benchmark = PerformanceBenchmark()

    async def test_end_to_end_workflow_performance(self):
        """Benchmark complete end-to-end workflow performance"""
        # Mock all major components
        with (
            patch("orchestrator.Orchestrator") as mock_orchestrator_class,
            patch("knowledge_base.KnowledgeBase") as mock_kb_class,
            patch("memory.manager.MemoryManager") as mock_memory_class,
        ):
            # Set up mocks. #13162: the workflow awaits every one of these
            # calls, so the doubles must be AsyncMocks — a MagicMock hands back
            # a plain dict/list that cannot be awaited.
            mock_orchestrator = AsyncMock()
            mock_kb = AsyncMock()
            mock_memory = AsyncMock()

            mock_orchestrator_class.return_value = mock_orchestrator
            mock_kb_class.return_value = mock_kb
            mock_memory_class.return_value = mock_memory

            # Mock responses
            mock_orchestrator.process_request.return_value = {
                "status": "completed",
                "response": "Mock workflow completed",
                "steps": [{"action": "test", "result": "success"}],
            }
            mock_kb.search.return_value = [{"content": "Mock search result"}]
            mock_memory.store_memory.return_value = True

            # Test workflows of varying complexity
            workflows = [
                "Simple echo command",
                "Search knowledge base and process results",
                "Complex multi-step workflow with research, analysis, and system commands",
            ]

            for workflow in workflows:
                self.benchmark.metrics = []

                for _ in range(3):  # Fewer iterations for integration tests
                    self.benchmark.start_measurement()

                    # Simulate end-to-end workflow
                    result = await mock_orchestrator.process_request(workflow)
                    search_results = await mock_kb.search(workflow)
                    memory_stored = await mock_memory.store_memory(
                        content=workflow,
                        memory_type="episodic",
                        context="integration_test",
                    )

                    self.benchmark.end_measurement()

                    # Verify integration results
                    assert result["status"] == "completed"
                    assert isinstance(search_results, list)
                    assert memory_stored

                stats = self.benchmark.get_statistics()

                # Performance assertions
                assert stats["avg_duration"] < 5.0, f"Integration workflow too slow: {workflow[:50]}..."

                print(f"\nIntegration '{workflow[:40]}...': {stats['avg_duration']:.3f}s avg")  # noqa: print

    async def test_resource_usage_under_load(self):
        """Test system resource usage under sustained load"""
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        psutil.Process().cpu_percent()

        # Simulate sustained load
        async def simulate_load():
            with patch("asyncio.sleep"):  # Speed up for testing
                for _ in range(10):
                    # Simulate various operations
                    await asyncio.sleep(0.01)  # Minimal delay

        # Run multiple concurrent load simulations
        tasks = [simulate_load() for _ in range(20)]

        start_time = time.perf_counter()
        await asyncio.gather(*tasks)
        end_time = time.perf_counter()

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        psutil.Process().cpu_percent()

        # Resource usage assertions
        memory_increase = final_memory - initial_memory
        assert memory_increase < 100, f"Memory usage increased too much: {memory_increase}MB"

        total_time = end_time - start_time
        assert total_time < 10.0, f"Load test took too long: {total_time}s"

        print(f"\nLoad test: {total_time:.3f}s, Memory: {initial_memory:.1f}MB -> {final_memory:.1f}MB")  # noqa: print


if __name__ == "__main__":
    # Run performance benchmarks
    pytest.main([__file__, "-v", "-s"])  # -s to show print statements
