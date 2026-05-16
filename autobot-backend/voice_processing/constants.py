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
    AUTOMATION_INTENT_PATTERNS,
    NAVIGATION_INTENT_PATTERNS,
    QUERY_INTENT_PATTERNS,
    HIGH_RISK_INTENTS,
    CONTEXT_DEPENDENT_INTENTS,
    SCREEN_STATE_INTENTS,
    NUMBER_RE,
    QUOTED_TEXT_RE,
    URL_RE,
    DIRECTION_RE,
    APP_PATTERNS_RE,
    match_intent_from_patterns,
)
