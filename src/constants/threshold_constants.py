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
    DEFAULT_SUCCESS_THRESHOLD = 3  # Successes to close circuit from half-open

    # Database service circuit breaker
    DATABASE_FAILURE_THRESHOLD = 5
    DATABASE_RECOVERY_TIMEOUT = 15.0
    DATABASE_TIMEOUT = 10.0
    DATABASE_SLOW_CALL_THRESHOLD = 2.0  # Database calls should be fast

    # Network service circuit breaker
    NETWORK_FAILURE_THRESHOLD = 3
    NETWORK_RECOVERY_TIMEOUT = 20.0
    NETWORK_TIMEOUT = 15.0

    # Performance monitoring
    SLOW_CALL_THRESHOLD = 10.0  # Seconds - what constitutes a slow call
    SLOW_CALL_RATE_THRESHOLD = 0.5  # 50% of calls being slow opens circuit
    MIN_CALLS_FOR_EVALUATION = 10  # Minimum calls before evaluating performance
    RECENT_CALLS_WINDOW = 60.0  # Seconds - window for recent call analysis
    PERFORMANCE_WINDOW = 300.0  # Seconds (5 minutes) - window for performance metrics
    QUANTILE_SAMPLE_SIZE = 20  # Minimum samples for p95 calculation
    MAX_HISTORY_SIZE = 100  # Maximum call records to keep


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
    POLL_INTERVAL = 0.01  # Short polling loop delay to prevent CPU spinning
    STREAMING_CHUNK_DELAY = 0.05  # Delay between streaming chunks for UX
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

    # Long interval values
    HOURLY_INTERVAL = 3600  # 1 hour in seconds

    # Error recovery
    ERROR_RECOVERY_DELAY = 5.0  # Standard delay after errors
    ERROR_RECOVERY_LONG_DELAY = 30.0  # Extended delay after errors in monitoring loops

    # Service lifecycle
    SERVICE_STARTUP_DELAY = 2.0  # Wait for service to initialize after start/stop/restart
    KB_INIT_DELAY = 3.0  # Wait for knowledge base async initialization


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


class LLMDefaults:
    """Default values for LLM inference operations."""

    # Token limits - Minimal
    MINIMAL_MAX_TOKENS = 10  # Connection tests, simple checks
    SHORT_MAX_TOKENS = 50  # Short classification responses
    COMMAND_MAX_TOKENS = 75  # Command extraction
    DEFAULT_MAX_TOKENS = 100  # Default for simple operations
    RETRIEVAL_MAX_TOKENS = 150  # Knowledge retrieval responses
    ANALYSIS_MAX_TOKENS = 200  # Analysis operations
    CONCISE_MAX_TOKENS = 256  # Commands and concise responses

    # Token limits - Standard
    STANDARD_MAX_TOKENS = 500  # Standard chat responses
    CHAT_MAX_TOKENS = 512  # Chat agent responses
    ENRICHED_MAX_TOKENS = 1000  # Enriched/multi-context responses

    # Token limits - Long
    SYNTHESIS_MAX_TOKENS = 1024  # RAG synthesis responses
    EXTENDED_MAX_TOKENS = 1500  # Extended synthesis
    LONG_MAX_TOKENS = 2048  # Long form responses
    VERY_LONG_MAX_TOKENS = 4000  # Comprehensive analysis

    # Sampling parameters
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_TOP_P = 0.9

    # Concurrency
    DEFAULT_CONCURRENT_WORKERS = 3


class ResourceThresholds:
    """System resource monitoring thresholds."""

    # Memory thresholds (as percentage, 0.0-1.0)
    MEMORY_WARNING_THRESHOLD = 0.8  # 80% - trigger warning
    MEMORY_CRITICAL_THRESHOLD = 0.9  # 90% - trigger critical alert

    # CPU thresholds
    CPU_HIGH_THRESHOLD = 0.9  # 90% - high usage
    CPU_OPTIMAL_MAX = 0.2  # 20% - low usage / good headroom

    # GPU thresholds (as percentage, 0.0-100.0)
    GPU_LOW_UTILIZATION = 0.2  # 20% - underutilized
    GPU_RECOMMENDATION_THRESHOLD = 0.3  # 30% - recommend optimization
    GPU_SATURATED = 0.95  # 95% - saturated
    GPU_BUSY_THRESHOLD = 80.0  # 80% - GPU considered busy
    GPU_MODERATE_THRESHOLD = 70.0  # 70% - moderate utilization threshold
    GPU_AVAILABLE_THRESHOLD = 60.0  # 60% - NPU can handle if GPU above this

    # NPU thresholds (as percentage, 0.0-100.0)
    NPU_BUSY_THRESHOLD = 80.0  # 80% - NPU considered busy
    NPU_AVAILABLE_THRESHOLD = 60.0  # 60% - NPU can accept moderate tasks

    # CPU core thresholds
    HIGH_CORE_COUNT = 16  # Systems with more cores benefit from parallel optimization


