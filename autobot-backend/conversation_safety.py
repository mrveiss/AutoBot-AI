# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Safety Guards

Enforces safety rules to prevent inappropriate conversation endings.
Critical component for maintaining conversation quality and user experience.

Safety Rules:
- Never end on questions
- Never end on confusion signals
- Never end on short conversations (<3 messages)
- Never end on active tasks
- Require explicit intent for ending

Related Issue: #159 - Prevent Premature Conversation Endings
"""

import logging
from dataclasses import dataclass
from typing import Optional

from conversation_context import ConversationContext
from intent_classifier import ConversationIntent, IntentClassification

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheckResult:
    """Result of safety guard check"""

    is_safe_to_end: bool
    override_intent: Optional[ConversationIntent]  # If safety guard overrides intent
    reason: str  # Reason for the decision
    violated_rules: list[str]  # Which safety rules were violated


class ConversationSafetyGuards:
    """
    Enforces safety rules to prevent inappropriate conversation endings.

    These guards override intent classification when necessary to protect
    conversation quality.
    """

    # Minimum messages before allowing conversation end
    MIN_CONVERSATION_LENGTH = 3

    # Minimum confidence required for END intent
    MIN_END_CONFIDENCE = 0.85

    def _check_context_rules(self, context: ConversationContext) -> list[str]:
        """
        Check context-based safety rules.

        (Issue #398: extracted helper)
        """
        violated = []

        if context.has_recent_question:
            violated.append("assistant_asked_question")
            logger.info("Safety guard: Cannot end - assistant just asked a question")

        if context.has_confusion_signals:
            violated.append("user_confused")
            logger.info("Safety guard: Cannot end - user expressed confusion")

        if context.message_count < self.MIN_CONVERSATION_LENGTH:
            violated.append("conversation_too_short")
            logger.info(
                "Safety guard: Cannot end - conversation too short (%d < %d)",
                context.message_count,
                self.MIN_CONVERSATION_LENGTH,
            )

        if context.has_active_task:
            violated.append("active_task")
            logger.info("Safety guard: Cannot end - active task in progress")

        return violated

    def _check_intent_rules(
        self, classification: IntentClassification, context: ConversationContext
    ) -> list[str]:
        """
        Check intent-based safety rules.

        (Issue #398: extracted helper)
        """
        violated = []

        if classification.intent == ConversationIntent.END:
            if classification.confidence < self.MIN_END_CONFIDENCE:
                violated.append("low_confidence_end")
                logger.info(
                    "Safety guard: Cannot end - confidence too low (%.2f < %.2f)",
                    classification.confidence,
                    self.MIN_END_CONFIDENCE,
                )

            if context.user_engagement_level == "high":
                violated.append("high_engagement")
                logger.info("Safety guard: Cannot end - user showing high engagement")

        return violated

    def check(
        self,
        classification: IntentClassification,
        context: ConversationContext,
    ) -> SafetyCheckResult:
        """
        Check if it's safe to end the conversation based on classification and context.

        (Issue #398: refactored to use extracted helpers)

        Args:
            classification: Intent classification result
            context: Conversation context analysis

        Returns:
            SafetyCheckResult indicating if it's safe to end and any overrides
        """
        violated_rules = self._check_context_rules(context)
        violated_rules.extend(self._check_intent_rules(classification, context))

        if violated_rules:
            override_intent = (
                ConversationIntent.CONTINUE
                if classification.intent == ConversationIntent.END
                else None
            )

            return SafetyCheckResult(
                is_safe_to_end=False,
                override_intent=override_intent,
                reason=f"Safety rules violated: {', '.join(violated_rules)}",
                violated_rules=violated_rules,
            )

        return SafetyCheckResult(
            is_safe_to_end=True,
            override_intent=None,
            reason="All safety checks passed",
            violated_rules=[],
        )

    def should_continue_conversation(
        self,
        classification: IntentClassification,
        context: ConversationContext,
    ) -> bool:
        """
        Determine if conversation should continue (convenience method).

        Returns:
            bool: True if conversation should continue, False if safe to end
        """
        safety_check = self.check(classification, context)

        # If safety guard says not safe to end, continue
        if not safety_check.is_safe_to_end:
            return True

        # If intent is END and safety checks passed, don't continue
        if classification.intent == ConversationIntent.END:
            return False

        # For all other intents, continue
        return True
