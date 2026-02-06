# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context-Aware Decision Package

Provides intelligent decision making that considers multi-modal context,
history, and environmental factors.

This package refactors the original monolithic context_aware_decision_system.py
into focused, single-responsibility modules.

Part of Issue #381 - God Class Refactoring

Original module: 1,591 lines
New package: ~1,200 lines across multiple focused modules

Usage:
    from context_aware_decision import (
        ContextAwareDecisionSystem,
        DecisionType,
        ConfidenceLevel,
        context_aware_decision_system,
    )

    # Quick decision
    decision = await context_aware_decision_system.make_contextual_decision(
        DecisionType.AUTOMATION_ACTION,
        "Click login button"
    )

    # Custom instance
    system = ContextAwareDecisionSystem()
    decision = await system.make_contextual_decision(
        DecisionType.NAVIGATION_CHOICE,
        "Navigate to settings page"
    )
"""

# Types and enums
from .types import (
    ConfidenceLevel,
    ContextType,
    DecisionType,
    HIGH_RESOURCE_CONSTRAINT_TYPES,
    HIGH_RISK_ACTIONS,
    MITIGATION_REQUIRED_RISK_LEVELS,
    CONFIDENCE_THRESHOLDS,
    DEFAULT_USER_PREFERENCES,
)

# Time provider utility
from .time_provider import TimeProvider

# Data models
from .models import (
    ContextElement,
    Decision,
    DecisionContext,
)

# Collectors
from .collectors import (
    AudioContextCollector,
    ContextCollector,
    SystemContextCollector,
    VisualContextCollector,
)

# Decision engine
from .decision_engine import DecisionEngine

# Main system
from .system import ContextAwareDecisionSystem

# Global instance
context_aware_decision_system = ContextAwareDecisionSystem()

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
