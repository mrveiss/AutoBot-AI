# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing Constants

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

# Temporary placeholders for constants migration (Issue MVA-2185)
# These were expected to come from ssot_constants but don't exist there yet
APP_PATTERNS_RE = {}  # noqa: F401
HIGH_RISK_COMMAND_TYPES = set()  # noqa: F401
AUTOMATION_INTENT_PATTERNS = []  # noqa: F401
CONTEXT_DEPENDENT_INTENTS = []  # noqa: F401
DIRECTION_RE = None  # noqa: F401
HIGH_RISK_INTENTS = []  # noqa: F401
NAVIGATION_INTENT_PATTERNS = []  # noqa: F401
NUMBER_RE = None  # noqa: F401
QUERY_INTENT_PATTERNS = []  # noqa: F401
QUOTED_TEXT_RE = None  # noqa: F401
SCREEN_STATE_INTENTS = []  # noqa: F401
URL_RE = None  # noqa: F401


def match_intent_from_patterns(text, patterns):  # noqa: F401
    """Placeholder for match_intent_from_patterns."""
    return None