class AnalyticsConfig:
    """Code analytics and bug prediction configuration constants."""

    # Bug prediction timeouts (seconds)
    BUG_PREDICTION_TIMEOUT = 120.0  # Extended timeout for large codebases
    DUPLICATE_DETECTION_TIMEOUT = 120.0  # Timeout for duplicate code analysis (increased from 60s)

    # Analysis file limits (0 = no limit, scan all files)
    BUG_PREDICTION_FILE_LIMIT = 0  # No limit on files to analyze
    DUPLICATE_DETECTION_FILE_LIMIT = 0  # No limit on files to scan

    # Similarity thresholds
    DUPLICATE_MIN_SIMILARITY = 0.5  # Minimum similarity (50%) to report
    SEMANTIC_MIN_SIMILARITY = 0.6  # Minimum for semantic matches

    # Report limits
    TOP_HIGH_RISK_FILES_LIMIT = 10  # Max high-risk files to show in report
    API_ENDPOINT_LIST_LIMIT = 20  # Max API endpoints to show

    # Cache TTLs (seconds)
    BUG_PREDICTION_CACHE_TTL = 1800  # 30 minute cache
    DUPLICATE_DETECTION_CACHE_TTL = 3600  # 1 hour cache


class HardwareAcceleratorConfig:
    """Hardware accelerator configuration constants."""

    # NPU device thresholds
    NPU_MAX_MODEL_SIZE_MB = 2000  # NPU handles < 2GB models
    NPU_MAX_RESPONSE_TIME_S = 2.0  # NPU for < 2s tasks
    NPU_BASE_TEMPERATURE_C = 45.0  # Base temperature for NPU
    NPU_TEMP_UTILIZATION_FACTOR = 0.3  # Temperature increase per utilization %
    NPU_BASE_POWER_W = 2.0  # Base power consumption
    NPU_MAX_POWER_W = 10.0  # 2-10W range (delta = 8W)
    NPU_MEMORY_MB = 1024.0  # NPU memory estimation
    NPU_UTILIZATION_PER_MODEL = 25.0  # Estimated utilization per loaded model

    # Monitoring
    HARDWARE_CHECK_INTERVAL_S = 30  # Hardware check interval in seconds

    # Model dimensions
    UNIFIED_EMBEDDING_DIM = 512  # Common embedding dimension
    MINILM_OUTPUT_DIM = 384  # MiniLM output dimension
    CLIP_OUTPUT_DIM = 512  # CLIP output dimension
    WAV2VEC_OUTPUT_DIM = 768  # Wav2Vec2 output dimension

    # Task complexity thresholds
    TEXT_LIGHTWEIGHT_LENGTH = 500  # Text length for lightweight task
    TEXT_MODERATE_LENGTH = 2000  # Text length for moderate task
    DOC_LIGHTWEIGHT_COUNT = 100  # Document count for lightweight search
    DOC_MODERATE_COUNT = 1000  # Document count for moderate search

    # Performance cap
    PERFORMANCE_FACTOR_CAP = 2.0  # Cap at 2x base duration


class WorkflowConfig:
    """Workflow scheduler configuration constants."""

    # Queue defaults
    DEFAULT_MAX_CONCURRENT = 3  # Maximum concurrent workflow executions

    # Scheduler timing
    SCHEDULER_CHECK_INTERVAL_S = 10  # Check scheduler every 10 seconds
    SCHEDULER_ERROR_BACKOFF_S = 30  # Back off on scheduler error

    # Priority scoring
    PRIORITY_BASE_MULTIPLIER = 100  # Base score multiplier for priority
    MAX_OVERDUE_BONUS = 50  # Maximum priority bonus for overdue workflows
    OVERDUE_BONUS_RATE = 0.1  # Priority bonus per overdue minute
    DEPENDENCY_PENALTY = 0.9  # Priority reduction when dependencies not met

    # Duration thresholds
    DEFAULT_ESTIMATED_DURATION_MIN = 30  # Default workflow duration estimate
    DEFAULT_TIMEOUT_MIN = 120  # Default workflow timeout
    MIN_DURATION_FACTOR = 0.5  # Minimum duration factor for priority

    # Complexity multipliers
    COMPLEXITY_SIMPLE = 0.8
    COMPLEXITY_RESEARCH = 1.0
    COMPLEXITY_INSTALL = 1.1
    COMPLEXITY_COMPLEX = 1.2
    COMPLEXITY_SECURITY_SCAN = 1.3


