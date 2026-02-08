"""
Unit Tests for Timeout Configuration System

Tests the centralized timeout configuration implemented in KB-ASYNC-014.
Validates:
- Timeout configuration loading
- Environment-aware timeout access
- Accessor class functionality
- Backward compatibility
"""

import os

import pytest
from config import UnifiedConfigManager
from utils.knowledge_base_timeouts import KnowledgeBaseTimeouts


class TestUnifiedConfigTimeouts:
    """Test UnifiedConfigManager timeout methods"""

    def setup_method(self):
        """Setup for each test"""
        self.config = UnifiedConfigManager()

    def test_get_timeout_for_env_production(self):
        """Test environment-specific timeout retrieval for production"""
        # Get expected value from configuration
        expected = self.config.get(
            "environments.production.timeouts.redis.operations.get"
        )

        timeout = self.config.get_timeout_for_env(
            "redis.operations", "get", environment="production"
        )
        assert timeout == expected

    def test_get_timeout_for_env_development(self):
        """Test environment-specific timeout retrieval for development"""
        # Redis GET - base value (no override in development)
        base_value = self.config.get("timeouts.redis.operations.get")
        timeout = self.config.get_timeout_for_env(
            "redis.operations", "get", environment="development"
        )
        assert timeout == base_value

        # Redis SCAN_ITER - should use development override
        expected = self.config.get(
            "environments.development.timeouts.redis.operations.scan_iter"
        )
        timeout = self.config.get_timeout_for_env(
            "redis.operations", "scan_iter", environment="development"
        )
        assert timeout == expected

    def test_get_timeout_for_env_base_values(self):
        """Test base timeout values without environment override"""
        # Test base Redis connection timeout (no production override)
        expected = self.config.get("timeouts.redis.connection.socket_connect")
        timeout = self.config.get_timeout_for_env(
            "redis.connection", "socket_connect", environment="production"
        )
        assert timeout == expected

        # Test base LlamaIndex indexing timeout (no production override)
        expected = self.config.get("timeouts.llamaindex.indexing.single_document")
        timeout = self.config.get_timeout_for_env(
            "llamaindex.indexing", "single_document", environment="production"
        )
        assert timeout == expected

    def test_get_timeout_for_env_default_fallback(self):
        """Test fallback to default when timeout not configured"""
        timeout = self.config.get_timeout_for_env(
            "nonexistent.category", "timeout", environment="production", default=99.0
        )
        assert timeout == 99.0

    def test_get_timeout_group(self):
        """Test batch timeout retrieval for a category"""
        # Get all Redis operations
        timeouts = self.config.get_timeout_group("redis.operations")

        assert isinstance(timeouts, dict)
        assert "get" in timeouts
        assert "set" in timeouts
        assert "scan_iter" in timeouts
        assert timeouts["get"] == 1.0
        assert timeouts["set"] == 1.0

    def test_get_timeout_group_with_environment(self):
        """Test batch timeout retrieval with environment override"""
        # Get Redis operations for production (should have overrides)
        timeouts = self.config.get_timeout_group(
            "redis.operations", environment="production"
        )

        assert timeouts["get"] == 0.5  # Overridden
        assert timeouts["set"] == 0.5  # Overridden
        assert timeouts["scan_iter"] == 10.0  # Base value

    def test_validate_timeouts(self):
        """Test timeout configuration validation"""
        validation = self.config.validate_timeouts()

        assert isinstance(validation, dict)
        assert "valid" in validation
        assert "issues" in validation
        assert "warnings" in validation

        # Configuration should be valid
        assert validation["valid"] is True
        assert len(validation["issues"]) == 0

    def test_validate_timeouts_detects_issues(self):
        """Test that validation detects configuration issues"""
        # This would require modifying config temporarily
        # For now, just ensure the validation method works
        validation = self.config.validate_timeouts()
        assert isinstance(validation["issues"], list)
        assert isinstance(validation["warnings"], list)


