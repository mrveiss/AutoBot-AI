# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing Constants

Module-level constants, pattern definitions, and pre-compiled regex patterns.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

import re

from voice_processing.types import VoiceCommand

# Issue #315: Intent extraction dispatch tables to reduce nesting
AUTOMATION_INTENT_PATTERNS = [
    (r"(?i)click", "click_element"),
    (r"(?i)type|enter", "type_text"),
    (r"(?i)open|start", "open_application"),
    (r"(?i)scroll", "scroll_page"),
]

NAVIGATION_INTENT_PATTERNS = [
    (r"(?i)go to|navigate", "navigate_to"),
    (r"(?i)back", "navigate_back"),
    (r"(?i)search", "search_content"),
]

QUERY_INTENT_PATTERNS = [
    (r"(?i)what", "what_query"),
    (r"(?i)how", "how_query"),
    (r"(?i)status", "status_query"),
]

# Issue #380: Module-level frozensets to avoid repeated list creation
HIGH_RISK_INTENTS = frozenset({
    "shutdown",
    "restart",
    "delete",
    "uninstall",
    "request_manual_control",
    "emergency",
})

CONTEXT_DEPENDENT_INTENTS = frozenset({
    "click_element",
    "type_text",
    "scroll_page",
    "navigate_to",
})

# Issue #380: Intents requiring current screen state
SCREEN_STATE_INTENTS = frozenset({"click_element", "type_text"})

# Issue #380: High-risk command types
HIGH_RISK_COMMAND_TYPES = frozenset({VoiceCommand.SYSTEM, VoiceCommand.TAKEOVER})

# Issue #380: Pre-compiled regex patterns for entity extraction
NUMBER_RE = re.compile(r"\b\d+\b")
QUOTED_TEXT_RE = re.compile(r'"([^"]*)"')
URL_RE = re.compile(r"https?://[^\s]+")
DIRECTION_RE = re.compile(r"(?i)\b(up|down|left|right|top|bottom|center)\b")
APP_PATTERNS_RE = [
    re.compile(r"(?i)\b(chrome|firefox|safari|edge|browser)\b"),
    re.compile(r"(?i)\b(notepad|word|excel|powerpoint)\b"),
    re.compile(r"(?i)\b(calculator|terminal|cmd|console)\b"),
]


def match_intent_from_patterns(
    transcription: str, patterns: list, default: str
) -> str:
    """Match transcription against intent patterns (Issue #315 - extracted)."""
    for pattern, intent in patterns:
        if re.search(pattern, transcription):
            return intent
    return default
