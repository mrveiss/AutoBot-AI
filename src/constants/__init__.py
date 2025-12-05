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
from .threshold_constants import (  # Issue #318: Threshold and timing constants
    AgentThresholds,
    BatchConfig,
    CacheConfig,
    CircuitBreakerDefaults,
    ComputerVisionThresholds,
    KnowledgeSyncConfig,
    RetryConfig,
    SecurityThresholds,
    TimingConstants,
    VoiceRecognitionConfig,
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
]
