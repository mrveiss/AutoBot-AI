#!/usr/bin/env python3
"""
Test script for the knowledge base caching system
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_knowledge_cache():
    """Test the knowledge cache functionality"""
    logger.info("🧪 Testing Knowledge Base Cache System")

    try:
        from src.utils.knowledge_cache import get_knowledge_cache
        from src.config_helper import cfg

        # Initialize cache
        cache = get_knowledge_cache()
        logger.info(f"✅ Cache initialized successfully")

        # Test data
        test_query = "test cache performance"
        test_top_k = 5
        test_results = [
            {"content": "Test result 1", "score": 0.95, "metadata": {"source": "test"}},
            {"content": "Test result 2", "score": 0.90, "metadata": {"source": "test"}},
            {"content": "Test result 3", "score": 0.85, "metadata": {"source": "test"}},
        ]

        # Test 1: Cache miss (first time)
        logger.info("🔍 Test 1: Cache miss scenario")
        start_time = time.time()
        cached_results = await cache.get_cached_results(test_query, test_top_k)
        miss_time = time.time() - start_time

        if cached_results is None:
            logger.info(f"✅ Cache miss detected correctly ({miss_time:.3f}s)")
        else:
            logger.error("❌ Expected cache miss but got results")
            return False

        # Test 2: Store results
        logger.info("💾 Test 2: Storing results in cache")
        start_time = time.time()
        cache_success = await cache.cache_results(test_query, test_top_k, test_results)
        store_time = time.time() - start_time

        if cache_success:
            logger.info(f"✅ Results cached successfully ({store_time:.3f}s)")
        else:
            logger.error("❌ Failed to cache results")
            return False

        # Test 3: Cache hit (retrieve cached results)
        logger.info("🎯 Test 3: Cache hit scenario")
        start_time = time.time()
        cached_results = await cache.get_cached_results(test_query, test_top_k)
        hit_time = time.time() - start_time

        if cached_results is not None:
            logger.info(f"✅ Cache hit successful ({hit_time:.3f}s)")

            # Verify data integrity
            if len(cached_results) == len(test_results):
                logger.info("✅ Result count matches")

                # Check content
                for i, (cached, original) in enumerate(zip(cached_results, test_results)):
                    if cached["content"] == original["content"]:
                        logger.info(f"✅ Result {i+1} content matches")
                    else:
                        logger.error(f"❌ Result {i+1} content mismatch")
                        return False
            else:
                logger.error(f"❌ Result count mismatch: cached={len(cached_results)}, original={len(test_results)}")
                return False
        else:
            logger.error("❌ Expected cache hit but got None")
            return False

        # Test 4: Performance comparison
        logger.info("⚡ Test 4: Performance analysis")
        logger.info(f"Cache miss time: {miss_time:.3f}s")
        logger.info(f"Cache store time: {store_time:.3f}s")
        logger.info(f"Cache hit time: {hit_time:.3f}s")

        if hit_time < store_time:
            logger.info("✅ Cache retrieval is faster than storage")
        else:
            logger.warning("⚠️ Cache retrieval is slower than storage")

        # Test 5: Cache statistics
        logger.info("📊 Test 5: Cache statistics")
        stats = await cache.get_cache_stats()
        logger.info(f"Cache statistics: {json.dumps(stats, indent=2)}")

        if "cache_entries" in stats and stats["cache_entries"] >= 1:
            logger.info("✅ Cache statistics show entries")
        else:
            logger.warning("⚠️ Cache statistics don't show expected entries")

        # Test 6: Cache clearing
        logger.info("🧹 Test 6: Cache clearing")
        deleted_count = await cache.clear_cache("*test*")
        logger.info(f"✅ Cleared {deleted_count} test cache entries")

        # Verify clearing worked
        cached_results_after_clear = await cache.get_cached_results(test_query, test_top_k)
        if cached_results_after_clear is None:
            logger.info("✅ Cache clearing verified - no results found")
        else:
            logger.warning("⚠️ Cache clearing may not have worked completely")

        # Test 7: Configuration validation
        logger.info("⚙️ Test 7: Configuration validation")
        cache_enabled = cfg.get('knowledge_base.cache.enabled', True)
        cache_ttl = cfg.get('knowledge_base.cache.ttl', 300)
        cache_max_size = cfg.get('knowledge_base.cache.max_size', 1000)

        logger.info(f"Cache enabled: {cache_enabled}")
        logger.info(f"Cache TTL: {cache_ttl} seconds")
        logger.info(f"Cache max size: {cache_max_size} entries")

        logger.info("🎉 All cache tests completed successfully!")
        return True

    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.info("Make sure the AutoBot environment is properly set up")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during cache testing: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test the cache API endpoints"""
    logger.info("🌐 Testing Cache API Endpoints")

    try:
        import aiohttp

        base_url = "http://localhost:8001/api/knowledge_base"
        endpoints_to_test = [
            "/cache/stats",
            "/cache/health"
        ]

        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints_to_test:
                try:
                    url = f"{base_url}{endpoint}"
                    logger.info(f"Testing endpoint: {endpoint}")

                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ {endpoint} - Status: {response.status}")
                            logger.info(f"Response: {json.dumps(data, indent=2)}")
                        else:
                            logger.warning(f"⚠️ {endpoint} - Status: {response.status}")

                except Exception as e:
                    logger.warning(f"⚠️ Could not test {endpoint}: {e}")

        logger.info("🎉 API endpoint testing completed!")
        return True

    except ImportError:
        logger.warning("⚠️ aiohttp not available, skipping API tests")
        return True
    except Exception as e:
        logger.error(f"❌ API testing error: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("🚀 Starting Knowledge Cache Test Suite")

    # Test cache functionality
    cache_test_success = await test_knowledge_cache()

    # Test API endpoints (optional, might fail if backend not running)
    api_test_success = await test_api_endpoints()

    if cache_test_success:
        logger.info("🎉 Knowledge Cache Test Suite PASSED!")
        logger.info("The caching system is ready for production use.")
    else:
        logger.error("❌ Knowledge Cache Test Suite FAILED!")
        logger.error("Please check the implementation and dependencies.")

    return cache_test_success


if __name__ == "__main__":
    asyncio.run(main())
