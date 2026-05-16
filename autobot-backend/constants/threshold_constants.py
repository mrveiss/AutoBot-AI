# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threshold and Timing Constants for AutoBot

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

from autobot_shared.ssot_constants import (  # noqa: F401,F403
    SecurityThresholds,
    AgentThresholds,
    WorkflowThresholds,
    ComputerVisionThresholds,
    CircuitBreakerDefaults,
    VoiceRecognitionConfig,
    CacheConfig,
    KnowledgeSyncConfig,
    TimingConstants,
    exponential_backoff_delay,
    RetryConfig,
    BatchConfig,
    LLMDefaults,
    ResourceThresholds,
    AnalyticsConfig,
    HardwareAcceleratorConfig,
    WorkflowConfig,
    ServiceDiscoveryConfig,
    StringParsingConstants,
    FileWatcherConfig,
    QueryDefaults,
    CategoryDefaults,
    WorkStealingConfig,
    ProtocolDefaults,
)
