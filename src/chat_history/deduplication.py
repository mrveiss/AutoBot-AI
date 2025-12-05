# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Deduplication Mixin - Message deduplication logic.

Provides deduplication of streaming and duplicate messages:
- Streaming message consolidation (Issue #259)
- User message deduplication
- Time-window based grouping
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for streaming message types (Issue #326)
STREAMING_TYPES = frozenset(["llm_response", "llm_response_chunk", "response"])


class DeduplicationMixin:
    """
    Mixin providing message deduplication for chat history.

    This mixin is stateless and doesn't require any base class attributes.
    """

    def _dedupe_streaming_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate messages to fix Issue #259.

        Handles two types of duplicates:
        1. STREAMING: Multiple accumulated states with different timestamps
           - Groups by 2-minute time window, keeps longest per group
        2. USER MESSAGES: Duplicate saves from backend + frontend
           - Deduplicates by content, keeps first occurrence

        Args:
            messages: List of message dicts

        Returns:
            Deduplicated message list
        """
        if not messages:
            return messages

        # STEP 1: Deduplicate user messages by content
        seen_user_content: set = set()
        deduped_messages = []

        for msg in messages:
            sender = msg.get("sender", "")
            text_content = msg.get("text", "") or msg.get("content", "")

            if sender == "user":
                # Deduplicate user messages by content
                content_key = text_content[:200]  # First 200 chars
                if content_key in seen_user_content:
                    continue  # Skip duplicate user message
                seen_user_content.add(content_key)

            deduped_messages.append(msg)

        # STEP 2: Deduplicate streaming messages by time-window grouping
        result = []
        streaming_groups: List[List[Dict[str, Any]]] = []
        current_group: List[Dict[str, Any]] = []
        last_streaming_ts = None

        for msg in deduped_messages:
            msg_type = msg.get("messageType", msg.get("type", "default"))

            if msg_type in STREAMING_TYPES:
                msg_ts = msg.get("timestamp", "")
                try:
                    if isinstance(msg_ts, str) and msg_ts:
                        if "T" in msg_ts:
                            current_ts = datetime.fromisoformat(
                                msg_ts.replace("Z", "+00:00")
                            )
                        else:
                            current_ts = datetime.strptime(msg_ts, "%Y-%m-%d %H:%M:%S")

                        if last_streaming_ts is not None:
                            time_diff = abs(
                                (current_ts - last_streaming_ts).total_seconds()
                            )
                            if time_diff > 120:  # 2 minutes = new group
                                if current_group:
                                    streaming_groups.append(current_group)
                                current_group = []

                        last_streaming_ts = current_ts
                except (ValueError, TypeError) as e:
                    logger.debug("Timestamp parse error: %s", e)

                current_group.append(msg)
            else:
                if current_group:
                    streaming_groups.append(current_group)
                    current_group = []
                    last_streaming_ts = None
                result.append(msg)

        if current_group:
            streaming_groups.append(current_group)

        # Keep only longest message per streaming group
        for group in streaming_groups:
            if not group:
                continue
            longest = max(
                group,
                key=lambda m: len(m.get("text", "") or m.get("content", "")),
            )
            result.append(longest)

        result.sort(key=lambda m: m.get("timestamp", ""))

        return result
