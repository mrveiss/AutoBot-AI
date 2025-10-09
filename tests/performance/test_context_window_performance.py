"""
Performance benchmarks for Context Window Configuration
Measures efficiency improvements and system overhead
"""

import pytest
import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.context_window_manager import ContextWindowManager
from backend.utils.async_redis_manager import get_redis_manager


@pytest.mark.asyncio
class TestContextWindowPerformance:
    """Performance benchmarks for context window management"""

    async def test_config_load_time(self):
        """Test that config loading is fast"""
        start = time.time()
        context_mgr = ContextWindowManager()
        load_time = time.time() - start

        assert load_time < 0.1, f"Config load too slow: {load_time:.3f}s (should be <0.1s)"
        print(f"✅ Config load time: {load_time*1000:.2f}ms")

    async def test_message_limit_lookup_speed(self):
        """Test that message limit lookup is instant"""
        context_mgr = ContextWindowManager()

        # Warm up
        context_mgr.get_message_limit()

        # Benchmark 1000 lookups
        start = time.time()
        for _ in range(1000):
            context_mgr.get_message_limit()
        duration = time.time() - start

        avg_time_us = (duration / 1000) * 1000000
        assert avg_time_us < 100, f"Lookup too slow: {avg_time_us:.2f}μs (should be <100μs)"
        print(f"✅ Average lookup time: {avg_time_us:.2f}μs per call")

    async def test_redis_fetch_efficiency_improvement(self):
        """Benchmark efficiency improvement vs old hardcoded approach"""

        # OLD APPROACH: Fetch 500, use 200
        old_fetch = 500
        old_use = 200
        old_waste = old_fetch - old_use
        old_waste_pct = (old_waste / old_fetch) * 100

        # NEW APPROACH: Model-aware fetching
        context_mgr = ContextWindowManager()
        new_fetch = context_mgr.calculate_retrieval_limit()  # 40
        new_use = context_mgr.get_message_limit()  # 20
        new_waste = new_fetch - new_use
        new_waste_pct = (new_waste / new_fetch) * 100

        # Calculate improvement
        fetch_reduction = ((old_fetch - new_fetch) / old_fetch) * 100

        print(f"\n📊 Efficiency Comparison:")
        print(f"  OLD: Fetch {old_fetch}, use {old_use}, waste {old_waste} ({old_waste_pct:.1f}%)")
        print(f"  NEW: Fetch {new_fetch}, use {new_use}, waste {new_waste} ({new_waste_pct:.1f}%)")
        print(f"  ✅ Fetch reduction: {fetch_reduction:.1f}%")

        assert fetch_reduction >= 90, f"Expected >= 90% improvement, got {fetch_reduction:.1f}%"

    async def test_model_switching_overhead(self):
        """Test that model switching is negligible overhead"""
        context_mgr = ContextWindowManager()

        models = [
            "qwen2.5-coder-7b-instruct",
            "qwen2.5-coder-14b-instruct",
            "llama-3.2-3b-instruct",
            "phi-3-mini-4k-instruct"
        ]

        # Benchmark 100 model switches
        start = time.time()
        for _ in range(100):
            for model in models:
                context_mgr.set_model(model)
                context_mgr.get_message_limit()
        duration = time.time() - start

        avg_time_ms = (duration / (100 * len(models))) * 1000

        assert avg_time_ms < 1, f"Model switching too slow: {avg_time_ms:.3f}ms (should be <1ms)"
        print(f"✅ Model switch + lookup: {avg_time_ms:.3f}ms per operation")

    async def test_token_estimation_speed(self):
        """Test token estimation performance"""
        context_mgr = ContextWindowManager()

        # Create test text of various sizes
        test_texts = [
            "Short text",
            "Medium " * 100,
            "Long " * 1000,
            "Very long " * 10000
        ]

        for text in test_texts:
            start = time.time()
            for _ in range(100):
                context_mgr.estimate_tokens(text)
            duration = time.time() - start

            avg_time_us = (duration / 100) * 1000000
            text_len = len(text)

            # Should be < 100μs regardless of text size (simple division)
            assert avg_time_us < 100, f"Estimation too slow for {text_len} chars: {avg_time_us:.2f}μs"

        print(f"✅ Token estimation: <100μs for all text sizes")

    async def test_memory_footprint(self):
        """Test that ContextWindowManager has minimal memory footprint"""
        import sys

        # Measure size of context manager
        context_mgr = ContextWindowManager()
        size_bytes = sys.getsizeof(context_mgr)

        # Should be < 10KB
        assert size_bytes < 10240, f"Memory footprint too large: {size_bytes} bytes"
        print(f"✅ Memory footprint: {size_bytes} bytes (~{size_bytes/1024:.2f}KB)")

    async def test_concurrent_access_performance(self):
        """Test performance under concurrent access"""
        context_mgr = ContextWindowManager()

        async def concurrent_lookup():
            """Simulate concurrent request"""
            context_mgr.set_model("qwen2.5-coder-7b-instruct")
            limit = context_mgr.get_message_limit()
            return limit

        # 50 concurrent requests
        start = time.time()
        results = await asyncio.gather(*[concurrent_lookup() for _ in range(50)])
        duration = time.time() - start

        assert all(r == 20 for r in results), "All concurrent lookups should return same value"
        assert duration < 0.1, f"Concurrent access too slow: {duration:.3f}s (should be <0.1s)"

        print(f"✅ 50 concurrent requests: {duration*1000:.2f}ms total ({duration*1000/50:.2f}ms per request)")


@pytest.mark.asyncio
class TestRealWorldScenarios:
    """Real-world usage scenario tests"""

    async def test_typical_chat_session_performance(self):
        """Simulate typical chat session with context management"""
        context_mgr = ContextWindowManager()

        # Simulate 10 chat turns
        start = time.time()
        for turn in range(10):
            # Model might change per request
            model = "qwen2.5-coder-7b-instruct" if turn % 2 == 0 else "qwen2.5-coder-14b-instruct"
            context_mgr.set_model(model)

            # Get limits
            retrieval_limit = context_mgr.calculate_retrieval_limit()
            message_limit = context_mgr.get_message_limit()

            # Simulate message truncation check
            messages = [{"content": "test"} for _ in range(message_limit)]
            needs_truncation = context_mgr.should_truncate_history(messages)

        duration = time.time() - start
        avg_per_turn = (duration / 10) * 1000

        assert avg_per_turn < 5, f"Per-turn overhead too high: {avg_per_turn:.2f}ms"
        print(f"✅ Typical chat session (10 turns): {duration*1000:.2f}ms total ({avg_per_turn:.2f}ms per turn)")

    async def test_high_load_simulation(self):
        """Simulate high load scenario"""
        context_mgr = ContextWindowManager()

        # 1000 rapid-fire requests
        start = time.time()
        for _ in range(1000):
            context_mgr.get_message_limit()
            context_mgr.calculate_retrieval_limit()
        duration = time.time() - start

        requests_per_sec = 1000 / duration

        assert requests_per_sec > 10000, f"Throughput too low: {requests_per_sec:.0f} req/s"
        print(f"✅ High load performance: {requests_per_sec:.0f} requests/second")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
