# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Analysis Mixin - Metadata extraction and conversation analysis.

Provides analysis capabilities for chat conversations:
- Topic extraction from messages
- Entity mention detection
- Conversation summary generation
- Metadata extraction for Memory Graph integration
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for sender type detection
_BOT_SENDER_TYPES = frozenset({"bot", "assistant"})

# Performance optimization: O(1) lookup for topic keywords (Issue #326)
TOPIC_PATTERNS = {
    "installation": frozenset(["install", "setup", "configure", "deployment"]),
    "troubleshooting": frozenset(["error", "issue", "problem", "fix", "debug"]),
    "architecture": frozenset(
        ["architecture", "design", "vm", "distributed", "service"]
    ),
    "api": frozenset(["api", "endpoint", "request", "integration"]),
    "knowledge_base": frozenset(["knowledge", "document", "upload", "vectorize"]),
    "chat": frozenset(["chat", "conversation", "message", "response"]),
    "redis": frozenset(["redis", "cache", "database"]),
    "frontend": frozenset(["frontend", "vue", "ui", "interface"]),
    "backend": frozenset(["backend", "fastapi", "python"]),
    "security": frozenset(["security", "authentication", "encryption"]),
}


class AnalysisMixin:
    """
    Mixin providing analysis and metadata extraction for chat conversations.

    This mixin is stateless and doesn't require any base class attributes.
    """

    def _categorize_messages_by_sender(self, messages: List[Dict[str, Any]]) -> tuple:
        """
        Categorize messages into user and bot message lists.

        Args:
            messages: List of conversation messages.

        Returns:
            Tuple of (all_text, user_messages, bot_messages).

        Issue #620.
        """
        all_text = []
        user_messages = []
        bot_messages = []

        for msg in messages:
            sender = msg.get("sender", "")
            text = msg.get("text", "")

            all_text.append(text)

            if sender == "user":
                user_messages.append(text)
            elif sender in _BOT_SENDER_TYPES:
                bot_messages.append(text)

        return all_text, user_messages, bot_messages

    def _build_metadata_result(
        self,
        topics: List[str],
        entity_mentions: List[str],
        summary: str,
        message_count: int,
        user_message_count: int,
        bot_message_count: int,
    ) -> Dict[str, Any]:
        """
        Build the metadata result dictionary.

        Args:
            topics: List of detected topics.
            entity_mentions: List of entity mentions.
            summary: Conversation summary.
            message_count: Total message count.
            user_message_count: User message count.
            bot_message_count: Bot message count.

        Returns:
            Dictionary with all metadata fields.

        Issue #620.
        """
        return {
            "topics": topics,
            "entity_mentions": entity_mentions,
            "summary": summary,
            "message_count": message_count,
            "user_message_count": user_message_count,
            "bot_message_count": bot_message_count,
        }

    def _extract_conversation_metadata(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract metadata from conversation messages for Memory Graph entity.

        Args:
            messages: List of conversation messages

        Returns:
            Dictionary with extracted metadata (topics, entities, summary)
        """
        try:
            if not messages:
                return self._build_metadata_result(
                    [], [], "Empty conversation", 0, 0, 0
                )

            all_text, user_messages, bot_messages = self._categorize_messages_by_sender(
                messages
            )

            topics = self._extract_topics(all_text)
            entity_mentions = self._detect_entity_mentions(all_text)
            summary = self._generate_conversation_summary(user_messages, bot_messages)

            return self._build_metadata_result(
                topics,
                entity_mentions,
                summary,
                len(messages),
                len(user_messages),
                len(bot_messages),
            )

        except Exception as e:
            logger.warning("Failed to extract conversation metadata: %s", e)
            return self._build_metadata_result(
                [],
                [],
                "Metadata extraction failed",
                len(messages) if messages else 0,
                0,
                0,
            )

    def _extract_topics(self, text_list: List[str]) -> List[str]:
        """
        Extract topics from conversation text using keyword detection.

        Args:
            text_list: List of message texts

        Returns:
            List of detected topics
        """
        topics = set()

        # Combine all text
        combined_text = " ".join(text_list).lower()

        for topic, keywords in TOPIC_PATTERNS.items():
            if any(keyword in combined_text for keyword in keywords):
                topics.add(topic)

        return list(topics)

    def _detect_entity_mentions(self, text_list: List[str]) -> List[str]:
        """
        Detect mentions of bugs, features, tasks in conversation.

        Args:
            text_list: List of message texts

        Returns:
            List of detected entity mention types
        """
        mentions = set()

        combined_text = " ".join(text_list).lower()

        # Bug mention patterns
        if re.search(r"bug|issue|error|problem|fix", combined_text):
            mentions.add("bug_mention")

        # Feature mention patterns
        if re.search(r"feature|implement|add|new|enhancement", combined_text):
            mentions.add("feature_mention")

        # Task mention patterns
        if re.search(r"task|todo|need to|should|must", combined_text):
            mentions.add("task_mention")

        # Decision mention patterns
        if re.search(r"decide|decision|choose|select|prefer", combined_text):
            mentions.add("decision_mention")

        return list(mentions)

    def _generate_conversation_summary(
        self, user_messages: List[str], bot_messages: List[str]
    ) -> str:
        """
        Generate brief summary of conversation.

        Args:
            user_messages: List of user message texts
            bot_messages: List of bot message texts

        Returns:
            Brief summary string
        """
        if not user_messages:
            return "No user messages"

        # Get first user message for context
        first_msg = user_messages[0][:100] if user_messages else ""

        if len(user_messages) == 1:
            return f"Single exchange: {first_msg}..."
        else:
            return f"Conversation started with: {first_msg}... ({len(user_messages)} user messages)"
