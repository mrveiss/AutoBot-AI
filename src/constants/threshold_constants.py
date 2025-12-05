# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threshold and Timing Constants for AutoBot

Issue #318: Centralized constants to replace magic numbers throughout the codebase.
This module contains threshold values, timing constants, and configuration values
that were previously hardcoded.
"""


class SecurityThresholds:
    """Security risk evaluation thresholds."""

    # Risk scoring thresholds
    HIGH_RISK_THRESHOLD = 0.3  # Commands with risk > 0.3 are high risk
    BLOCK_THRESHOLD = 0.7  # Commands with risk > 0.7 should be blocked


class AgentThresholds:
    """Agent response evaluation thresholds."""

    # Response quality thresholds
    QUALITY_THRESHOLD = 0.7  # Minimum quality score for good response
    RELEVANCE_THRESHOLD = 0.8  # Minimum relevance score required

    # Multi-agent consensus
    CONSENSUS_THRESHOLD = 0.8  # Minimum agreement level for consensus

    # Scoring weights (must sum to 1.0)
    QUALITY_WEIGHT = 0.4
    RELEVANCE_WEIGHT = 0.3
    CONSISTENCY_WEIGHT = 0.3


class WorkflowThresholds:
    """Workflow step execution thresholds."""

    SAFETY_THRESHOLD = 0.7  # Minimum safety score required
    QUALITY_THRESHOLD = 0.6  # Minimum quality score required


class ComputerVisionThresholds:
    """Computer vision and UI element detection thresholds."""

    SEARCH_RESULT_LIMIT = 10
    SIMILARITY_THRESHOLD = 0.7  # UI element matching precision


class CircuitBreakerDefaults:
    """Circuit breaker default values for service protection."""

    # LLM service circuit breaker
    LLM_FAILURE_THRESHOLD = 3
    LLM_RECOVERY_TIMEOUT = 30.0
    LLM_TIMEOUT = 120.0  # LLM calls can be slow

    # General service circuit breaker
    DEFAULT_FAILURE_THRESHOLD = 5
    DEFAULT_RECOVERY_TIMEOUT = 60.0
    DEFAULT_TIMEOUT = 30.0


class VoiceRecognitionConfig:
    """Voice recognition system configuration."""

    ENERGY_THRESHOLD = 300
    PAUSE_THRESHOLD = 0.8
    PHRASE_THRESHOLD = 0.3


class CacheConfig:
    """Cache configuration constants."""

    # Embedding cache
    EMBEDDING_CACHE_MAX_SIZE = 1000
    EMBEDDING_CACHE_TTL_SECONDS = 3600

    # Database cache
    DATABASE_CACHE_SIZE = 10000


class KnowledgeSyncConfig:
    """Knowledge synchronization configuration."""

    MAX_CONCURRENT_FILES = 4  # Parallel file processing
    CHUNK_BATCH_SIZE = 50  # GPU batch optimization


class TimingConstants:
    """Common timing values used throughout the codebase."""

    # Short delays (sub-second)
    MICRO_DELAY = 0.1
    SHORT_DELAY = 0.5
    STANDARD_DELAY = 1.0

    # Medium delays (seconds)
    MEDIUM_DELAY = 5.0
    LONG_DELAY = 10.0

    # Timeout values
    SHORT_TIMEOUT = 30
    STANDARD_TIMEOUT = 60
    LONG_TIMEOUT = 120
    VERY_LONG_TIMEOUT = 300


class RetryConfig:
    """Retry configuration constants."""

    # Common retry counts
    MIN_RETRIES = 2
    DEFAULT_RETRIES = 3
    MAX_RETRIES = 5

    # Backoff multipliers
    BACKOFF_BASE = 2.0
    BACKOFF_MAX_DELAY = 60.0


class BatchConfig:
    """Batch processing configuration."""

    # Concurrent operation limits
    DEFAULT_CONCURRENCY = 10
    HIGH_CONCURRENCY = 50
    MAX_CONCURRENCY = 100

    # Batch sizes
    SMALL_BATCH = 10
    MEDIUM_BATCH = 50
    LARGE_BATCH = 100
