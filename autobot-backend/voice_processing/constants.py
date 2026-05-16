# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing Constants

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

from autobot_shared.ssot_constants import (  # noqa: F401,F403
    APP_PATTERNS_RE,
    AUTOMATION_INTENT_PATTERNS,
    CONTEXT_DEPENDENT_INTENTS,
    DIRECTION_RE,
    HIGH_RISK_INTENTS,
    NAVIGATION_INTENT_PATTERNS,
    NUMBER_RE,
    QUERY_INTENT_PATTERNS,
    QUOTED_TEXT_RE,
    SCREEN_STATE_INTENTS,
    URL_RE,
    match_intent_from_patterns,
)
