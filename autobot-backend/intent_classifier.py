# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Intent Classifier for AutoBot Conversations

Provides 4-category intent classification to prevent premature conversation endings:
- CONTINUE: User wants to continue the conversation
- END: User explicitly wants to end the conversation
- CLARIFICATION: User is asking for clarification
- TASK_REQUEST: User is requesting a task/action

Uses pattern matching + context analysis for fast, accurate classification (<10ms).
Avoids heavy ML models for performance.

Related Issue: #159 - Prevent Premature Conversation Endings
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for acknowledgment word detection
_ACKNOWLEDGMENT_WORDS = frozenset(
    {"ok", "okay", "yes", "no", "sure", "thanks", "thank you"}
)


class ConversationIntent(Enum):
    """Intent categories for conversation management"""

    CONTINUE = "continue"
    END = "end"
    CLARIFICATION = "clarification"
    TASK_REQUEST = "task_request"


@dataclass
class IntentClassification:
    """Result of intent classification"""

    intent: ConversationIntent
    confidence: float  # 0.0 to 1.0
    reasoning: str  # Why this classification was made
    signals: Dict[str, bool]  # Detected signals (has_question, has_task_word, etc.)


class IntentClassifier:
    """
    Fast, pattern-based intent classifier for conversation management.

    Designed for <10ms classification overhead with >95% accuracy.
    """

    # Explicit exit phrases (high confidence)
    EXIT_PHRASES = {
        "goodbye",
        "bye",
        "bye bye",
        "farewell",
        "see you",
        "see you later",
        "talk to you later",
        "ttyl",
        "gotta go",
        "have to go",
        "need to go",
        "i'm done",
        "im done",
        "that's all",
        "thats all",
        "that is all",
        "thanks goodbye",
        "thank you goodbye",
        "end chat",
        "exit",
        "quit",
        "close chat",
        "end conversation",
        "stop chat",
    }

    # Words that indicate continuation (not exit)
    CONTINUATION_WORDS = {
        "of",  # Critical: "of autobot" should NOT trigger exit
        "about",
        "explain",
        "tell",
        "show",
        "how",
        "what",
        "why",
        "when",
        "where",
        "which",
        "who",
        "can",
        "could",
        "would",
        "should",
        "please",
        "help",
        "more",
        "also",
        "additionally",
        "furthermore",
        "and",
        "but",
        "however",
        "next",
        "then",
        "after",
        "before",
    }

    # Question indicators
    QUESTION_WORDS = {
        "what",
        "why",
        "how",
        "when",
        "where",
        "which",
        "who",
        "whose",
        "whom",
        "can",
        "could",
        "would",
        "should",
        "is",
        "are",
        "do",
        "does",
        "did",
        "will",
        "won't",
        "shall",
    }

    # Task/action indicators
    TASK_WORDS = {
        "create",
        "make",
        "build",
        "generate",
        "write",
        "code",
        "fix",
        "debug",
        "install",
        "setup",
        "configure",
        "deploy",
        "run",
        "execute",
        "start",
        "stop",
        "restart",
        "update",
        "upgrade",
        "download",
        "upload",
        "delete",
        "remove",
        "add",
        "modify",
        "change",
        "analyze",
        "check",
        "test",
        "verify",
    }

    # Clarification indicators
    CLARIFICATION_WORDS = {
        "mean",
        "clarify",
        "explain",
        "elaborate",
        "confused",
        "unclear",
        "understand",
        "sorry",
        "pardon",
        "repeat",
        "again",
        "rephrase",
        "what do you mean",
        "what does that mean",
        "i don't understand",
        "i dont understand",
        "can you explain",
    }

    def classify(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> IntentClassification:
        """
        Classify user's intent from message.

        Args:
            message: User's message to classify
            conversation_history: Previous conversation for context
                Format: [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            IntentClassification with intent, confidence, and reasoning
        """
        # Normalize message
        message_lower = message.lower().strip()
        words = message_lower.split()

        # Detect signals
        signals = {
            "has_question_mark": "?" in message,
            "has_exclamation": "!" in message,
            "is_very_short": len(words) <= 2,
            "is_long": len(words) > 20,
            "starts_with_question_word": (
                words[0] in self.QUESTION_WORDS if words else False
            ),
            "has_task_word": any(word in self.TASK_WORDS for word in words),
            "has_clarification_word": any(
                word in self.CLARIFICATION_WORDS for word in words
            ),
            "has_continuation_word": any(
                word in self.CONTINUATION_WORDS for word in words
            ),
            "has_exit_phrase": any(
                phrase in message_lower for phrase in self.EXIT_PHRASES
            ),
        }

        # Classify based on signals
        return self._classify_from_signals(
            message, message_lower, words, signals, conversation_history
        )

    def _check_exit_phrase_intent(
        self, signals: Dict[str, bool]
    ) -> Optional[IntentClassification]:
        """
        Check if exit phrase signals indicate END or CONTINUE intent.

        Issue #281: Extracted helper for exit phrase rule.

        Args:
            signals: Detected signals dictionary

        Returns:
            IntentClassification if exit phrase detected, None otherwise
        """
        if not signals["has_exit_phrase"]:
            return None

        # Exit phrase as question = clarification
        if signals["has_question_mark"]:
            return IntentClassification(
                intent=ConversationIntent.CLARIFICATION,
                confidence=0.85,
                reasoning=(
                    "Exit phrase detected but in question form - "
                    "user asking about exiting"
                ),
                signals=signals,
            )

        # Exit phrase with continuation context = continue
        if signals["has_continuation_word"]:
            return IntentClassification(
                intent=ConversationIntent.CONTINUE,
                confidence=0.90,
                reasoning="Exit word present but continuation context detected",
                signals=signals,
            )

        # Clear exit intent
        return IntentClassification(
            intent=ConversationIntent.END,
            confidence=0.95,
            reasoning="Explicit exit phrase detected without question context",
            signals=signals,
        )

    def _check_question_intent(
        self, signals: Dict[str, bool]
    ) -> Optional[IntentClassification]:
        """
        Check if question signals indicate CLARIFICATION or CONTINUE intent.

        Issue #281: Extracted helper for question rule.

        Args:
            signals: Detected signals dictionary

        Returns:
            IntentClassification if question detected, None otherwise
        """
        if not (signals["has_question_mark"] or signals["starts_with_question_word"]):
            return None

        if signals["has_clarification_word"]:
            return IntentClassification(
                intent=ConversationIntent.CLARIFICATION,
                confidence=0.90,
                reasoning="Question with clarification indicators",
                signals=signals,
            )

        return IntentClassification(
            intent=ConversationIntent.CONTINUE,
            confidence=0.90,
            reasoning="Question detected - user wants information",
            signals=signals,
        )

    def _check_short_message_intent(
        self,
        words: List[str],
        signals: Dict[str, bool],
        conversation_history: Optional[List[Dict[str, str]]],
    ) -> Optional[IntentClassification]:
        """
        Check if short message context indicates continuation intent.

        Issue #281: Extracted helper for short message rule.

        Args:
            words: List of words in message
            signals: Detected signals dictionary
            conversation_history: Previous conversation messages

        Returns:
            IntentClassification if short message pattern detected, None otherwise
        """
        if not signals["is_very_short"]:
            return None

        # Check if responding to assistant's question
        if conversation_history and len(conversation_history) > 0:
            last_msg = conversation_history[-1]
            if last_msg.get("role") == "assistant" and "?" in last_msg.get(
                "content", ""
            ):
                return IntentClassification(
                    intent=ConversationIntent.CONTINUE,
                    confidence=0.75,
                    reasoning="Short response to assistant's question",
                    signals=signals,
                )

        # Single word acknowledgments - Issue #380: use module constant
        if len(words) == 1 and words[0] in _ACKNOWLEDGMENT_WORDS:
            return IntentClassification(
                intent=ConversationIntent.CONTINUE,
                confidence=0.70,
                reasoning="Acknowledgment - likely continuing conversation",
                signals=signals,
            )

        return None

    def _classify_from_signals(
        self,
        message: str,
        message_lower: str,
        words: List[str],
        signals: Dict[str, bool],
        conversation_history: Optional[List[Dict[str, str]]],
    ) -> IntentClassification:
        """
        Internal classification logic based on detected signals.

        Issue #281: Refactored from 123 lines to use extracted helper methods.

        Args:
            message: Original message
            message_lower: Lowercased message
            words: List of words in message
            signals: Detected signals dictionary
            conversation_history: Previous conversation messages

        Returns:
            IntentClassification with intent, confidence, and reasoning
        """
        # RULE 1: Check for explicit exit phrases (highest priority)
        # Issue #281: uses helper
        exit_result = self._check_exit_phrase_intent(signals)
        if exit_result:
            return exit_result

        # RULE 2: Question indicators (high priority for continuation)
        # Issue #281: uses helper
        question_result = self._check_question_intent(signals)
        if question_result:
            return question_result

        # RULE 3: Task request indicators
        if signals["has_task_word"]:
            return IntentClassification(
                intent=ConversationIntent.TASK_REQUEST,
                confidence=0.85,
                reasoning="Task/action word detected",
                signals=signals,
            )

        # RULE 4: Clarification request
        if signals["has_clarification_word"]:
            return IntentClassification(
                intent=ConversationIntent.CLARIFICATION,
                confidence=0.85,
                reasoning="Clarification indicators detected",
                signals=signals,
            )

        # RULE 5: Very short messages - likely acknowledgment or continuation
        # Issue #281: uses helper
        short_msg_result = self._check_short_message_intent(
            words, signals, conversation_history
        )
        if short_msg_result:
            return short_msg_result

        # RULE 6: Continuation words indicate ongoing conversation
        if signals["has_continuation_word"]:
            return IntentClassification(
                intent=ConversationIntent.CONTINUE,
                confidence=0.80,
                reasoning="Continuation words detected",
                signals=signals,
            )

        # DEFAULT: Assume continuation (safer than premature ending)
        return IntentClassification(
            intent=ConversationIntent.CONTINUE,
            confidence=0.60,
            reasoning="Default to continuation - no clear exit signal",
            signals=signals,
        )
