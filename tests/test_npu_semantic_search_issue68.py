# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test NPU Semantic Search with Pre-computed Embeddings (Issue #68)

Tests:
1. EmbeddingCache integration
2. Batch search functionality
3. NPU-accelerated embedding generation
4. Performance metrics
"""

import asyncio
import time

from src.npu_semantic_search import get_npu_search_engine


async def test_embedding_cache():
    """Test that embedding cache is working"""
    print("\n=== Test 1: Embedding Cache ===")

    engine = await get_npu_search_engine()

    # First search - cache miss
    query = "authentication system"
    start = time.time()
    results1, metrics1 = await engine.enhanced_search(query, similarity_top_k=5)
    time1 = (time.time() - start) * 1000

    # Second search - should hit cache
    start = time.time()
    results2, metrics2 = await engine.enhanced_search(query, similarity_top_k=5)
    time2 = (time.time() - start) * 1000

    # Get cache stats
    stats = await engine.get_search_statistics()
    cache_stats = stats["embedding_cache_stats"]

    print(f"First search: {time1:.2f}ms (device: {metrics1.device_used})")
    print(f"Second search: {time2:.2f}ms (device: {metrics2.device_used})")
    print(f"Cache hit rate: {cache_stats['hit_rate_percent']}%")
    print(
        f"Speed improvement: {((time1 - time2) / time1 * 100):.1f}% faster on cached"
    )

    assert cache_stats["hits"] > 0, "Cache should have hits on repeated query"
    assert time2 < time1, "Cached query should be faster"
    print("✅ Embedding cache working correctly")


async def test_batch_search():
    """Test batch search functionality"""
    print("\n=== Test 2: Batch Search ===")

    engine = await get_npu_search_engine()

    queries = [
        "user authentication",
        "database connection",
        "API endpoint",
        "error handling",
        "logging configuration",
    ]

    start = time.time()
    batch_results = await engine.batch_search(queries, similarity_top_k=3)
    batch_time = (time.time() - start) * 1000

    print(f"Batch search ({len(queries)} queries): {batch_time:.2f}ms")
    print(
        f"Average per query: {batch_time / len(queries):.2f}ms"
    )

    for i, (results, metrics) in enumerate(batch_results):
        print(
            f"  Query {i+1}: {len(results)} results, {metrics.total_search_time_ms:.2f}ms"
        )

    assert len(batch_results) == len(queries), "Should return results for all queries"
    print("✅ Batch search working correctly")


async def test_performance_metrics():
    """Test that performance metrics are collected"""
    print("\n=== Test 3: Performance Metrics ===")

    engine = await get_npu_search_engine()

    results, metrics = await engine.enhanced_search(
        "configuration management", similarity_top_k=5
    )

    print(f"Total search time: {metrics.total_search_time_ms:.2f}ms")
    print(f"Embedding generation: {metrics.embedding_generation_time_ms:.2f}ms")
    print(f"Similarity computation: {metrics.similarity_computation_time_ms:.2f}ms")
    print(f"Device used: {metrics.device_used}")
    print(f"Results found: {metrics.total_documents_searched}")

    stats = await engine.get_search_statistics()
    print(f"\nCache stats:")
    print(f"  Embedding cache: {stats['embedding_cache_stats']}")
    print(f"  Search results cache: {stats['search_results_cache_stats']}")

    assert metrics.total_search_time_ms > 0, "Should have search time"
    assert metrics.device_used is not None, "Should record device used"
    print("✅ Performance metrics working correctly")


async def test_npu_acceleration():
    """Test NPU acceleration when available"""
    print("\n=== Test 4: NPU Acceleration ===")

    engine = await get_npu_search_engine()

    # Test with NPU acceleration enabled
    results_npu, metrics_npu = await engine.enhanced_search(
        "machine learning model", similarity_top_k=5, enable_npu_acceleration=True
    )

    # Test with NPU acceleration disabled (CPU fallback)
    results_cpu, metrics_cpu = await engine.enhanced_search(
        "machine learning model", similarity_top_k=5, enable_npu_acceleration=False
    )

    print(f"NPU-enabled search: {metrics_npu.total_search_time_ms:.2f}ms")
    print(f"  Device: {metrics_npu.device_used}")
    print(f"CPU fallback search: {metrics_cpu.total_search_time_ms:.2f}ms")
    print(f"  Device: {metrics_cpu.device_used}")

    if metrics_npu.device_used not in ["cached", "cpu_fallback"]:
        speedup = metrics_cpu.total_search_time_ms / metrics_npu.total_search_time_ms
        print(f"NPU speedup: {speedup:.2f}x faster than CPU")

    print("✅ NPU acceleration tested")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("NPU Semantic Search with Pre-computed Embeddings (Issue #68)")
    print("=" * 60)

    try:
        await test_embedding_cache()
        await test_batch_search()
        await test_performance_metrics()
        await test_npu_acceleration()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
