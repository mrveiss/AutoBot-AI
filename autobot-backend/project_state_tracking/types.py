# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking Types and Constants

Enums and constants for the enhanced project state tracking system.

Part of Issue #381 - God Class Refactoring
"""

from enum import Enum


class StateChangeType(Enum):
    """Types of state changes in the system"""

    PHASE_PROGRESSION = "phase_progression"
    CAPABILITY_UNLOCK = "capability_unlock"
    VALIDATION_UPDATE = "validation_update"
    CONFIGURATION_CHANGE = "configuration_change"
    SYSTEM_EVENT = "system_event"
    USER_ACTION = "user_action"
    ERROR_OCCURRED = "error_occurred"
    MILESTONE_REACHED = "milestone_reached"


class TrackingMetric(Enum):
    """Metrics to track for system evolution"""

    PHASE_COMPLETION = "phase_completion"
    CAPABILITY_COUNT = "capability_count"
    VALIDATION_SCORE = "validation_score"
    ERROR_RATE = "error_rate"
    PROGRESSION_VELOCITY = "progression_velocity"
    SYSTEM_MATURITY = "system_maturity"
    USER_INTERACTIONS = "user_interactions"
    API_CALLS = "api_calls"


# O(1) lookup optimization constants (Issue #326)
SIGNIFICANT_CHANGES = {
    StateChangeType.PHASE_PROGRESSION,
    StateChangeType.CAPABILITY_UNLOCK,
}
SIGNIFICANT_INTERACTIONS = {"login", "logout", "settings_change", "agent_switch"}

# Redis metric keys
REDIS_METRIC_KEYS = {
    "error_count": "autobot:metrics:error_count",
    "api_calls": "autobot:metrics:api_calls",
    "user_interactions": "autobot:metrics:user_interactions",
    "error_rate": "autobot:metrics:error_rate",
}
