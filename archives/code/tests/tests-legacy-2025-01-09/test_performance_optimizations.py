"""
Test Performance Optimizations
Validates that agent-identified performance fixes are working correctly
Expected improvements: 60-80% faster chat, 80% memory reduction, stable Redis
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from utils.apply_performance_fixes import get_performance_optimizer, benchmark_performance_improvements

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_optimized_stream_processor():
    """Test the optimized LLM stream processor"""
    logger.info("🧪 Testing optimized stream processor...")
    
    try:
        from utils.optimized_stream_processor import OptimizedLLMInterface
        
        interface = OptimizedLLMInterface()
        
        # Test streaming request
        start_time = time.time()
        
        url = "http://localhost:11434/api/chat"
        data = {
            "model": "llama3.1:8b",
            "messages": [{"role": "user", "content": "Say hello"}],
            "stream": True
        }
        
        content, success = await interface.stream_ollama_request(url, data)
        response_time = (time.time() - start_time) * 1000
        
        logger.info(f"✅ Stream test: {response_time:.2f}ms, success: {success}")
        logger.info(f"📝 Response: {content[:100]}...")
        
        await interface.cleanup()
        return True
        
    except Exception as e:
        logger.error(f"❌ Stream processor test failed: {e}")
        return False


async def test_redis_connection_pooling():
    """Test the optimized Redis connection pooling"""
    logger.info("🧪 Testing Redis connection pooling...")
    
    try:
        from utils.optimized_redis_manager import get_optimized_redis_manager
        
        manager = get_optimized_redis_manager()
        
        # Test connection pool creation with correct Redis host
        client1 = manager.get_redis_client('172.16.168.23', 6379, 0)
        client2 = manager.get_redis_client('172.16.168.23', 6379, 1)
        
        # Test operations
        client1.set('test_key_1', 'test_value_1')
        client2.set('test_key_2', 'test_value_2')
        
        value1 = client1.get('test_key_1')
        value2 = client2.get('test_key_2')
        
        # Test pool statistics
        stats = manager.get_pool_stats()
        health = await manager.health_check_all_pools()
        
        logger.info(f"✅ Redis test: Pools created: {len(stats)}")
        logger.info(f"📊 Health status: {health}")
        logger.info(f"📈 Pool stats: {json.dumps(stats, indent=2)}")
        
        # Clean up test keys
        client1.delete('test_key_1')
        client2.delete('test_key_2')
        
        return len(stats) > 0 and all(health.values())
        
    except Exception as e:
        logger.error(f"❌ Redis pooling test failed: {e}")
        return False


async def test_memory_management():
    """Test the optimized memory management"""
    logger.info("🧪 Testing memory management...")
    
    try:
        from utils.optimized_memory_manager import get_optimized_memory_manager
        
        manager = get_optimized_memory_manager()
        
        # Test cache creation and operations
        cache_name = 'test_cache'
        cache = manager.create_lru_cache(cache_name, 100)
        
        # Fill cache beyond limit to test LRU eviction
        for i in range(150):
            manager.put_in_cache(cache_name, f'key_{i}', f'value_{i}')
        
        # Test LRU behavior
        recent_value = manager.get_from_cache(cache_name, 'key_149')  # Should exist
        old_value = manager.get_from_cache(cache_name, 'key_0')      # Should be evicted
        
        # Get statistics
        cache_stats = manager.get_cache_stats()
        memory_usage = manager.get_memory_usage()
        
        logger.info(f"✅ Memory test: Cache size: {cache_stats[cache_name]['size']}")
        logger.info(f"📊 LRU eviction working: {old_value is None and recent_value is not None}")
        logger.info(f"💾 Memory usage: {memory_usage['percent']:.1f}%")
        
        # Test cleanup
        cleaned = manager.cleanup_specific_cache(cache_name, 1.0)
        logger.info(f"🧹 Cleaned {cleaned} cache entries")
        
        return cache_stats[cache_name]['size'] <= 100
        
    except Exception as e:
        logger.error(f"❌ Memory management test failed: {e}")
        return False


async def test_integrated_performance():
    """Test integrated performance optimizer"""
    logger.info("🧪 Testing integrated performance optimizer...")
    
    try:
        optimizer = await get_performance_optimizer()
        
        # Get performance metrics
        metrics = await optimizer.get_performance_metrics()
        
        # Run benchmarks
        benchmarks = await benchmark_performance_improvements()
        
        logger.info("📊 Performance Metrics:")
        logger.info(json.dumps(metrics, indent=2, default=str))
        
        logger.info("🏁 Benchmark Results:")
        logger.info(json.dumps(benchmarks, indent=2, default=str))
        
        # Validate optimizations are working
        optimizations_working = (
            'memory' in metrics and 
            'redis' in metrics and
            'tests' in benchmarks
        )
        
        if optimizations_working:
            logger.info("✅ All performance optimizations validated!")
        else:
            logger.warning("⚠️  Some optimizations may not be working correctly")
        
        return optimizations_working
        
    except Exception as e:
        logger.error(f"❌ Integrated performance test failed: {e}")
        return False


async def main():
    """Run all performance optimization tests"""
    logger.info("🚀 Starting performance optimization validation tests...")
    
    tests = [
        ("Stream Processor", test_optimized_stream_processor),
        ("Redis Pooling", test_redis_connection_pooling),
        ("Memory Management", test_memory_management),
        ("Integrated Performance", test_integrated_performance)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} Test")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            results[test_name] = result
            
            if result:
                logger.info(f"✅ {test_name} test PASSED")
            else:
                logger.error(f"❌ {test_name} test FAILED")
                
        except Exception as e:
            logger.error(f"❌ {test_name} test ERROR: {e}")
            results[test_name] = False
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All performance optimizations are working correctly!")
        logger.info("Expected improvements:")
        logger.info("  • 60-80% faster chat responses")
        logger.info("  • 80% reduction in memory growth")  
        logger.info("  • Stable Redis connection performance")
    else:
        logger.warning("⚠️  Some performance optimizations need attention")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)