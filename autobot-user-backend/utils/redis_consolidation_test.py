"""
Test Suite for Redis Client Consolidation

Verifies all consolidated features work correctly and backward compatibility is maintained.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


from utils.redis_client import (
    ConnectionState,
    ManagerStats,
    PoolStatistics,
    RedisConfig,
    RedisConfigLoader,
    RedisConnectionManager,
    RedisDatabase,
    RedisStats,
    get_redis_client,
)


class TestPhase1Configuration:
    """Test Phase 1: Configuration Layer"""

    def test_redis_database_enum(self):
        """Test RedisDatabase enum has all expected databases"""
        assert RedisDatabase.MAIN.value == 0
        assert RedisDatabase.KNOWLEDGE.value == 1
        assert RedisDatabase.PROMPTS.value == 2
        assert RedisDatabase.AGENTS.value == 3
        assert RedisDatabase.METRICS.value == 4

    def test_redis_config_dataclass(self):
        """Test RedisConfig dataclass creation"""
        config = RedisConfig(
            name="test",
            db=0,
            host="172.16.168.23",
            port=6379,
            max_connections=100,
        )
        assert config.name == "test"
        assert config.db == 0
        assert config.max_connections == 100
        assert config.socket_keepalive is True

    def test_redis_config_loader_yaml(self):
        """Test YAML configuration loading"""
        # Should handle missing YAML gracefully
        configs = RedisConfigLoader.load_from_yaml("/nonexistent/path.yaml")
        assert isinstance(configs, dict)

    def test_redis_config_loader_timeout(self):
        """Test timeout configuration loading"""
        timeout_config = RedisConfigLoader.load_timeout_config()
        assert isinstance(timeout_config, dict)
        assert "socket_timeout" in timeout_config
        assert "socket_connect_timeout" in timeout_config


class TestPhase2Statistics:
    """Test Phase 2: Statistics Layer"""

    def test_redis_stats_dataclass(self):
        """Test RedisStats dataclass"""
        stats = RedisStats(
            database_name="test",
            successful_operations=100,
            failed_operations=10,
        )
        assert stats.database_name == "test"
        # Success rate = 100 / (100 + 10) = 90.909...
        assert 90.0 < stats.success_rate < 91.0

    def test_pool_statistics_dataclass(self):
        """Test PoolStatistics dataclass"""
        pool_stats = PoolStatistics(
            database_name="test",
            created_connections=10,
            available_connections=5,
            in_use_connections=5,
            max_connections=20,
            idle_connections=2,
        )
        assert pool_stats.database_name == "test"
        assert pool_stats.created_connections == 10

    def test_manager_stats_dataclass(self):
        """Test ManagerStats dataclass"""
        stats = ManagerStats(
            total_databases=5,
            healthy_databases=4,
            degraded_databases=1,
            failed_databases=0,
        )
        assert stats.total_databases == 5
        assert stats.healthy_databases == 4


class TestPhase3ConnectionManager:
    """Test Phase 3: Enhanced Connection Manager"""

    def test_singleton_pattern(self):
        """Test RedisConnectionManager is a singleton"""
        manager1 = RedisConnectionManager()
        manager2 = RedisConnectionManager()
        assert manager1 is manager2

    def test_manager_initialization(self):
        """Test manager initializes with all attributes"""
        manager = RedisConnectionManager()
        assert hasattr(manager, "_sync_pools")
        assert hasattr(manager, "_async_pools")
        assert hasattr(manager, "_configs")
        assert hasattr(manager, "_database_stats")
        assert hasattr(manager, "_tcp_keepalive_options")
        assert hasattr(manager, "_active_sync_connections")
        assert hasattr(manager, "_active_async_connections")

    def test_tcp_keepalive_configuration(self):
        """Test TCP keepalive options are configured"""
        manager = RedisConnectionManager()
        assert manager._tcp_keepalive_options[1] == 600  # TCP_KEEPIDLE
        assert manager._tcp_keepalive_options[2] == 60  # TCP_KEEPINTVL
        assert manager._tcp_keepalive_options[3] == 5  # TCP_KEEPCNT


class TestPhase4AdvancedFeatures:
    """Test Phase 4: Advanced Features"""

    def test_named_database_methods_exist(self):
        """Test named database convenience methods exist"""
        manager = RedisConnectionManager()
        assert hasattr(manager, "main")
        assert hasattr(manager, "knowledge")
        assert hasattr(manager, "prompts")
        assert hasattr(manager, "agents")
        assert hasattr(manager, "metrics")
        assert hasattr(manager, "sessions")
        assert hasattr(manager, "workflows")
        assert hasattr(manager, "vectors")
        assert hasattr(manager, "models")
        assert hasattr(manager, "memory")
        assert hasattr(manager, "analytics")

    def test_pipeline_context_manager_exists(self):
        """Test pipeline context manager exists"""
        manager = RedisConnectionManager()
        assert hasattr(manager, "pipeline")
        assert callable(manager.pipeline)

    def test_get_pool_statistics_method_exists(self):
        """Test pool statistics method exists"""
        manager = RedisConnectionManager()
        assert hasattr(manager, "get_pool_statistics")
        assert callable(manager.get_pool_statistics)

    def test_cleanup_idle_connections_exists(self):
        """Test idle connection cleanup method exists"""
        manager = RedisConnectionManager()
        assert hasattr(manager, "cleanup_idle_connections")
        assert callable(manager.cleanup_idle_connections)

    def test_get_statistics_method(self):
        """Test get_statistics method returns ManagerStats"""
        manager = RedisConnectionManager()
        stats = manager.get_statistics()
        assert isinstance(stats, ManagerStats)
        assert hasattr(stats, "total_databases")
        assert hasattr(stats, "healthy_databases")


class TestBackwardCompatibility:
    """Test Phase 5: Backward Compatibility"""

    def test_get_redis_client_signature_unchanged(self):
        """Test get_redis_client has same signature"""
        import inspect

        sig = inspect.signature(get_redis_client)
        params = list(sig.parameters.keys())
        assert "async_client" in params
        assert "database" in params
        assert sig.parameters["async_client"].default is False
        assert sig.parameters["database"].default == "main"

    def test_get_redis_client_sync_callable(self):
        """Test synchronous client can be obtained (without connecting)"""
        # Just verify the function is callable and returns something or None
        # Don't test actual connection (might not have Redis running in CI)
        result = get_redis_client(async_client=False, database="main")
        # Result can be redis.Redis or None (if Redis not available)
        assert result is None or hasattr(result, "ping")

    def test_manager_has_legacy_methods(self):
        """Test manager still has legacy methods for compatibility"""
        manager = RedisConnectionManager()
        assert hasattr(manager, "get_sync_client")
        assert hasattr(manager, "get_async_client")
        assert hasattr(manager, "get_metrics")
        assert hasattr(manager, "get_health_status")
        assert hasattr(manager, "close_all")

    def test_connection_state_enum_unchanged(self):
        """Test ConnectionState enum values unchanged"""
        assert ConnectionState.HEALTHY.value == "healthy"
        assert ConnectionState.DEGRADED.value == "degraded"
        assert ConnectionState.FAILED.value == "failed"


class TestFeatureIntegration:
    """Test integrated features work together"""

    def test_manager_creates_config_for_unknown_database(self):
        """Test manager can handle unknown database names"""
        manager = RedisConnectionManager()
        # Should not crash, should use fallback
        db_num = manager._get_database_number("unknown_database")
        assert isinstance(db_num, int)
        assert db_num >= 0

    def test_statistics_tracking(self):
        """Test statistics are tracked correctly"""
        manager = RedisConnectionManager()
        # Update stats
        manager._update_stats("test", success=True)
        manager._update_stats("test", success=False, error="Test error")

        # Verify stats exist
        assert "test" in manager._database_stats
        stats = manager._database_stats["test"]
        assert stats.successful_operations == 1
        assert stats.failed_operations == 1

    def test_circuit_breaker_logic(self):
        """Test circuit breaker opens after failures"""
        manager = RedisConnectionManager()
        database = "test_circuit"

        # Should be closed initially
        assert manager._check_circuit_breaker(database) is False

        # Record multiple failures
        for _ in range(10):
            manager._record_failure(database, Exception("Test error"))

        # Circuit should be open now
        assert manager._check_circuit_breaker(database) is True


def test_module_imports():
    """Test all expected exports are available"""
    from utils import redis_client

    # Check all main exports
    assert hasattr(redis_client, "get_redis_client")
    assert hasattr(redis_client, "RedisConnectionManager")
    assert hasattr(redis_client, "RedisDatabase")
    assert hasattr(redis_client, "RedisConfig")
    assert hasattr(redis_client, "RedisStats")
    assert hasattr(redis_client, "PoolStatistics")
    assert hasattr(redis_client, "ManagerStats")


def test_documentation_completeness():
    """Test key functions have documentation"""
    assert get_redis_client.__doc__ is not None
    assert "CANONICAL" in get_redis_client.__doc__
    assert "CONSOLIDATED FEATURES" in get_redis_client.__doc__


if __name__ == "__main__":
    # Run tests
    print("=" * 80)
    print("Redis Client Consolidation - Test Suite")
    print("=" * 80)

    test_classes = [
        TestPhase1Configuration,
        TestPhase2Statistics,
        TestPhase3ConnectionManager,
        TestPhase4AdvancedFeatures,
        TestBackwardCompatibility,
        TestFeatureIntegration,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        print("-" * 80)

        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                total_tests += 1
                try:
                    test_instance = test_class()
                    method = getattr(test_instance, method_name)
                    method()
                    print(f"  ✅ {method_name}")
                    passed_tests += 1
                except Exception as e:
                    print(f"  ❌ {method_name}: {e}")
                    failed_tests.append((test_class.__name__, method_name, str(e)))

    # Run module-level tests
    print("\nModule Tests:")
    print("-" * 80)
    for func in [test_module_imports, test_documentation_completeness]:
        total_tests += 1
        try:
            func()
            print(f"  ✅ {func.__name__}")
            passed_tests += 1
        except Exception as e:
            print(f"  ❌ {func.__name__}: {e}")
            failed_tests.append(("Module", func.__name__, str(e)))

    # Summary
    print("\n" + "=" * 80)
    print(f"Test Results: {passed_tests}/{total_tests} passed")
    print("=" * 80)

    if failed_tests:
        print("\nFailed Tests:")
        for class_name, method_name, error in failed_tests:
            print(f"  - {class_name}.{method_name}: {error}")
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)
