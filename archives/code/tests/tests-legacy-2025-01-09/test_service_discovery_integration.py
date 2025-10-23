"""
Test Service Discovery Integration with Redis Connections

Validates that distributed_service_discovery.py is properly integrated
and eliminates DNS resolution timeouts.
"""

import sys
import time
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_service_discovery_sync():
    """Test synchronous service discovery functions"""
    from src.utils.distributed_service_discovery import (
        get_redis_connection_params_sync,
        get_service_endpoint_sync
    )

    print("\n" + "=" * 60)
    print("TEST 1: Synchronous Service Discovery Functions")
    print("=" * 60)

    # Test Redis connection parameters
    start_time = time.time()
    params = get_redis_connection_params_sync()
    elapsed = time.time() - start_time

    print(f"\n✅ get_redis_connection_params_sync() executed in {elapsed*1000:.2f}ms")
    print(f"   Host: {params['host']}")
    print(f"   Port: {params['port']}")
    print(f"   Socket Connect Timeout: {params['socket_connect_timeout']}s")
    print(f"   Socket Timeout: {params['socket_timeout']}s")

    assert params['host'] == '172.16.168.23', f"Expected Redis VM IP, got {params['host']}"
    assert params['port'] == 6379, f"Expected port 6379, got {params['port']}"
    assert params['socket_connect_timeout'] == 0.5, "Expected fast timeout 0.5s"
    assert elapsed < 0.1, f"Function took {elapsed}s, expected < 0.1s (instant)"

    # Test service endpoint resolution
    redis_endpoint = get_service_endpoint_sync('redis')
    print(f"\n✅ get_service_endpoint_sync('redis')")
    print(f"   Host: {redis_endpoint['host']}")
    print(f"   Port: {redis_endpoint['port']}")
    print(f"   Protocol: {redis_endpoint['protocol']}")

    assert redis_endpoint['host'] == '172.16.168.23'
    assert redis_endpoint['port'] == 6379
    assert redis_endpoint['protocol'] == 'redis'

    print("\n✅ All synchronous service discovery tests PASSED")
    return True


def test_redis_connection_with_service_discovery():
    """Test actual Redis connection using service discovery"""
    import redis
    from src.utils.distributed_service_discovery import get_redis_connection_params_sync

    print("\n" + "=" * 60)
    print("TEST 2: Redis Connection with Service Discovery")
    print("=" * 60)

    # Get parameters from service discovery
    start_time = time.time()
    params = get_redis_connection_params_sync()
    param_time = time.time() - start_time

    print(f"\n✅ Got service discovery params in {param_time*1000:.2f}ms")

    # Create Redis connection
    connection_start = time.time()
    try:
        client = redis.Redis(
            host=params['host'],
            port=params['port'],
            socket_connect_timeout=params['socket_connect_timeout'],
            socket_timeout=params['socket_timeout'],
            retry_on_timeout=params['retry_on_timeout'],
            decode_responses=True
        )

        # Test connection
        ping_start = time.time()
        result = client.ping()
        ping_time = time.time() - ping_start
        total_time = time.time() - connection_start

        print(f"✅ Redis PING successful in {ping_time*1000:.2f}ms")
        print(f"✅ Total connection time: {total_time*1000:.2f}ms")
        print(f"   (Parameter retrieval: {param_time*1000:.2f}ms + Connection: {(total_time-param_time)*1000:.2f}ms)")

        assert result is True, "Redis PING failed"
        assert total_time < 1.0, f"Connection took {total_time}s, expected < 1s"

        # Test a simple operation
        client.set('test:service_discovery', 'integration_test', ex=60)
        value = client.get('test:service_discovery')
        assert value == 'integration_test', f"Expected 'integration_test', got {value}"

        print(f"✅ Redis SET/GET operations successful")

        client.close()
        print("\n✅ Redis connection test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Redis connection FAILED: {e}")
        return False


def test_integrated_modules():
    """Test modules that were integrated with service discovery"""
    print("\n" + "=" * 60)
    print("TEST 3: Integrated Module Imports")
    print("=" * 60)

    modules_to_test = [
        ('backend.api.cache', 'get_redis_connection'),
        ('backend.api.infrastructure_monitor', 'InfrastructureMonitor'),
        ('backend.api.codebase_analytics', 'get_redis_connection'),
        ('src.redis_pool_manager', 'RedisPoolManager'),
    ]

    all_passed = True
    for module_name, class_or_func in modules_to_test:
        try:
            module = __import__(module_name, fromlist=[class_or_func])
            obj = getattr(module, class_or_func)
            print(f"✅ {module_name}.{class_or_func} - Import successful")
        except Exception as e:
            print(f"❌ {module_name}.{class_or_func} - Import FAILED: {e}")
            all_passed = False

    if all_passed:
        print("\n✅ All module imports PASSED")
    else:
        print("\n❌ Some module imports FAILED")

    return all_passed


def test_cache_api_integration():
    """Test backend.api.cache integration"""
    print("\n" + "=" * 60)
    print("TEST 4: cache.py Integration Test")
    print("=" * 60)

    try:
        from backend.api.cache import get_redis_connection

        # Test connection function
        start_time = time.time()
        client = get_redis_connection(db_number=5)  # Cache database
        connection_time = time.time() - start_time

        # Test connection
        result = client.ping()
        total_time = time.time() - start_time

        print(f"✅ cache.py get_redis_connection() successful in {total_time*1000:.2f}ms")
        print(f"   Connection creation: {connection_time*1000:.2f}ms")
        print(f"   PING test: {(total_time-connection_time)*1000:.2f}ms")

        assert result is True
        assert total_time < 1.0, f"Expected < 1s, got {total_time}s"

        client.close()
        print("✅ cache.py integration test PASSED")
        return True

    except Exception as e:
        print(f"❌ cache.py integration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests"""
    print("\n" + "=" * 60)
    print("SERVICE DISCOVERY INTEGRATION TEST SUITE")
    print("=" * 60)
    print("Testing distributed_service_discovery.py integration")
    print("Goal: Eliminate Redis DNS resolution timeouts")
    print("=" * 60)

    tests = [
        ("Synchronous Service Discovery", test_service_discovery_sync),
        ("Redis Connection Test", test_redis_connection_with_service_discovery),
        ("Module Import Test", test_integrated_modules),
        ("cache.py Integration", test_cache_api_integration),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {test_name}")

    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n✅ ALL TESTS PASSED - Service discovery integration successful!")
        print("   DNS resolution timeouts eliminated ✓")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
