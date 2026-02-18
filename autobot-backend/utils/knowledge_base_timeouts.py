# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Timeout Configuration Accessor

Provides convenient access to centralized timeout configuration
for knowledge_base.py operations.

Part of KB-ASYNC-014: Timeout Configuration Centralization
"""

import os
from typing import Dict

from config import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()


class KnowledgeBaseTimeouts:
    """Accessor class for knowledge base timeout configuration"""

    def __init__(self):
        """Initialize timeout accessor with current environment"""
        self.environment = os.getenv("AUTOBOT_ENVIRONMENT", "production")
        self._config = config

    # Redis Connection Timeouts
    @property
    def redis_socket_timeout(self) -> float:
        """Timeout for Redis socket operations"""
        return self._config.get_timeout_for_env(
            "redis.connection",
            "socket_timeout",
            environment=self.environment,
            default=2.0,
        )

    @property
    def redis_socket_connect(self) -> float:
        """Timeout for Redis connection establishment"""
        return self._config.get_timeout_for_env(
            "redis.connection",
            "socket_connect",
            environment=self.environment,
            default=2.0,
        )

    # Redis Operation Timeouts
    @property
    def redis_get(self) -> float:
        """Timeout for Redis GET operations"""
        return self._config.get_timeout_for_env(
            "redis.operations", "get", environment=self.environment, default=1.0
        )

    @property
    def redis_set(self) -> float:
        """Timeout for Redis SET operations"""
        return self._config.get_timeout_for_env(
            "redis.operations", "set", environment=self.environment, default=1.0
        )

    @property
    def redis_hgetall(self) -> float:
        """Timeout for Redis HGETALL operations"""
        return self._config.get_timeout_for_env(
            "redis.operations", "hgetall", environment=self.environment, default=2.0
        )

    @property
    def redis_pipeline(self) -> float:
        """Timeout for Redis pipeline operations"""
        return self._config.get_timeout_for_env(
            "redis.operations", "pipeline", environment=self.environment, default=5.0
        )

    @property
    def redis_scan_iter(self) -> float:
        """Timeout for Redis SCAN_ITER operations"""
        return self._config.get_timeout_for_env(
            "redis.operations", "scan_iter", environment=self.environment, default=10.0
        )

    @property
    def redis_ft_info(self) -> float:
        """Timeout for Redis FT.INFO operations"""
        return self._config.get_timeout_for_env(
            "redis.operations", "ft_info", environment=self.environment, default=2.0
        )

    # LlamaIndex Operation Timeouts
    @property
    def llamaindex_embedding_generation(self) -> float:
        """Timeout for LlamaIndex embedding generation"""
        return self._config.get_timeout_for_env(
            "llamaindex.embedding",
            "generation",
            environment=self.environment,
            default=10.0,
        )

    @property
    def llamaindex_indexing_single(self) -> float:
        """Timeout for indexing single document"""
        return self._config.get_timeout_for_env(
            "llamaindex.indexing",
            "single_document",
            environment=self.environment,
            default=10.0,
        )

    @property
    def llamaindex_indexing_batch(self) -> float:
        """Timeout for batch document indexing"""
        return self._config.get_timeout_for_env(
            "llamaindex.indexing",
            "batch_documents",
            environment=self.environment,
            default=60.0,
        )

    @property
    def llamaindex_search_query(self) -> float:
        """Timeout for semantic search queries"""
        return self._config.get_timeout_for_env(
            "llamaindex.search", "query", environment=self.environment, default=10.0
        )

    @property
    def llamaindex_search_hybrid(self) -> float:
        """Timeout for hybrid search operations"""
        return self._config.get_timeout_for_env(
            "llamaindex.search", "hybrid", environment=self.environment, default=15.0
        )

    # Document Operation Timeouts
    @property
    def document_add(self) -> float:
        """Timeout for adding a document"""
        return self._config.get_timeout_for_env(
            "documents.operations",
            "add_document",
            environment=self.environment,
            default=30.0,
        )

    @property
    def document_batch_upload(self) -> float:
        """Timeout for batch document upload"""
        return self._config.get_timeout_for_env(
            "documents.operations",
            "batch_upload",
            environment=self.environment,
            default=120.0,
        )

    @property
    def document_export(self) -> float:
        """Timeout for knowledge base export"""
        return self._config.get_timeout_for_env(
            "documents.operations", "export", environment=self.environment, default=60.0
        )

    # LLM Operation Timeouts
    @property
    def llm_default(self) -> float:
        """Default LLM operation timeout"""
        return self._config.get_timeout_for_env(
            "llm", "default", environment=self.environment, default=120.0
        )

    @property
    def llm_fast(self) -> float:
        """Fast LLM operation timeout"""
        return self._config.get_timeout_for_env(
            "llm", "fast", environment=self.environment, default=30.0
        )

    # Convenience Methods
    def get_all_redis_timeouts(self) -> Dict[str, float]:
        """Get all Redis operation timeouts"""
        return self._config.get_timeout_group(
            "redis.operations", environment=self.environment
        )

    def get_all_llamaindex_timeouts(self) -> Dict[str, float]:
        """Get all LlamaIndex operation timeouts"""
        indexing = self._config.get_timeout_group(
            "llamaindex.indexing", environment=self.environment
        )
        search = self._config.get_timeout_group(
            "llamaindex.search", environment=self.environment
        )
        return {**indexing, **search}

    def get_timeout_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary of all knowledge base timeouts"""
        return {
            "redis": self.get_all_redis_timeouts(),
            "llamaindex": self.get_all_llamaindex_timeouts(),
            "documents": self._config.get_timeout_group(
                "documents.operations", environment=self.environment
            ),
            "llm": {"default": self.llm_default, "fast": self.llm_fast},
        }


# Create singleton instance for convenient import
kb_timeouts = KnowledgeBaseTimeouts()
