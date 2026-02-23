# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Context Analyzer

Analyzes conversation history to provide context signals for intent classification.
Helps prevent premature conversation endings by understanding conversation flow.

Features:
- Detect questions in conversation
- Analyze sentiment and confusion signals
- Track conversation length and engagement
- Identify active tasks and workflows

Related Issue: #159 - Prevent Premature Conversation Endings
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for engagement keyword detection (O(1) iteration)
_ENGAGEMENT_KEYWORDS = ("how", "what", "why", "create", "make", "build")

# Issue #380: Module-level dict for topic keyword mapping
_TOPIC_KEYWORDS = {
    "installation": ("install", "setup", "configure", "deploy"),
    "troubleshooting": ("error", "issue", "problem", "fix", "debug"),
    "architecture": ("architecture", "design", "component", "system"),
    "api": ("api", "endpoint", "request", "response"),
    "configuration": ("config", "setting", "environment", "variable"),
}


@dataclass
class ConversationContext:
    """Context information about the conversation"""

    message_count: int
    has_recent_question: bool  # Did assistant ask a question recently?
    has_active_task: bool  # Is there an ongoing task?
    has_confusion_signals: bool  # Did user express confusion?
    user_engagement_level: str  # low, medium, high
    last_assistant_message: Optional[str]
    conversation_topic: Optional[str]  # Current topic being discussed


class ConversationContextAnalyzer:
    """
    Analyzes conversation history to provide context for intent classification.

    Fast, lightweight analysis focused on preventing premature conversation endings.
    """

    # Question patterns in assistant messages
    QUESTION_PATTERNS = [
        r"\?",  # Any question mark
        r"^(what|why|how|when|where|which|who|can|could|would|should|do|does|did)",
        r"(please|could you|would you|can you) (tell|explain|describe|clarify)",
    ]

    # Confusion indicators in user messages
    CONFUSION_INDICATORS = {
        "confused",
        "unclear",
        "don't understand",
        "dont understand",
        "not sure",
        "what do you mean",
        "what does that mean",
        "can you explain",
        "i'm lost",
        "im lost",
        "help",
        "huh",
        "what",
    }

    # Task indicators
    TASK_INDICATORS = {
        "working on",
        "currently",
        "processing",
        "analyzing",
        "running",
        "executing",
        "building",
        "creating",
        "configuring",
        "installing",
        "deploying",
    }

    def analyze(
        self,
        conversation_history: List[Dict[str, str]],
        current_message: str,
    ) -> ConversationContext:
        """
        Analyze conversation history to extract context.

        Args:
            conversation_history: List of conversation messages
                Format: [{"role": "user"/"assistant", "content": "..."}]
            current_message: The current user message being classified

        Returns:
            ConversationContext with analyzed signals
        """
        if not conversation_history:
            # Even with empty history, check current message for confusion signals
            has_confusion_signals = self._has_confusion_signals(current_message)
            engagement_level = self._assess_engagement([], current_message)

            return ConversationContext(
                message_count=0,
                has_recent_question=False,
                has_active_task=False,
                has_confusion_signals=has_confusion_signals,
                user_engagement_level=engagement_level,
                last_assistant_message=None,
                conversation_topic=None,
            )

        return self._analyze_with_history(conversation_history, current_message)

    def _analyze_with_history(
        self,
        conversation_history: List[Dict[str, str]],
        current_message: str,
    ) -> ConversationContext:
        """Helper for analyze. Ref: #1088."""
        message_count = len(conversation_history)

        # Get last assistant message
        last_assistant_msg = None
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "")
                break

        has_recent_question = (
            self._has_question(last_assistant_msg) if last_assistant_msg else False
        )
        has_active_task = self._has_active_task(conversation_history)
        has_confusion_signals = self._has_confusion_signals(current_message)
        engagement_level = self._assess_engagement(
            conversation_history, current_message
        )
        topic = self._determine_topic(conversation_history)

        return ConversationContext(
            message_count=message_count,
            has_recent_question=has_recent_question,
            has_active_task=has_active_task,
            has_confusion_signals=has_confusion_signals,
            user_engagement_level=engagement_level,
            last_assistant_message=last_assistant_msg,
            conversation_topic=topic,
        )

    def _has_question(self, message: Optional[str]) -> bool:
        """Check if message contains a question"""
        if not message:
            return False

        message_lower = message.lower()

        # Check for question mark
        if "?" in message:
            return True

        # Check for question patterns
        for pattern in self.QUESTION_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return True

        return False

    def _has_active_task(self, conversation_history: List[Dict[str, str]]) -> bool:
        """Check if there's an active task in recent conversation"""
        # Look at last 3 messages
        recent_messages = (
            conversation_history[-3:]
            if len(conversation_history) >= 3
            else conversation_history
        )

        for msg in recent_messages:
            content = msg.get("content", "").lower()
            if any(indicator in content for indicator in self.TASK_INDICATORS):
                return True

        return False

    def _has_confusion_signals(self, message: str) -> bool:
        """Check if user is expressing confusion"""
        message_lower = message.lower()
        return any(
            indicator in message_lower for indicator in self.CONFUSION_INDICATORS
        )

    def _assess_engagement(
        self,
        conversation_history: List[Dict[str, str]],
        current_message: str,
    ) -> str:
        """
        Assess user's engagement level.

        Returns: "low", "medium", or "high"
        """
        # Very short message = potentially low engagement
        if len(current_message.split()) <= 3:
            return "low"

        # Long, detailed messages = high engagement
        if len(current_message.split()) > 20:
            return "high"

        # Questions or task requests = high engagement
        if "?" in current_message or any(
            word in current_message.lower() for word in _ENGAGEMENT_KEYWORDS
        ):
            return "high"

        # Short conversation but engaged message = medium
        if len(conversation_history) < 3:
            return "medium"

        # Default to medium
        return "medium"

    def _determine_topic(
        self, conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Determine current conversation topic.

        Returns: Topic string or None
        """
        if not conversation_history:
            return None

        # Simple topic detection based on keywords in recent messages
        recent_content = " ".join(
            msg.get("content", "").lower() for msg in conversation_history[-3:]
        )

        # Issue #380: Use module-level topic keywords constant
        for topic, keywords in _TOPIC_KEYWORDS.items():
            if any(keyword in recent_content for keyword in keywords):
                return topic

        return "general"