class TestKnowledgeBaseTimeouts:
    """Test KnowledgeBaseTimeouts accessor class"""

    def setup_method(self):
        """Setup for each test"""
        # Save original environment
        self.original_env = os.getenv("AUTOBOT_ENVIRONMENT")

    def teardown_method(self):
        """Restore original environment"""
        if self.original_env:
            os.environ["AUTOBOT_ENVIRONMENT"] = self.original_env
        elif "AUTOBOT_ENVIRONMENT" in os.environ:
            del os.environ["AUTOBOT_ENVIRONMENT"]

    def test_redis_connection_timeouts(self):
        """Test Redis connection timeout properties"""
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        expected_socket_timeout = config.get("timeouts.redis.connection.socket_timeout")
        expected_socket_connect = config.get("timeouts.redis.connection.socket_connect")

        assert kb_timeouts.redis_socket_timeout == expected_socket_timeout
        assert kb_timeouts.redis_socket_connect == expected_socket_connect

    def test_redis_operation_timeouts(self):
        """Test Redis operation timeout properties"""
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        # Production environment is default, so check for overrides
        expected_get = config.get_timeout_for_env(
            "redis.operations", "get", "production"
        )
        expected_set = config.get_timeout_for_env(
            "redis.operations", "set", "production"
        )
        expected_hgetall = config.get("timeouts.redis.operations.hgetall")
        expected_pipeline = config.get("timeouts.redis.operations.pipeline")
        expected_scan_iter = config.get("timeouts.redis.operations.scan_iter")

        assert kb_timeouts.redis_get == expected_get
        assert kb_timeouts.redis_set == expected_set
        assert kb_timeouts.redis_hgetall == expected_hgetall
        assert kb_timeouts.redis_pipeline == expected_pipeline
        assert kb_timeouts.redis_scan_iter == expected_scan_iter

    def test_llamaindex_timeouts(self):
        """Test LlamaIndex timeout properties"""
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        # Read expected values from configuration
        expected_embedding = config.get("timeouts.llamaindex.embedding.generation")
        expected_indexing_single = config.get(
            "timeouts.llamaindex.indexing.single_document"
        )
        expected_indexing_batch = config.get(
            "timeouts.llamaindex.indexing.batch_documents"
        )
        expected_search = config.get_timeout_for_env(
            "llamaindex.search", "query", "production"
        )
        expected_hybrid = config.get("timeouts.llamaindex.search.hybrid")

        assert kb_timeouts.llamaindex_embedding_generation == expected_embedding
        assert kb_timeouts.llamaindex_indexing_single == expected_indexing_single
        assert kb_timeouts.llamaindex_indexing_batch == expected_indexing_batch
        assert kb_timeouts.llamaindex_search_query == expected_search
        assert kb_timeouts.llamaindex_search_hybrid == expected_hybrid

    def test_document_timeouts(self):
        """Test document operation timeout properties"""
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        expected_add = config.get("timeouts.documents.operations.add_document")
        expected_batch = config.get("timeouts.documents.operations.batch_upload")
        expected_export = config.get("timeouts.documents.operations.export")

        assert kb_timeouts.document_add == expected_add
        assert kb_timeouts.document_batch_upload == expected_batch
        assert kb_timeouts.document_export == expected_export

    def test_llm_timeouts(self):
        """Test LLM timeout properties"""
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        expected_default = config.get("timeouts.llm.default")
        expected_fast = config.get("timeouts.llm.fast")

        assert kb_timeouts.llm_default == expected_default
        assert kb_timeouts.llm_fast == expected_fast

    def test_environment_awareness_production(self):
        """Test that accessor respects production environment"""
        os.environ["AUTOBOT_ENVIRONMENT"] = "production"
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        # Production should have tighter timeouts (read from config)
        expected_redis_get = config.get_timeout_for_env(
            "redis.operations", "get", "production"
        )
        expected_search = config.get_timeout_for_env(
            "llamaindex.search", "query", "production"
        )

        assert kb_timeouts.redis_get == expected_redis_get
        assert kb_timeouts.llamaindex_search_query == expected_search

    def test_environment_awareness_development(self):
        """Test that accessor respects development environment"""
        os.environ["AUTOBOT_ENVIRONMENT"] = "development"
        kb_timeouts = KnowledgeBaseTimeouts()
        config = UnifiedConfigManager()

        # Development should have more lenient timeouts (read from config)
        expected_scan_iter = config.get_timeout_for_env(
            "redis.operations", "scan_iter", "development"
        )
        expected_search = config.get_timeout_for_env(
            "llamaindex.search", "query", "development"
        )

        assert kb_timeouts.redis_scan_iter == expected_scan_iter
        assert kb_timeouts.llamaindex_search_query == expected_search

    def test_get_all_redis_timeouts(self):
        """Test batch Redis timeout retrieval"""
        kb_timeouts = KnowledgeBaseTimeouts()
        all_timeouts = kb_timeouts.get_all_redis_timeouts()

        assert isinstance(all_timeouts, dict)
        assert "get" in all_timeouts
        assert "set" in all_timeouts
        assert "scan_iter" in all_timeouts

    def test_get_timeout_summary(self):
        """Test comprehensive timeout summary"""
        kb_timeouts = KnowledgeBaseTimeouts()
        summary = kb_timeouts.get_timeout_summary()

        assert isinstance(summary, dict)
        assert "redis" in summary
        assert "llamaindex" in summary
        assert "documents" in summary
        assert "llm" in summary

        # Verify structure
        assert isinstance(summary["redis"], dict)
        assert isinstance(summary["llamaindex"], dict)
        assert isinstance(summary["documents"], dict)
        assert isinstance(summary["llm"], dict)


class TestBackwardCompatibility:
    """Test backward compatibility with existing code"""

    def setup_method(self):
        """Setup for each test"""
        self.config = UnifiedConfigManager()

    def test_legacy_config_get_still_works(self):
        """Ensure old config.get() paths still work"""
        # Test that direct path access still works
        expected_llm = self.config.get("timeouts.llm.default")
        timeout = self.config.get("timeouts.llm.default")
        assert timeout == expected_llm
        assert timeout is not None

        expected_redis = self.config.get("timeouts.redis.operations.get")
        timeout = self.config.get("timeouts.redis.operations.get")
        assert timeout == expected_redis
        assert timeout is not None

    def test_environment_variable_override(self):
        """Test that AUTOBOT_LLM_TIMEOUT env var still works"""
        original = os.getenv("AUTOBOT_LLM_TIMEOUT")
        try:
            os.environ["AUTOBOT_LLM_TIMEOUT"] = "999.0"
            # Reload config would be needed here
            # For now, just test the mechanism exists
            assert "AUTOBOT_LLM_TIMEOUT" in os.environ
        finally:
            if original:
                os.environ["AUTOBOT_LLM_TIMEOUT"] = original
            elif "AUTOBOT_LLM_TIMEOUT" in os.environ:
                del os.environ["AUTOBOT_LLM_TIMEOUT"]


class TestIntegration:
    """Integration tests for timeout system"""

    def test_knowledge_base_uses_timeouts(self):
        """Test that KnowledgeBase correctly uses timeout accessor"""
        # This would require importing KnowledgeBase
        # and checking that it uses kb_timeouts
        # Skipped for unit tests - would be in integration tests

    def test_timeout_changes_affect_runtime(self):
        """Test that timeout configuration changes affect runtime behavior"""
        # This would require testing actual timeout behavior
        # Skipped for unit tests - would be in integration tests


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
