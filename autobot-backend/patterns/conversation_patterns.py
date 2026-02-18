# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Conversation Patterns for AutoBot

This module contains all conversational pattern matching logic used throughout
the application for consistent pattern recognition.
"""

import re
from enum import Enum
from functools import cached_property
from typing import Dict, List, Pattern


class ConversationType(Enum):
    """Types of conversational messages."""

    GREETING = "greeting"
    FAREWELL = "farewell"
    GRATITUDE = "gratitude"
    STATUS_INQUIRY = "status_inquiry"
    AFFIRMATION = "affirmation"
    NEGATION = "negation"


class ConversationPatterns:
    """Centralized conversation pattern management."""

    def __init__(self):
        """Initialize conversation patterns."""
        self.patterns: Dict[ConversationType, List[Pattern]] = {
            ConversationType.GREETING: [
                re.compile(r"^(hello|hi|hey|greetings?)!?$", re.IGNORECASE),
                re.compile(
                    r"^(good\s+(morning|afternoon|evening|day))!?$", re.IGNORECASE
                ),
            ],
            ConversationType.STATUS_INQUIRY: [
                re.compile(
                    r"^(how\s+are\s+you|how\s+are\s+things)[\?!]?$", re.IGNORECASE
                ),
                re.compile(
                    r"^(how\s+are\s+you)$", re.IGNORECASE
                ),  # Without punctuation
                re.compile(r"^(what'?s\s+up|wassup)[\?!]?$", re.IGNORECASE),
            ],
            ConversationType.GRATITUDE: [
                re.compile(r"^(thanks?|thank\s+you)!?$", re.IGNORECASE),
                re.compile(r"^(much\s+appreciated|appreciate\s+it)!?$", re.IGNORECASE),
            ],
            ConversationType.FAREWELL: [
                re.compile(r"^(bye|goodbye|see\s+you)!?$", re.IGNORECASE),
                re.compile(
                    r"^(catch\s+you\s+later|talk\s+later|ttyl)!?$", re.IGNORECASE
                ),
            ],
            ConversationType.AFFIRMATION: [
                re.compile(r"^(yes|yeah|yep|y|ok|okay|sure|alright)!?$", re.IGNORECASE),
                re.compile(r"^(sounds\s+good|looks\s+good|perfect)!?$", re.IGNORECASE),
            ],
            ConversationType.NEGATION: [
                re.compile(r"^(no|nah|nope|n)!?$", re.IGNORECASE),
                re.compile(r"^(not\s+now|maybe\s+later)!?$", re.IGNORECASE),
            ],
        }

    def classify_message(self, message: str) -> ConversationType:
        """
        Classify a message based on conversation patterns.

        Args:
            message: The message to classify

        Returns:
            ConversationType if message matches a pattern, None otherwise
        """
        message_clean = message.strip()

        for conversation_type, patterns in self.patterns.items():
            for pattern in patterns:
                if pattern.match(message_clean):
                    return conversation_type

        return None

    def is_conversational(self, message: str) -> bool:
        """
        Check if a message is conversational (matches any pattern).

        Args:
            message: The message to check

        Returns:
            True if message is conversational
        """
        return self.classify_message(message) is not None

    def get_all_patterns(self) -> List[Pattern]:
        """Get all patterns as a flat list."""
        all_patterns = []
        for patterns in self.patterns.values():
            all_patterns.extend(patterns)
        return all_patterns

    def add_pattern(self, conversation_type: ConversationType, pattern: str):
        """Add a new pattern to a conversation type."""
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        self.patterns[conversation_type].append(compiled_pattern)

    @cached_property
    def _response_templates(self) -> Dict[ConversationType, str]:
        """Issue #380: Cache templates to avoid repeated dict creation."""
        return {
            ConversationType.GREETING: (
                "Hello! I'm AutoBot, your AI assistant. I'm here to help you with "
                "various tasks including system commands, research, security analysis, "
                "and more. What can I help you with today?"
            ),
            ConversationType.STATUS_INQUIRY: (
                "I'm doing well and ready to help! My systems are operational and I'm "
                "equipped with various capabilities. What would you like to work on?"
            ),
            ConversationType.GRATITUDE: (
                "You're welcome! I'm always happy to help. Let me know if you need anything else."
            ),
            ConversationType.FAREWELL: (
                "Goodbye! Feel free to return anytime you need assistance. Have a great day!"
            ),
            ConversationType.AFFIRMATION: "Great! How can I assist you?",
            ConversationType.NEGATION: (
                "No problem! Let me know if you need help with anything else."
            ),
        }

    def get_response_template(self, conversation_type: ConversationType) -> str:
        """Get response template for a conversation type."""
        return self._response_templates.get(
            conversation_type,
            "I'm here to help! What would you like me to assist you with today?",
        )


# Global instance for easy access
conversation_patterns = ConversationPatterns()
