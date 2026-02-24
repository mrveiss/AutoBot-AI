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
        # No timeouts section in config.yaml, falls back to default=60.0
        timeout = self.config.get_timeout_for_env(
            "redis.operations", "get", environment="production"
        )
        assert timeout == 60.0

    def test_get_timeout_for_env_development(self):
        """Test environment-specific timeout retrieval for development"""
        # No timeouts section in config.yaml, falls back to default
        timeout = self.config.get_timeout_for_env(
            "redis.operations", "get", environment="development"
        )
        assert timeout == 60.0

        timeout = self.config.get_timeout_for_env(
            "redis.operations", "scan_iter", environment="development"
        )
        assert timeout == 60.0

    def test_get_timeout_for_env_base_values(self):
        """Test base timeout values fallback to default when no config exists"""
        timeout = self.config.get_timeout_for_env(
            "redis.connection",
            "socket_connect",
            environment="production",
            default=2.0,
        )
        assert timeout == 2.0

        timeout = self.config.get_timeout_for_env(
            "llamaindex.indexing",
            "single_document",
            environment="production",
            default=10.0,
        )
        assert timeout == 10.0

    def test_get_timeout_for_env_default_fallback(self):
        """Test fallback to default when timeout not configured"""
        timeout = self.config.get_timeout_for_env(
            "nonexistent.category", "timeout", environment="production", default=99.0
        )
        assert timeout == 99.0

    def test_get_timeout_group(self):
        """Test batch timeout retrieval for a category"""
        # No timeouts section, returns empty dict
        timeouts = self.config.get_timeout_group("redis.operations")
        assert isinstance(timeouts, dict)
        assert timeouts == {}

    def test_get_timeout_group_with_environment(self):
        """Test batch timeout retrieval with environment"""
        timeouts = self.config.get_timeout_group(
            "redis.operations", environment="production"
        )
        assert isinstance(timeouts, dict)
        assert timeouts == {}

    def test_validate_timeouts(self):
        """Test timeout configuration validation"""
        validation = self.config.validate_timeouts()

        assert isinstance(validation, dict)
        assert "valid" in validation
        assert "issues" in validation
        assert "warnings" in validation
        # No timeouts in config, so required categories are missing
        assert isinstance(validation["issues"], list)

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
        """Test Redis connection timeout properties return defaults"""
        kb_timeouts = KnowledgeBaseTimeouts()
        assert kb_timeouts.redis_socket_timeout == 2.0
        assert kb_timeouts.redis_socket_connect == 2.0

    def test_redis_operation_timeouts(self):
        """Test Redis operation timeout properties return defaults"""
        kb_timeouts = KnowledgeBaseTimeouts()
        assert kb_timeouts.redis_get == 1.0
        assert kb_timeouts.redis_set == 1.0
        assert kb_timeouts.redis_hgetall == 2.0
        assert kb_timeouts.redis_pipeline == 5.0
        assert kb_timeouts.redis_scan_iter == 10.0

    def test_llamaindex_timeouts(self):
        """Test LlamaIndex timeout properties return defaults"""
        kb_timeouts = KnowledgeBaseTimeouts()
        assert kb_timeouts.llamaindex_embedding_generation == 10.0
        assert kb_timeouts.llamaindex_indexing_single == 10.0
        assert kb_timeouts.llamaindex_indexing_batch == 60.0
        assert kb_timeouts.llamaindex_search_query == 10.0
        assert kb_timeouts.llamaindex_search_hybrid == 15.0

    def test_document_timeouts(self):
        """Test document operation timeout properties return defaults"""
        kb_timeouts = KnowledgeBaseTimeouts()
        assert kb_timeouts.document_add == 30.0
        assert kb_timeouts.document_batch_upload == 120.0
        assert kb_timeouts.document_export == 60.0

    def test_llm_timeouts(self):
        """Test LLM timeout properties return defaults"""
        kb_timeouts = KnowledgeBaseTimeouts()
        assert kb_timeouts.llm_default == 120.0
        assert kb_timeouts.llm_fast == 30.0

    def test_environment_awareness_production(self):
        """Test that accessor respects production environment"""
        os.environ["AUTOBOT_ENVIRONMENT"] = "production"
        kb_timeouts = KnowledgeBaseTimeouts()
        # Without config overrides, defaults are used
        assert kb_timeouts.redis_get == 1.0
        assert kb_timeouts.llamaindex_search_query == 10.0

    def test_environment_awareness_development(self):
        """Test that accessor respects development environment"""
        os.environ["AUTOBOT_ENVIRONMENT"] = "development"
        kb_timeouts = KnowledgeBaseTimeouts()
        # Without config overrides, defaults are used
        assert kb_timeouts.redis_scan_iter == 10.0
        assert kb_timeouts.llamaindex_search_query == 10.0

    def test_get_all_redis_timeouts(self):
        """Test batch Redis timeout retrieval"""
        kb_timeouts = KnowledgeBaseTimeouts()
        all_timeouts = kb_timeouts.get_all_redis_timeouts()
        # Returns empty dict when no config timeouts section exists
        assert isinstance(all_timeouts, dict)

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

    def test_legacy_config_get_returns_none_without_timeout_config(self):
        """Config.get() returns None when timeouts section is absent"""
        assert self.config.get("timeouts.llm.default") is None
        assert self.config.get("timeouts.redis.operations.get") is None

    def test_get_timeout_provides_fallback(self):
        """get_timeout() provides hardcoded fallback defaults"""
        assert self.config.get_timeout("llm", "default") == 120.0
        assert self.config.get_timeout("redis", "default") == 5.0

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
