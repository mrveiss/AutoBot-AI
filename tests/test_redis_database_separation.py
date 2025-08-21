"""
Test Redis Database Separation
Validates that different databases are properly isolated and connections work correctly
"""

import time

import pytest

from src.utils.redis_client import (
    get_agents_redis,
    get_knowledge_base_redis,
    get_main_redis,
    get_metrics_redis,
    get_prompts_redis,
    get_redis_client,
)
from src.utils.redis_database_manager import RedisDatabaseManager


class TestRedisDatabaseSeparation:
    """Test suite for Redis database separation functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.test_data_prefix = f"test_{int(time.time())}"
        self.manager = RedisDatabaseManager()

    def teardown_method(self):
        """Cleanup test data from all databases."""
        try:
            # Clean up test data from all databases
            for db_name in ["main", "knowledge", "prompts", "agents", "metrics"]:
                try:
                    client = self.manager.get_connection(db_name)
                    # Delete all keys with our test prefix
                    for key in client.scan_iter(f"{self.test_data_prefix}*"):
                        client.delete(key)
                except Exception as e:
                    print(f"Cleanup warning for {db_name}: {e}")
        except Exception as e:
            print(f"Cleanup error: {e}")

    def test_database_configuration_loading(self):
        """Test that database configuration loads correctly."""
        config = self.manager.get_database_info()
        assert config is not None
        assert "main" in config
        assert "knowledge" in config
        assert "prompts" in config
        assert "agents" in config

        # Check database numbers are correct
        assert self.manager.get_database_number("main") == 0
        assert self.manager.get_database_number("knowledge") == 1
        assert self.manager.get_database_number("prompts") == 2
        assert self.manager.get_database_number("agents") == 3

    def test_database_separation_validation(self):
        """Test that database separation validation works."""
        is_valid = self.manager.validate_database_separation()
        assert is_valid is True

    def test_different_databases_are_isolated(self):
        """Test that data stored in different databases is properly isolated."""
        test_key = f"{self.test_data_prefix}_isolation"
        test_values = {
            "main": "main_data",
            "knowledge": "knowledge_data",
            "prompts": "prompts_data",
            "agents": "agents_data",
        }

        # Store different values in each database
        for db_name, value in test_values.items():
            client = self.manager.get_connection(db_name)
            client.set(test_key, value)

        # Verify each database has its own isolated data
        for db_name, expected_value in test_values.items():
            client = self.manager.get_connection(db_name)
            stored_value = client.get(test_key)
            assert stored_value == expected_value, (
                f"Database {db_name} should contain '{expected_value}', "
                f"got '{stored_value}'"
            )

    def test_convenience_functions(self):
        """Test that convenience functions connect to correct databases."""
        test_key = f"{self.test_data_prefix}_convenience"

        # Test each convenience function
        convenience_clients = {
            "main": get_main_redis(),
            "knowledge": get_knowledge_base_redis(),
            "prompts": get_prompts_redis(),
            "agents": get_agents_redis(),
            "metrics": get_metrics_redis(),
        }

        # Store unique data through each convenience function
        for db_name, client in convenience_clients.items():
            client.set(test_key, f"{db_name}_convenience_data")

        # Verify data isolation through direct database manager access
        for db_name in convenience_clients.keys():
            direct_client = self.manager.get_connection(db_name)
            value = direct_client.get(test_key)
            expected = f"{db_name}_convenience_data"
            assert value == expected, (
                f"Convenience function for {db_name} failed, "
                f"expected '{expected}', got '{value}'"
            )

    def test_get_redis_client_with_database_parameter(self):
        """Test that get_redis_client works with database parameter."""
        test_key = f"{self.test_data_prefix}_client_param"

        # Test different database parameters
        databases = ["main", "knowledge", "prompts", "agents"]

        for db_name in databases:
            client = get_redis_client(database=db_name)
            client.set(test_key, f"{db_name}_param_data")

        # Verify isolation
        for db_name in databases:
            client = get_redis_client(database=db_name)
            value = client.get(test_key)
            expected = f"{db_name}_param_data"
            assert value == expected, f"get_redis_client(database='{db_name}') failed"

    def test_connection_reuse(self):
        """Test that connections are properly reused."""
        # Get connections multiple times
        client1 = self.manager.get_connection("main")
        client2 = self.manager.get_connection("main")

        # They should be the same connection object (reused)
        assert client1 is client2, "Connections should be reused"

        # But different databases should have different connections
        knowledge_client = self.manager.get_connection("knowledge")
        assert (
            client1 is not knowledge_client
        ), "Different databases should have different connections"

    def test_fallback_to_environment_variables(self):
        """Test that database numbers fall back to environment variables."""
        # Test with a non-existent database name
        db_number = self.manager.get_database_number("nonexistent_db")
        # Should fallback to main database (0)
        assert db_number == 0

    def test_redis_client_backward_compatibility(self):
        """Test that existing code using get_redis_client() still works."""
        test_key = f"{self.test_data_prefix}_backward_compat"

        # Test default behavior (should use main database)
        client = get_redis_client()
        client.set(test_key, "backward_compat_data")

        # Verify it's in the main database
        main_client = get_redis_client(database="main")
        value = main_client.get(test_key)
        assert value == "backward_compat_data"

    def test_database_connection_health(self):
        """Test that all database connections are healthy."""
        databases = ["main", "knowledge", "prompts", "agents", "metrics"]

        for db_name in databases:
            client = self.manager.get_connection(db_name)
            # Test ping to verify connection is healthy
            ping_result = client.ping()
            assert (
                ping_result is True
            ), f"Database {db_name} connection health check failed"

    def test_concurrent_access_to_different_databases(self):
        """Test concurrent access to different databases."""
        import threading

        test_key = f"{self.test_data_prefix}_concurrent"
        results = {}

        def worker(db_name):
            client = self.manager.get_connection(db_name)
            client.set(test_key, f"{db_name}_concurrent")
            results[db_name] = client.get(test_key)

        # Create threads for different databases
        threads = []
        databases = ["main", "knowledge", "prompts", "agents"]

        for db_name in databases:
            thread = threading.Thread(target=worker, args=(db_name,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify results
        for db_name in databases:
            expected = f"{db_name}_concurrent"
            assert (
                results[db_name] == expected
            ), f"Concurrent access to {db_name} failed"

    def test_error_handling_for_invalid_database(self):
        """Test error handling when trying to connect to invalid database."""
        # This should not raise an exception, but should fall back gracefully
        try:
            client = self.manager.get_connection("invalid_database")
            # Should still get a valid Redis client (fallback to main DB)
            assert client is not None
            ping_result = client.ping()
            assert ping_result is True
        except Exception as e:
            pytest.fail(f"Should handle invalid database gracefully, but got: {e}")

    def test_database_specific_features(self):
        """Test database-specific functionality."""
        # Test TTL handling for different databases
        test_key = f"{self.test_data_prefix}_ttl"

        # Knowledge database - should support longer TTLs
        knowledge_client = get_knowledge_base_redis()
        knowledge_client.setex(test_key, 86400, "knowledge_with_ttl")  # 24 hours
        ttl = knowledge_client.ttl(test_key)
        assert ttl > 0, "Knowledge database should support TTL"

        # Agents database - should support shorter TTLs
        agents_client = get_agents_redis()
        agents_client.setex(test_key, 300, "agents_with_ttl")  # 5 minutes
        ttl = agents_client.ttl(test_key)
        assert ttl > 0, "Agents database should support TTL"


# Integration test that can be run manually
if __name__ == "__main__":
    print("🧪 Running Redis Database Separation Tests...")

    test_suite = TestRedisDatabaseSeparation()
    test_methods = [method for method in dir(test_suite) if method.startswith("test_")]

    passed = 0
    failed = 0

    for test_method in test_methods:
        try:
            print(f"Running {test_method}...")
            test_suite.setup_method()
            getattr(test_suite, test_method)()
            test_suite.teardown_method()
            print(f"✅ {test_method} PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ {test_method} FAILED: {e}")
            failed += 1
            test_suite.teardown_method()  # Cleanup even on failure

    print(f"\n📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All Redis database separation tests passed!")
    else:
        print("⚠️  Some tests failed - check Redis configuration")
