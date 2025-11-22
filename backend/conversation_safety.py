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

from backend.conversation_context import ConversationContext
from backend.intent_classifier import ConversationIntent, IntentClassification

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

    def check(
        self,
        classification: IntentClassification,
        context: ConversationContext,
    ) -> SafetyCheckResult:
        """
        Check if it's safe to end the conversation based on classification and context.

        Args:
            classification: Intent classification result
            context: Conversation context analysis

        Returns:
            SafetyCheckResult indicating if it's safe to end and any overrides
        """
        violated_rules = []

        # SAFETY RULE 1: Never end on questions
        if context.has_recent_question:
            violated_rules.append("assistant_asked_question")
            logger.info("Safety guard: Cannot end - assistant just asked a question")

        # SAFETY RULE 2: Never end on confusion signals
        if context.has_confusion_signals:
            violated_rules.append("user_confused")
            logger.info("Safety guard: Cannot end - user expressed confusion")

        # SAFETY RULE 3: Never end on short conversations
        if context.message_count < self.MIN_CONVERSATION_LENGTH:
            violated_rules.append("conversation_too_short")
            logger.info(
                f"Safety guard: Cannot end - conversation too short "
                f"({context.message_count} < {self.MIN_CONVERSATION_LENGTH})"
            )

        # SAFETY RULE 4: Never end on active tasks
        if context.has_active_task:
            violated_rules.append("active_task")
            logger.info("Safety guard: Cannot end - active task in progress")

        # SAFETY RULE 5: Require high confidence for END intent
        if classification.intent == ConversationIntent.END:
            if classification.confidence < self.MIN_END_CONFIDENCE:
                violated_rules.append("low_confidence_end")
                logger.info(
                    f"Safety guard: Cannot end - confidence too low "
                    f"({classification.confidence} < {self.MIN_END_CONFIDENCE})"
                )

        # SAFETY RULE 6: High engagement level prevents ending
        if context.user_engagement_level == "high":
            if classification.intent == ConversationIntent.END:
                violated_rules.append("high_engagement")
                logger.info("Safety guard: Cannot end - user showing high engagement")

        # Determine if it's safe to end
        if violated_rules:
            # Override END intent to CONTINUE
            override_intent = ConversationIntent.CONTINUE if classification.intent == ConversationIntent.END else None

            return SafetyCheckResult(
                is_safe_to_end=False,
                override_intent=override_intent,
                reason=f"Safety rules violated: {', '.join(violated_rules)}",
                violated_rules=violated_rules,
            )

        # All safety checks passed
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