class ServiceDiscoveryConfig:
    """Service discovery and health monitoring configuration."""

    # Health check intervals
    HEALTH_CHECK_INTERVAL_S = 30  # Default health check interval
    CIRCUIT_BREAKER_THRESHOLD = 5  # Consecutive failures to open circuit
    CIRCUIT_BREAKER_CHECK_MULTIPLIER = 2  # Skip check if < interval * multiplier

    # Service timeouts
    FRONTEND_TIMEOUT = 10.0
    NPU_WORKER_TIMEOUT = 15.0
    REDIS_TIMEOUT = 5.0
    AI_STACK_TIMEOUT = 20.0
    BROWSER_SERVICE_TIMEOUT = 10.0
    BACKEND_TIMEOUT = 5.0
    OLLAMA_TIMEOUT = 10.0

    # Wait/retry intervals
    SERVICE_WAIT_INTERVAL_S = 2  # Check every 2 seconds when waiting for service
    CORE_SERVICES_WAIT_INTERVAL_S = 5  # Check every 5 seconds for core services
    ERROR_RECOVERY_DELAY_S = 5  # Delay after error in health monitor

    # Default wait timeouts
    DEFAULT_SERVICE_WAIT_TIMEOUT = 60.0
    CORE_SERVICES_WAIT_TIMEOUT = 120.0


class StringParsingConstants:
    """String parsing constants for boolean/truthy value detection.

    Issue #380: Centralized constants to eliminate duplicate definitions.
    These frozensets provide O(1) lookup for string parsing operations.
    """

    # Boolean string values (for strict true/false parsing)
    BOOL_STRING_VALUES = frozenset({"true", "false"})

    # Truthy string values (for flexible boolean interpretation)
    TRUTHY_STRING_VALUES = frozenset({"true", "1", "yes", "on"})

    # Falsy string values (for flexible boolean interpretation)
    FALSY_STRING_VALUES = frozenset({"false", "0", "no", "off"})


class FileWatcherConfig:
    """File watcher configuration for config file monitoring."""

    # Check intervals
    CHECK_INTERVAL_S = 1.0  # Normal check interval
    ERROR_RETRY_INTERVAL_S = 5.0  # Retry interval after error


class QueryDefaults:
    """
    Default values for search, query, and pagination operations.

    Issue #694: Consolidate duplicate magic numbers for search limits,
    pagination, and query parameters.

    Usage:
        from src.constants.threshold_constants import QueryDefaults

        limit = QueryDefaults.DEFAULT_SEARCH_LIMIT
        offset = QueryDefaults.DEFAULT_OFFSET
    """

    # Search result limits
    DEFAULT_SEARCH_LIMIT: int = 10  # Default number of search results
    DEFAULT_TOP_K: int = 10  # Default top-k for vector searches
    MAX_SEARCH_LIMIT: int = 100  # Maximum allowed search results
    EXTENDED_SEARCH_LIMIT: int = 50  # Extended search for facts/documents
    LARGE_BATCH_LIMIT: int = 100  # Large batch operations

    # Pagination
    DEFAULT_OFFSET: int = 0  # Default pagination offset
    DEFAULT_PAGE_SIZE: int = 50  # Default page size for lists
    MAX_PAGE_SIZE: int = 500  # Maximum page size

    # RAG/Knowledge base specific
    RAG_DEFAULT_RESULTS: int = 5  # Default RAG retrieval count
    RAG_MAX_RESULTS: int = 20  # Maximum RAG results per query
    KNOWLEDGE_DEFAULT_LIMIT: int = 100  # Default for knowledge base queries


class CategoryDefaults:
    """
    Default category and type values for classification.

    Issue #694: Consolidate duplicate string literals for categories,
    types, and default classifications.

    Usage:
        from src.constants.threshold_constants import CategoryDefaults

        category = CategoryDefaults.GENERAL
        search_mode = CategoryDefaults.SEARCH_MODE_HYBRID
    """

    # General categories
    GENERAL: str = "general"
    IMPORTED: str = "imported"
    UNKNOWN: str = "unknown"

    # Search modes
    SEARCH_MODE_HYBRID: str = "hybrid"
    SEARCH_MODE_SEMANTIC: str = "semantic"
    SEARCH_MODE_KEYWORD: str = "keyword"

    # Query types
    QUERY_TYPE_GENERAL: str = "general"
    QUERY_TYPE_TECHNICAL: str = "technical"
    QUERY_TYPE_CODE: str = "code"

    # Context types
    CONTEXT_TYPE_GENERAL: str = "general"
    CONTEXT_TYPE_SECURITY: str = "security"
    CONTEXT_TYPE_RESEARCH: str = "research"

    # Message roles
    ROLE_USER: str = "user"
    ROLE_ASSISTANT: str = "assistant"
    ROLE_SYSTEM: str = "system"

    # Environment modes
    MODE_DEVELOPMENT: str = "development"
    MODE_PRODUCTION: str = "production"
    MODE_TESTING: str = "testing"


class ProtocolDefaults:
    """
    Default protocol and endpoint values.

    Issue #694: Consolidate duplicate protocol strings and endpoint patterns.
    """

    # Protocols
    HTTP: str = "http"
    HTTPS: str = "https"
    WS: str = "ws"
    WSS: str = "wss"
    TCP: str = "tcp"

    # Health endpoints
    HEALTH_ENDPOINT: str = "/health"
    API_HEALTH_ENDPOINT: str = "/api/health"

    # API version
    API_VERSION: str = "1.0"
