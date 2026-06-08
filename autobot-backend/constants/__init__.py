# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Constants Package
========================

Centralized constants to eliminate hardcoded values throughout the codebase.
"""

from .api_constants import (  # Issue #3531: Centralized API path constants
    PATH_API_HEALTH,
    PATH_HEALTH,
    PATH_OLLAMA_CHAT,
    PATH_OLLAMA_GENERATE,
    PATH_OLLAMA_TAGS,
)
from .error_constants import (  # Issue #3530: Centralized error message strings
    ERR_ASSESSMENT_NOT_FOUND,
    ERR_CONNECTOR_NOT_FOUND,
    ERR_DIRECTORY_NOT_FOUND,
    ERR_EXPERIMENT_NOT_FOUND,
    ERR_FILE_NOT_FOUND,
    ERR_FILE_OR_DIR_NOT_FOUND,
    ERR_INVALID_CREDENTIALS,
    ERR_INVALID_TOKEN,
    ERR_JOB_NOT_FOUND,
    ERR_PATH_NOT_FOUND,
    ERR_SESSION_NOT_FOUND,
    ERR_TEMPLATE_NOT_FOUND,
    ERR_WORKFLOW_NOT_FOUND,
)
from .network_constants import (  # Legacy compatibility exports
    BACKEND_URL,
    FRONTEND_URL,
    LOCALHOST_IP,
    MAIN_MACHINE_IP,
    REDIS_HOST,
    DatabaseConstants,
    NetworkConfig,
    NetworkConstants,
    ServiceURLs,
    get_network_config,
)
from .path_constants import PATH
from .status_enums import (  # Issue #670: Centralized status enums
    HealthStatus,
    LLMProvider,
    OperationOutcome,
    Priority,
    Severity,
    TaskStatus,
)
from .threshold_constants import CategoryDefaults  # Issue #694: Category and type defaults
from .threshold_constants import ProtocolDefaults  # Issue #694: Protocol and endpoint defaults
from .threshold_constants import QueryDefaults  # Issue #694: Search and pagination defaults
from .threshold_constants import StringParsingConstants  # Issue #380: Centralized string parsing
from .threshold_constants import (  # Issue #318: Threshold and timing constants
    AgentThresholds,
    BatchConfig,
    CacheConfig,
    CircuitBreakerDefaults,
    ComputerVisionThresholds,
    FileWatcherConfig,
    HardwareAcceleratorConfig,
    KnowledgeSyncConfig,
    LLMDefaults,
    ResourceThresholds,
    RetryConfig,
    SecurityThresholds,
    ServiceDiscoveryConfig,
    TimingConstants,
    VoiceRecognitionConfig,
    WorkflowConfig,
    WorkflowThresholds,
)
from .ttl_constants import (  # Issue #3529: Redis TTL and timeout constants
    TIMEOUT_HTTP_DEFAULT,
    TIMEOUT_HTTP_LONG,
    TIMEOUT_TASK_ANALYSIS,
    TTL_1_HOUR,
    TTL_5_MINUTES,
    TTL_7_DAYS,
    TTL_24_HOURS,
    TTL_30_DAYS,
    TTL_90_DAYS,
    TTL_365_DAYS,
)

__all__ = [
    "NetworkConstants",
    "ServiceURLs",
    "NetworkConfig",
    "DatabaseConstants",
    "get_network_config",
    # Legacy compatibility
    "BACKEND_URL",
    "FRONTEND_URL",
    "REDIS_HOST",
    "MAIN_MACHINE_IP",
    "LOCALHOST_IP",
    # Path constants
    "PATH",
    # Issue #318: Threshold and timing constants
    "SecurityThresholds",
    "AgentThresholds",
    "WorkflowThresholds",
    "ComputerVisionThresholds",
    "CircuitBreakerDefaults",
    "VoiceRecognitionConfig",
    "CacheConfig",
    "KnowledgeSyncConfig",
    "TimingConstants",
    "RetryConfig",
    "BatchConfig",
    "LLMDefaults",
    "ResourceThresholds",
    "HardwareAcceleratorConfig",
    "WorkflowConfig",
    "ServiceDiscoveryConfig",
    "FileWatcherConfig",
    "StringParsingConstants",  # Issue #380
    # Issue #670: Status enums
    "TaskStatus",
    "Severity",
    "Priority",
    "LLMProvider",
    "OperationOutcome",
    "HealthStatus",
    # Issue #694: Query, category, and protocol defaults
    "QueryDefaults",
    "CategoryDefaults",
    "ProtocolDefaults",
    # Issue #3530: Error message string constants
    "ERR_ASSESSMENT_NOT_FOUND",
    "ERR_SESSION_NOT_FOUND",
    "ERR_FILE_NOT_FOUND",
    "ERR_DIRECTORY_NOT_FOUND",
    "ERR_FILE_OR_DIR_NOT_FOUND",
    "ERR_PATH_NOT_FOUND",
    "ERR_CONNECTOR_NOT_FOUND",
    "ERR_JOB_NOT_FOUND",
    "ERR_TEMPLATE_NOT_FOUND",
    "ERR_WORKFLOW_NOT_FOUND",
    "ERR_EXPERIMENT_NOT_FOUND",
    "ERR_INVALID_CREDENTIALS",
    "ERR_INVALID_TOKEN",
    # Issue #3531: API path constants
    "PATH_API_HEALTH",
    "PATH_HEALTH",
    "PATH_OLLAMA_CHAT",
    "PATH_OLLAMA_GENERATE",
    "PATH_OLLAMA_TAGS",
    # Issue #3529: TTL and timeout constants
    "TTL_5_MINUTES",
    "TTL_1_HOUR",
    "TTL_24_HOURS",
    "TTL_7_DAYS",
    "TTL_30_DAYS",
    "TTL_90_DAYS",
    "TTL_365_DAYS",
    "TIMEOUT_HTTP_DEFAULT",
    "TIMEOUT_HTTP_LONG",
    "TIMEOUT_TASK_ANALYSIS",
]
