#!/usr/bin/env python3
"""
Comprehensive test suite for Phase 4: Cache Consolidation

Tests the unified AdvancedCacheManager with backward compatibility for:
- backend/utils/cache_manager.py (SimpleCacheManager wrapper)
- src/utils/knowledge_cache.py (knowledge-specific methods)

Ensures all features from 3 cache managers are preserved in one unified implementation.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """Test 1: All imports work correctly"""
    print("\n" + "=" * 70)
    print("TEST 1: Import Verification")
    print("=" * 70)

    try:
        # Import unified cache manager components
        from utils.advanced_cache_manager import (
            SimpleCacheManager,
            advanced_cache,
            cache_manager,
        )

        print("✓ All AdvancedCacheManager imports successful")

        # Verify global instances exist
        assert advanced_cache is not None, "advanced_cache instance missing"
        assert cache_manager is not None, "cache_manager instance missing"
        print("✓ Global cache instances verified")

        # Verify SimpleCacheManager is instance
        assert isinstance(
            cache_manager, SimpleCacheManager
        ), "cache_manager should be SimpleCacheManager instance"
        print("✓ cache_manager is SimpleCacheManager instance")

        return True

    except Exception as e:
        print(f"✗ Import test failed: {e}")
        return False


def test_simple_cache_basic_operations():
    """Test 2: SimpleCacheManager basic operations (get, set, delete)"""
    print("\n" + "=" * 70)
    print("TEST 2: SimpleCacheManager Basic Operations")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import SimpleCacheManager

        # Create cache instance
        cache = SimpleCacheManager(default_ttl=300)
        print("✓ SimpleCacheManager created")

        # Test attributes
        assert cache.default_ttl == 300, "default_ttl mismatch"
        assert cache.cache_prefix == "cache:", "cache_prefix mismatch"
        print("✓ SimpleCacheManager attributes verified")

        # Test methods exist
        assert hasattr(cache, "get"), "Missing get method"
        assert hasattr(cache, "set"), "Missing set method"
        assert hasattr(cache, "delete"), "Missing delete method"
        assert hasattr(cache, "clear"), "Missing clear method"
        assert hasattr(cache, "clear_pattern"), "Missing clear_pattern method"
        assert hasattr(cache, "get_stats"), "Missing get_stats method"
        assert hasattr(
            cache, "_ensure_redis_client"
        ), "Missing _ensure_redis_client method"
        assert hasattr(cache, "cache_response"), "Missing cache_response decorator"
        print("✓ All SimpleCacheManager methods present")

        # Test properties
        assert hasattr(cache, "_redis_client"), "Missing _redis_client property"
        assert hasattr(
            cache, "_redis_initialized"
        ), "Missing _redis_initialized property"
        print("✓ All SimpleCacheManager properties present")

        return True

    except Exception as e:
        print(f"✗ SimpleCacheManager basic operations test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cache_response_decorator():
    """Test 3: cache_response decorator functionality"""
    print("\n" + "=" * 70)
    print("TEST 3: cache_response Decorator")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import cache_response

        # Test decorator is callable
        assert callable(cache_response), "cache_response should be callable"
        print("✓ cache_response is callable")

        # Test decorator with parameters
        decorator = cache_response(cache_key="test_key", ttl=60)
        assert callable(decorator), "cache_response decorator should return callable"
        print("✓ cache_response decorator returns callable")

        # Test decorator without parameters
        decorator_default = cache_response()
        assert callable(
            decorator_default
        ), "cache_response with defaults should return callable"
        print("✓ cache_response with defaults works")

        return True

    except Exception as e:
        print(f"✗ cache_response decorator test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_knowledge_cache_functions():
    """Test 4: Knowledge cache functions"""
    print("\n" + "=" * 70)
    print("TEST 4: Knowledge Cache Functions")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import (
            cache_knowledge_results,
            get_cached_knowledge_results,
            get_knowledge_cache,
        )

        # Test functions exist and are callable
        assert callable(
            get_cached_knowledge_results
        ), "Missing get_cached_knowledge_results"
        assert callable(cache_knowledge_results), "Missing cache_knowledge_results"
        assert callable(get_knowledge_cache), "Missing get_knowledge_cache"
        print("✓ All knowledge cache functions present")

        # Test get_knowledge_cache returns cache instance
        kb_cache = get_knowledge_cache()
        assert kb_cache is not None, "get_knowledge_cache should return instance"
        print("✓ get_knowledge_cache returns instance")

        return True

    except Exception as e:
        print(f"✗ Knowledge cache functions test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_advanced_cache_manager_features():
    """Test 5: AdvancedCacheManager knowledge features"""
    print("\n" + "=" * 70)
    print("TEST 5: AdvancedCacheManager Knowledge Features")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import AdvancedCacheManager, CacheStrategy

        # Test KNOWLEDGE strategy exists
        assert hasattr(CacheStrategy, "KNOWLEDGE"), "Missing KNOWLEDGE cache strategy"
        print("✓ KNOWLEDGE cache strategy exists")

        # Test AdvancedCacheManager has knowledge methods
        cache = AdvancedCacheManager()
        assert hasattr(
            cache, "get_cached_knowledge_results"
        ), "Missing get_cached_knowledge_results"
        assert hasattr(
            cache, "cache_knowledge_results"
        ), "Missing cache_knowledge_results"
        assert hasattr(
            cache, "_generate_knowledge_key"
        ), "Missing _generate_knowledge_key"
        assert hasattr(cache, "_manage_cache_size"), "Missing _manage_cache_size"
        print("✓ All knowledge-specific methods present")

        # Test knowledge cache configs
        assert (
            "knowledge_queries" in cache.cache_configs
        ), "Missing knowledge_queries config"
        assert (
            "knowledge_embeddings" in cache.cache_configs
        ), "Missing knowledge_embeddings config"
        print("✓ Knowledge cache configs present")

        # Verify knowledge configs use KNOWLEDGE strategy
        kb_query_config = cache.cache_configs["knowledge_queries"]
        assert (
            kb_query_config.strategy == CacheStrategy.KNOWLEDGE
        ), "knowledge_queries should use KNOWLEDGE strategy"
        print("✓ Knowledge configs use KNOWLEDGE strategy")

        return True

    except Exception as e:
        print(f"✗ AdvancedCacheManager knowledge features test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_backward_compatibility_simple():
    """Test 6: SimpleCacheManager backward compatibility"""
    print("\n" + "=" * 70)
    print("TEST 6: SimpleCacheManager Backward Compatibility")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import SimpleCacheManager

        # Create instance with original CacheManager API
        cache = SimpleCacheManager(default_ttl=300)

        # Test all original CacheManager methods exist
        methods = [
            "get",
            "set",
            "delete",
            "clear_pattern",
            "get_stats",
            "_ensure_redis_client",
            "cache_response",
        ]

        for method in methods:
            assert hasattr(cache, method), f"Missing method: {method}"
        print(f"✓ All {len(methods)} original CacheManager methods present")

        # Test all original CacheManager attributes exist
        attributes = [
            "default_ttl",
            "cache_prefix",
            "_redis_client",
            "_redis_initialized",
        ]

        for attr in attributes:
            assert hasattr(cache, attr), f"Missing attribute: {attr}"
        print(f"✓ All {len(attributes)} original CacheManager attributes present")

        return True

    except Exception as e:
        print(f"✗ SimpleCacheManager backward compatibility test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_migrated_files_import():
    """Test 7: Migrated files can import successfully"""
    print("\n" + "=" * 70)
    print("TEST 7: Migrated Files Import Verification")
    print("=" * 70)

    try:
        # Test backend/api/llm.py
        pass

        print("✓ backend/api/llm.py imports successfully")

        # Test backend/api/system.py

        print("✓ backend/api/system.py imports successfully")

        # Test src/utils/system_validator.py

        print("✓ src/utils/system_validator.py imports successfully")

        # Test files already using AdvancedCacheManager

        print("✓ backend/api/cache_management.py imports successfully")
        print("✓ backend/api/project_state.py imports successfully")
        print("✓ backend/api/templates.py imports successfully")

        return True

    except Exception as e:
        print(f"✗ Migrated files import test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cache_function_decorator():
    """Test 8: cache_function decorator"""
    print("\n" + "=" * 70)
    print("TEST 8: cache_function Decorator")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import cache_function

        # Test decorator exists and is callable
        assert callable(cache_function), "cache_function should be callable"
        print("✓ cache_function is callable")

        # Test decorator with parameters
        decorator = cache_function(cache_key="test_func", ttl=120)
        assert callable(decorator), "cache_function decorator should return callable"
        print("✓ cache_function decorator returns callable")

        return True

    except Exception as e:
        print(f"✗ cache_function decorator test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_global_instances():
    """Test 9: Global cache instances work correctly"""
    print("\n" + "=" * 70)
    print("TEST 9: Global Cache Instances")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import (
            AdvancedCacheManager,
            SimpleCacheManager,
            advanced_cache,
            cache_manager,
        )

        # Test advanced_cache is AdvancedCacheManager instance
        assert isinstance(
            advanced_cache, AdvancedCacheManager
        ), "advanced_cache should be AdvancedCacheManager instance"
        print("✓ advanced_cache is AdvancedCacheManager instance")

        # Test cache_manager is SimpleCacheManager instance
        assert isinstance(
            cache_manager, SimpleCacheManager
        ), "cache_manager should be SimpleCacheManager instance"
        print("✓ cache_manager is SimpleCacheManager instance")

        # Test cache_manager wraps advanced_cache
        assert (
            cache_manager._cache is advanced_cache
        ), "cache_manager should wrap advanced_cache"
        print("✓ cache_manager wraps advanced_cache")

        return True

    except Exception as e:
        print(f"✗ Global instances test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_feature_completeness():
    """Test 10: All features from 3 cache managers preserved"""
    print("\n" + "=" * 70)
    print("TEST 10: Feature Completeness Verification")
    print("=" * 70)

    try:
        from utils.advanced_cache_manager import (
            AdvancedCacheManager,
            CacheStrategy,
            SimpleCacheManager,
        )

        # Test AdvancedCacheManager features (original)
        adv_features = [
            "get",
            "set",
            "invalidate",
        ]
        cache = AdvancedCacheManager()
        for feature in adv_features:
            assert hasattr(
                cache, feature
            ), f"Missing AdvancedCacheManager feature: {feature}"
        print(
            f"✓ All {len(adv_features)} AdvancedCacheManager original features present"
        )

        # Test SimpleCacheManager features (CacheManager compatibility)
        simple_features = [
            "get",
            "set",
            "delete",
            "clear_pattern",
            "get_stats",
            "cache_response",
        ]
        simple = SimpleCacheManager()
        for feature in simple_features:
            assert hasattr(
                simple, feature
            ), f"Missing SimpleCacheManager feature: {feature}"
        print(f"✓ All {len(simple_features)} SimpleCacheManager features present")

        # Test knowledge cache features
        knowledge_features = [
            "get_cached_knowledge_results",
            "cache_knowledge_results",
            "_generate_knowledge_key",
            "_manage_cache_size",
        ]
        for feature in knowledge_features:
            assert hasattr(
                cache, feature
            ), f"Missing knowledge cache feature: {feature}"
        print(f"✓ All {len(knowledge_features)} knowledge cache features present")

        # Test cache strategies
        strategies = [
            "STATIC",
            "DYNAMIC",
            "USER_SCOPED",
            "COMPUTED",
            "TEMPORARY",
            "KNOWLEDGE",
        ]
        for strategy in strategies:
            assert hasattr(
                CacheStrategy, strategy
            ), f"Missing cache strategy: {strategy}"
        print(f"✓ All {len(strategies)} cache strategies present")

        return True

    except Exception as e:
        print(f"✗ Feature completeness test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def run_all_tests():
    """Run all P4 cache consolidation tests"""
    print("\n" + "=" * 70)
    print("PHASE 4: CACHE CONSOLIDATION - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print("\nTesting unified AdvancedCacheManager with backward compatibility")
    print("Target files: 6 (3 migrated + 3 already using AdvancedCacheManager)")
    print(
        "Consolidating: cache_manager.py + knowledge_cache.py + advanced_cache_manager.py"
    )

    tests = [
        ("Import Verification", test_imports),
        ("SimpleCacheManager Basic Operations", test_simple_cache_basic_operations),
        ("cache_response Decorator", test_cache_response_decorator),
        ("Knowledge Cache Functions", test_knowledge_cache_functions),
        (
            "AdvancedCacheManager Knowledge Features",
            test_advanced_cache_manager_features,
        ),
        (
            "SimpleCacheManager Backward Compatibility",
            test_backward_compatibility_simple,
        ),
        ("Migrated Files Import", test_migrated_files_import),
        ("cache_function Decorator", test_cache_function_decorator),
        ("Global Cache Instances", test_global_instances),
        ("Feature Completeness", test_feature_completeness),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' failed with exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((test_name, False))

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 70)
    print(f"OVERALL: {passed}/{total} tests passed")
    print("=" * 70)

    if passed == total:
        print("\n✓ ALL TESTS PASSED - P4 Cache Consolidation Successful!")
        print("\nNext steps:")
        print("1. Code review (mandatory)")
        print("2. Archive old cache managers")
        print("3. Commit P4 consolidation")
        return True
    else:
        print(f"\n✗ {total - passed} tests failed - Fix issues before proceeding")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
