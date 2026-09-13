#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Comprehensive test suite for Phase 4: Cache Consolidation

Tests the unified AdvancedCacheManager with backward compatibility for:
- backend/utils/cache_manager.py (SimpleCacheManager wrapper)
- src/utils/knowledge_cache.py (knowledge-specific methods)

Ensures all features from 3 cache managers are preserved in one unified implementation.
"""

import importlib
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Modules migrated onto the unified AdvancedCacheManager in Phase 4.
MIGRATED_MODULES = (
    "api.llm",
    "api.system",
    "utils.system_validator",
    "api.cache_management",
    "api.project_state",
    "api.templates",
)


def test_imports():
    """Test 1: All imports work correctly"""
    from utils.advanced_cache_manager import SimpleCacheManager, advanced_cache, cache_manager

    # Verify global instances exist
    assert advanced_cache is not None, "advanced_cache instance missing"
    assert cache_manager is not None, "cache_manager instance missing"

    # Verify SimpleCacheManager is instance
    assert isinstance(cache_manager, SimpleCacheManager), "cache_manager should be SimpleCacheManager instance"


def test_simple_cache_basic_operations():
    """Test 2: SimpleCacheManager basic operations (get, set, delete)"""
    from utils.advanced_cache_manager import SimpleCacheManager

    cache = SimpleCacheManager(default_ttl=300)

    # Test attributes
    assert cache.default_ttl == 300, "default_ttl mismatch"
    assert cache.cache_prefix == "cache:", "cache_prefix mismatch"

    # Test methods exist
    assert hasattr(cache, "get"), "Missing get method"
    assert hasattr(cache, "set"), "Missing set method"
    assert hasattr(cache, "delete"), "Missing delete method"
    assert hasattr(cache, "clear"), "Missing clear method"
    assert hasattr(cache, "clear_pattern"), "Missing clear_pattern method"
    assert hasattr(cache, "get_stats"), "Missing get_stats method"
    assert hasattr(cache, "_ensure_redis_client"), "Missing _ensure_redis_client method"
    assert hasattr(cache, "cache_response"), "Missing cache_response decorator"

    # Test properties
    assert hasattr(cache, "_redis_client"), "Missing _redis_client property"
    assert hasattr(cache, "_redis_initialized"), "Missing _redis_initialized property"


def test_cache_response_decorator():
    """Test 3: cache_response decorator functionality"""
    from utils.advanced_cache_manager import cache_response

    # Test decorator is callable
    assert callable(cache_response), "cache_response should be callable"

    # Test decorator with parameters
    decorator = cache_response(cache_key="test_key", ttl=60)
    assert callable(decorator), "cache_response decorator should return callable"

    # Test decorator without parameters
    decorator_default = cache_response()
    assert callable(decorator_default), "cache_response with defaults should return callable"


def test_knowledge_cache_functions():
    """Test 4: Knowledge cache functions"""
    from utils.advanced_cache_manager import cache_knowledge_results, get_cached_knowledge_results, get_knowledge_cache

    # Test functions exist and are callable
    assert callable(get_cached_knowledge_results), "Missing get_cached_knowledge_results"
    assert callable(cache_knowledge_results), "Missing cache_knowledge_results"
    assert callable(get_knowledge_cache), "Missing get_knowledge_cache"

    # Test get_knowledge_cache returns cache instance
    kb_cache = get_knowledge_cache()
    assert kb_cache is not None, "get_knowledge_cache should return instance"


def test_advanced_cache_manager_features():
    """Test 5: AdvancedCacheManager knowledge features"""
    from utils.advanced_cache_manager import AdvancedCacheManager, CacheStrategy

    # Test KNOWLEDGE strategy exists
    assert hasattr(CacheStrategy, "KNOWLEDGE"), "Missing KNOWLEDGE cache strategy"

    # Test AdvancedCacheManager has knowledge methods
    cache = AdvancedCacheManager()
    assert hasattr(cache, "get_cached_knowledge_results"), "Missing get_cached_knowledge_results"
    assert hasattr(cache, "cache_knowledge_results"), "Missing cache_knowledge_results"
    assert hasattr(cache, "_generate_knowledge_key"), "Missing _generate_knowledge_key"
    assert hasattr(cache, "_manage_cache_size"), "Missing _manage_cache_size"

    # Test knowledge cache configs
    assert "knowledge_queries" in cache.cache_configs, "Missing knowledge_queries config"
    assert "knowledge_embeddings" in cache.cache_configs, "Missing knowledge_embeddings config"

    # Verify knowledge configs use KNOWLEDGE strategy
    kb_query_config = cache.cache_configs["knowledge_queries"]
    assert kb_query_config.strategy == CacheStrategy.KNOWLEDGE, "knowledge_queries should use KNOWLEDGE strategy"


def test_backward_compatibility_simple():
    """Test 6: SimpleCacheManager backward compatibility"""
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

    # Test all original CacheManager attributes exist
    attributes = [
        "default_ttl",
        "cache_prefix",
        "_redis_client",
        "_redis_initialized",
    ]

    for attr in attributes:
        assert hasattr(cache, attr), f"Missing attribute: {attr}"


def test_migrated_files_import():
    """Test 7: Migrated files can import successfully"""
    for module_name in MIGRATED_MODULES:
        module = importlib.import_module(module_name)
        assert module is not None, f"Migrated module imported as None: {module_name}"


def test_cache_function_decorator():
    """Test 8: cache_function decorator"""
    from utils.advanced_cache_manager import cache_function

    # Test decorator exists and is callable
    assert callable(cache_function), "cache_function should be callable"

    # Test decorator with parameters
    decorator = cache_function(cache_key="test_func", ttl=120)
    assert callable(decorator), "cache_function decorator should return callable"


def test_global_instances():
    """Test 9: Global cache instances work correctly"""
    from utils.advanced_cache_manager import AdvancedCacheManager, SimpleCacheManager, advanced_cache, cache_manager

    # Test advanced_cache is AdvancedCacheManager instance
    assert isinstance(advanced_cache, AdvancedCacheManager), "advanced_cache should be AdvancedCacheManager instance"

    # Test cache_manager is SimpleCacheManager instance
    assert isinstance(cache_manager, SimpleCacheManager), "cache_manager should be SimpleCacheManager instance"

    # Test cache_manager wraps advanced_cache
    assert cache_manager._cache is advanced_cache, "cache_manager should wrap advanced_cache"


def test_feature_completeness():
    """Test 10: All features from 3 cache managers preserved"""
    from utils.advanced_cache_manager import AdvancedCacheManager, CacheStrategy, SimpleCacheManager

    # Test AdvancedCacheManager features (original)
    adv_features = [
        "get",
        "set",
        "invalidate",
    ]
    cache = AdvancedCacheManager()
    for feature in adv_features:
        assert hasattr(cache, feature), f"Missing AdvancedCacheManager feature: {feature}"

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
        assert hasattr(simple, feature), f"Missing SimpleCacheManager feature: {feature}"

    # Test knowledge cache features
    knowledge_features = [
        "get_cached_knowledge_results",
        "cache_knowledge_results",
        "_generate_knowledge_key",
        "_manage_cache_size",
    ]
    for feature in knowledge_features:
        assert hasattr(cache, feature), f"Missing knowledge cache feature: {feature}"

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
        assert hasattr(CacheStrategy, strategy), f"Missing cache strategy: {strategy}"
