# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Redis Key Constants for AutoBot
Single source of truth for all Redis key patterns
"""

from dataclasses import dataclass

from src.constants.network_constants import NetworkConstants


@dataclass(frozen=True)
class RedisKeyConstants:
    """Centralized Redis key patterns - NO HARDCODED KEYS"""

    # Namespace prefix
    NAMESPACE: str = "autobot"

    # Prompts and templates
    PROMPTS_FILE_STATES: str = f"{NAMESPACE}:prompts:file_states"

    # System knowledge
    SYSTEM_KNOWLEDGE_FILE_STATES: str = f"{NAMESPACE}:system_knowledge:file_states"

    # Workflow management
    WORKFLOW_CLASSIFICATION_RULES: str = f"{NAMESPACE}:workflow:classification:rules"
    WORKFLOW_CLASSIFICATION_KEYWORDS: str = (
        f"{NAMESPACE}:workflow:classification:keywords"
    )

    # Sandbox security
    SANDBOX_SECURITY_EVENTS: str = f"{NAMESPACE}:sandbox:security:events"
    SANDBOX_METRICS: str = f"{NAMESPACE}:sandbox:metrics"

    # Entity resolution
    ENTITY_MAPPINGS: str = "entity_mappings"
    ENTITY_EMBEDDINGS: str = "entity_embeddings"
    ENTITY_RESOLUTION_HISTORY: str = "entity_resolution_history"

    # System metrics
    KB_CACHE_STATS: str = "kb_cache_stats"

    # Fact extraction
    ATOMIC_FACTS_INDEX: str = "atomic_facts_index"
    FACT_EXTRACTION_HISTORY: str = "fact_extraction_history"

    # Temporal invalidation
    TEMPORAL_INVALIDATION_RULES: str = "temporal_invalidation_rules"
    TEMPORAL_INVALIDATION_HISTORY: str = "temporal_invalidation_history"
    INVALIDATED_FACTS_INDEX: str = "invalidated_facts_index"
    INVALIDATION_SCHEDULE: str = "invalidation_schedule"

    # LLM caching
    LLM_MODELS_CACHE: str = "llm_models"

    @classmethod
    def get_key(cls, key_pattern: str, *args) -> str:
        """Build Redis key with dynamic parts"""
        if args:
            return f"{key_pattern}:{':'.join(str(arg) for arg in args)}"
        return key_pattern

    @classmethod
    def get_sandbox_event_key(cls, sandbox_id: str) -> str:
        """Get sandbox security event key"""
        return f"{cls.SANDBOX_SECURITY_EVENTS}:{sandbox_id}"

    @classmethod
    def get_sandbox_metrics_key(cls, sandbox_id: str) -> str:
        """Get sandbox metrics key"""
        return f"{cls.SANDBOX_METRICS}:{sandbox_id}"


# Export constants instance
REDIS_KEY = RedisKeyConstants()
