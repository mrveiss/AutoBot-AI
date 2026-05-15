# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context-Aware Decision Types and Constants

Defines enums, constants, and type definitions for the context-aware
decision making system.

Part of Issue #381 - God Class Refactoring
"""

from enum import Enum
from typing import Set

# Module-level constants for O(1) lookups (Issue #326)
HIGH_RESOURCE_CONSTRAINT_TYPES: Set[str] = {"high_cpu_usage", "high_memory_usage"}
MITIGATION_REQUIRED_RISK_LEVELS: Set[str] = {"medium", "high"}


class DecisionType(Enum):
    """Types of decisions the system can make."""

    AUTOMATION_ACTION = "automation_action"
    NAVIGATION_CHOICE = "navigation_choice"
    TASK_PRIORITIZATION = "task_prioritization"
    RISK_ASSESSMENT = "risk_assessment"
    CONTEXT_SWITCHING = "context_switching"
    RESOURCE_ALLOCATION = "resource_allocation"
    HUMAN_ESCALATION = "human_escalation"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"


class ConfidenceLevel(Enum):
    """Confidence levels for decision making."""

    VERY_HIGH = "very_high"  # > 0.9
    HIGH = "high"  # 0.7 - 0.9
    MEDIUM = "medium"  # 0.5 - 0.7
    LOW = "low"  # 0.3 - 0.5
    VERY_LOW = "very_low"  # < 0.3


class ContextType(Enum):
    """Types of context information."""

    VISUAL = "visual"
    AUDIO = "audio"
    TEXTUAL = "textual"
    HISTORICAL = "historical"
    ENVIRONMENTAL = "environmental"
    USER_PREFERENCE = "user_preference"
    SYSTEM_STATE = "system_state"
    TASK_CONTEXT = "task_context"


# High-risk actions that always require approval
HIGH_RISK_ACTIONS: Set[str] = {
    "shutdown",
    "delete",
    "uninstall",
    "modify_system_settings",
}

# Confidence thresholds
CONFIDENCE_THRESHOLDS = {
    "very_high": 0.9,
    "high": 0.7,
    "medium": 0.5,
    "low": 0.3,
}

# Default user preferences
DEFAULT_USER_PREFERENCES = {
    "automation_level": "high",
    "confirmation_required": False,
    "risk_tolerance": "medium",
    "preferred_interaction_mode": "autonomous",
    "response_time_priority": "speed",
    "accuracy_vs_speed": "balanced",
}
