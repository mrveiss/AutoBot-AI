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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for streaming message types (Issue #326)
STREAMING_TYPES = frozenset(["llm_response", "llm_response_chunk", "response"])


def _parse_timestamp(msg_ts: str) -> Optional[datetime]:
    """Parse message timestamp string (Issue #315 - extracted)."""
    if not isinstance(msg_ts, str) or not msg_ts:
        return None
    try:
        if "T" in msg_ts:
            return datetime.fromisoformat(msg_ts.replace("Z", "+00:00"))
        return datetime.strptime(msg_ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _is_streaming_type(msg: Dict[str, Any]) -> bool:
    """Check if message is a streaming type (Issue #315 - extracted)."""
    msg_type = msg.get("messageType", msg.get("type", "default"))
    return msg_type in STREAMING_TYPES


def _group_streaming_by_time_window(
    messages: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[List[Dict[str, Any]]]]:
    """
    Separate non-streaming and group streaming messages by time window (Issue #315).

    Returns:
        Tuple of (non_streaming_messages, streaming_groups)
    """
    non_streaming = []
    streaming_groups: List[List[Dict[str, Any]]] = []
    current_group: List[Dict[str, Any]] = []
    last_streaming_ts: Optional[datetime] = None

    for msg in messages:
        if not _is_streaming_type(msg):
            if current_group:
                streaming_groups.append(current_group)
                current_group = []
                last_streaming_ts = None
            non_streaming.append(msg)
            continue

        current_ts = _parse_timestamp(msg.get("timestamp", ""))
        if current_ts and last_streaming_ts:
            time_diff = abs((current_ts - last_streaming_ts).total_seconds())
            if time_diff > 120:  # 2 minutes = new group
                if current_group:
                    streaming_groups.append(current_group)
                current_group = []

        if current_ts:
            last_streaming_ts = current_ts

        current_group.append(msg)

    if current_group:
        streaming_groups.append(current_group)

    return non_streaming, streaming_groups


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
        deduped_messages = self._dedupe_user_messages(messages)

        # STEP 2: Use extracted helper for streaming grouping (Issue #315)
        non_streaming, streaming_groups = _group_streaming_by_time_window(
            deduped_messages
        )

        # STEP 3: Keep only longest message per streaming group
        result = list(non_streaming)
        for group in streaming_groups:
            if group:
                longest = max(
                    group,
                    key=lambda m: len(m.get("text", "") or m.get("content", "")),
                )
                result.append(longest)

        result.sort(key=lambda m: m.get("timestamp", ""))
        return result

    def _dedupe_user_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Deduplicate user messages by content (Issue #315 - extracted)."""
        seen_user_content: set = set()
        deduped_messages = []

        for msg in messages:
            sender = msg.get("sender", "")
            if sender == "user":
                text_content = msg.get("text", "") or msg.get("content", "")
                content_key = text_content[:200]  # First 200 chars
                if content_key in seen_user_content:
                    continue  # Skip duplicate user message
                seen_user_content.add(content_key)

            deduped_messages.append(msg)

        return deduped_messages
