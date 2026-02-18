# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Constants Package
========================

Centralized constants to eliminate hardcoded values throughout the codebase.
"""

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
from .threshold_constants import (
    CategoryDefaults,  # Issue #694: Category and type defaults
)
from .threshold_constants import (
    ProtocolDefaults,  # Issue #694: Protocol and endpoint defaults
)
from .threshold_constants import (
    QueryDefaults,  # Issue #694: Search and pagination defaults
)
from .threshold_constants import (
    StringParsingConstants,  # Issue #380: Centralized string parsing
)
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
]
