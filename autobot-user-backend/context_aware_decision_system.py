# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context-Aware Decision Making System - Facade Module

Intelligent decision making that considers multi-modal context,
history, and environmental factors.

Part of Issue #381 - God Class Refactoring
This module now serves as a facade that re-exports from the
context_aware_decision package for backward compatibility.

Original module: 1,591 lines
New facade: ~100 lines (94% reduction)
"""

# Re-export all public API from the package for backward compatibility
from context_aware_decision import (
    # Types and enums
    ConfidenceLevel,
    ContextType,
    DecisionType,
    HIGH_RESOURCE_CONSTRAINT_TYPES,
    HIGH_RISK_ACTIONS,
    MITIGATION_REQUIRED_RISK_LEVELS,
    CONFIDENCE_THRESHOLDS,
    DEFAULT_USER_PREFERENCES,
    # Time provider
    TimeProvider,
    # Data models
    ContextElement,
    Decision,
    DecisionContext,
    # Collectors
    AudioContextCollector,
    ContextCollector,
    SystemContextCollector,
    VisualContextCollector,
    # Decision engine
    DecisionEngine,
    # Main system
    ContextAwareDecisionSystem,
    # Global instance
    context_aware_decision_system,
)

__all__ = [
    # Types and enums
    "ConfidenceLevel",
    "ContextType",
    "DecisionType",
    "HIGH_RESOURCE_CONSTRAINT_TYPES",
    "HIGH_RISK_ACTIONS",
    "MITIGATION_REQUIRED_RISK_LEVELS",
    "CONFIDENCE_THRESHOLDS",
    "DEFAULT_USER_PREFERENCES",
    # Time provider
    "TimeProvider",
    # Data models
    "ContextElement",
    "Decision",
    "DecisionContext",
    # Collectors
    "AudioContextCollector",
    "ContextCollector",
    "SystemContextCollector",
    "VisualContextCollector",
    # Decision engine
    "DecisionEngine",
    # Main system
    "ContextAwareDecisionSystem",
    # Global instance
    "context_aware_decision_system",
]
