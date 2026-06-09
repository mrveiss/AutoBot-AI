# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Context overflow protection for chat conversations. Issue #9043.

Provides automatic context window management:
- Tracks cumulative token usage per session
- Warns at 80% of model context limit
- Auto-summarizes at 90% to preserve conversation history
- Injects summaries as system messages
- Preserves original history in database

Builds on #8990 (token usage tracking) and #3770 (compression service).
"""

from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# Redis key prefixes
_TOKEN_TRACKER_KEY_PREFIX = "chat:tokens:"
_SUMMARY_MARKER_KEY_PREFIX = "chat:summary_marker:"

# Default thresholds (can be overridden)
_DEFAULT_WARNING_THRESHOLD = 0.80  # 80%
_DEFAULT_COMPRESS_THRESHOLD = 0.90  # 90%


class SessionTokenTracker:
    """Tracks cumulative token usage for chat sessions.

    Accumulates token counts from LLMResponse usage fields and persists
    to Redis so long-running conversations can track their context fill.

    Usage::

        tracker = SessionTokenTracker()
        await tracker.add_message_tokens(session_id, prompt_tokens=100, completion_tokens=50)
        usage = await tracker.get_session_usage(session_id)
        # {'total_tokens': 150, 'message_count': 1}
    """

    def __init__(self, ttl_seconds: int = 86400):
        """Initialize token tracker.

        Args:
            ttl_seconds: TTL for Redis keys (default 24h).
        """
        self.ttl_seconds = ttl_seconds
        self.redis = None

    async def _ensure_redis(self):
        """Lazy init Redis client."""
        if self.redis is None:
            self.redis = await get_async_redis_client()
        if self.redis is None:
            logger.warning("SessionTokenTracker: Redis unavailable, token tracking disabled")
        return self.redis

    async def add_message_tokens(
        self,
        session_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Add token usage from a new message to session cumulative total.

        Args:
            session_id: Chat session identifier.
            prompt_tokens: Input token count.
            completion_tokens: Generated token count.
        """
        redis = await self._ensure_redis()
        if not redis:
            return

        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        total_tokens = prompt_tokens + completion_tokens

        try:
            # Atomic increment and expiry
            pipe = redis.pipeline()
            pipe.hincrby(key, "total_tokens", total_tokens)
            pipe.hincrby(key, "prompt_tokens", prompt_tokens)
            pipe.hincrby(key, "completion_tokens", completion_tokens)
            pipe.hincrby(key, "message_count", 1)
            pipe.expire(key, self.ttl_seconds)
            await pipe.execute()
        except Exception as e:
            logger.error("Failed to track tokens for session %s: %s", session_id, e)

    async def get_session_usage(self, session_id: str) -> Dict[str, int]:
        """Get cumulative token usage for a session.

        Args:
            session_id: Chat session identifier.

        Returns:
            Dict with total_tokens, prompt_tokens, completion_tokens, message_count.
            Returns zeros if no data exists.
        """
        redis = await self._ensure_redis()
        if not redis:
            return {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "message_count": 0,
            }

        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        try:
            data = await redis.hgetall(key)
            if not data:
                return {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "message_count": 0,
                }

            return {
                "total_tokens": int(data.get(b"total_tokens", 0)),
                "prompt_tokens": int(data.get(b"prompt_tokens", 0)),
                "completion_tokens": int(data.get(b"completion_tokens", 0)),
                "message_count": int(data.get(b"message_count", 0)),
            }
        except Exception as e:
            logger.error("Failed to get session usage for %s: %s", session_id, e)
            return {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "message_count": 0,
            }

    async def reset_session(self, session_id: str) -> None:
        """Reset token tracking for a session (after summarization).

        Args:
            session_id: Chat session identifier.
        """
        redis = await self._ensure_redis()
        if not redis:
            return

        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        try:
            await redis.delete(key)
        except Exception as e:
            logger.error("Failed to reset session %s: %s", session_id, e)


def _sanitize_tool_messages(msgs: List[Dict]) -> List[Dict]:
    """Drop orphaned tool messages and dangling assistant tool_calls.

    OpenAI/Anthropic APIs require every role='tool' message to immediately
    follow an assistant message that carries tool_calls. Front-trimming
    conversation history can cut the assistant tool_calls parent while keeping
    its tool responses, causing provider validation errors.
    """
    cleaned: List[Dict] = []
    in_batch = False
    for m in msgs:
        role = m.get("role")
        if role == "tool":
            if in_batch:
                cleaned.append(m)
            # else: orphan — drop silently
            continue
        if role == "assistant" and m.get("tool_calls"):
            in_batch = True
        else:
            in_batch = False
        cleaned.append(m)
    return cleaned


class ConversationSummarizer:
    """Uses LLM to create intelligent conversation summaries.

    Calls the LLM gateway to generate compact summaries that preserve
    decisions, facts, and action items from earlier conversation segments.

    Usage::

        summarizer = ConversationSummarizer()
        summary = await summarizer.summarize_messages(messages, model="gpt-4")
    """

    _SUMMARIZATION_PROMPT = (
        "You are summarizing a conversation to preserve context after compaction. "
        "Produce a structured summary that lets the conversation continue seamlessly.\n\n"
        "Use this format:\n\n"
        "## Conversation Summary\n"
        "**Turns summarized:** {{count}}\n\n"
        "### User Goal\n"
        "One sentence describing what the user is trying to accomplish.\n\n"
        "### What Was Done\n"
        "- Bullet points of completed actions, decisions made, and key outputs\n"
        "- Include specific file paths, function names, variable names, URLs, and config values\n"
        "- Note any errors encountered and how they were resolved\n\n"
        "### Current State\n"
        "What is the system/task state right now? What was the last thing discussed?\n\n"
        "### Pending / Next Steps\n"
        "- What remains to be done\n"
        "- Any open questions or blockers\n\n"
        "### Key Context\n"
        "- Important constraints, preferences, or decisions that must not be forgotten\n"
        "- Specific values: model names, ports, paths, credentials references, versions\n\n"
        "Keep the summary under 1000 tokens. Be dense — every token should carry information.\n\n"
        "Conversation to summarize:\n"
        "{{conversation}}\n\n"
        "Provide ONLY the structured summary above — no preamble or meta-commentary."
    )

    async def _get_gateway(self):
        """Return LLM gateway instance (separate method for test patching)."""
        from llm_shared.gateway import get_llm_gateway

        return get_llm_gateway()

    async def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        model_name: str,
    ) -> str:
        """Generate summary of conversation messages using LLM.

        Args:
            messages: List of message dicts with 'sender' and 'text' fields.
            model_name: LLM model to use for summarization.

        Returns:
            Summary text. Returns placeholder on error.
        """
        try:
            gateway = await self._get_gateway()

            # Sanitize orphaned tool messages before formatting
            safe_messages = _sanitize_tool_messages(messages)
            conversation_text = self._format_messages(safe_messages)
            prompt = self._SUMMARIZATION_PROMPT.replace("{{conversation}}", conversation_text).replace(
                "{{count}}", str(len(messages))
            )

            # Generate summary via LLM
            response = await gateway.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.3,  # Low temp for consistent summaries
                max_tokens=500,  # Cap summary length
            )

            summary = response.content.strip()
            if not summary:
                raise ValueError("LLM returned empty summary")

            logger.info(
                "Generated summary for %d messages (%d → %d tokens est.)",
                len(messages),
                sum(len(m.get("text", "")) for m in messages) // 4,
                len(summary) // 4,
            )
            return summary

        except Exception as e:
            logger.error("Summarization failed: %s", e, exc_info=True)
            # Fallback: simple count-based placeholder
            return f"[Summary: {len(messages)} earlier message(s) were summarized to preserve context.]"

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages into readable conversation text.

        Handles both API schema (role/content) and display schema (sender/text).
        """
        lines = []
        for msg in messages:
            role = msg.get("role") or msg.get("sender", "unknown")
            content = msg.get("content") or msg.get("text", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
            if role and content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)


class ContextOverflowProtection:
    """Orchestrates context overflow detection and auto-summarization.

    Monitors cumulative token usage, emits warnings at 80%, and triggers
    auto-summarization at 90% of model context limit.

    Usage::

        protection = ContextOverflowProtection()

        # After each message
        status = await protection.check_and_protect(
            session_id="abc-123",
            model_name="gpt-4",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            mode="auto"
        )

        if status.warning_triggered:
            # Show warning to user
        if status.summary_created:
            # Inject summary into conversation
    """

    def __init__(
        self,
        warning_threshold: float = _DEFAULT_WARNING_THRESHOLD,
        compress_threshold: float = _DEFAULT_COMPRESS_THRESHOLD,
    ):
        """Initialize context overflow protection.

        Args:
            warning_threshold: Percentage (0-1) at which to warn (default 0.80).
            compress_threshold: Percentage (0-1) at which to auto-compress (default 0.90).
        """
        self.warning_threshold = warning_threshold
        self.compress_threshold = compress_threshold
        self.tracker = SessionTokenTracker()
        self.summarizer = ConversationSummarizer()

    async def check_and_protect(
        self,
        session_id: str,
        model_name: str,
        usage: Optional[Dict[str, int]] = None,
        mode: str = "auto",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Check context fill and apply protection if needed.

        Args:
            session_id: Chat session identifier.
            model_name: Active LLM model name.
            usage: Optional token usage dict (prompt_tokens, completion_tokens).
            mode: Protection mode - "auto", "warn_only", or "disabled".
            messages: Full message history (required for summarization).

        Returns:
            Status dict with:
                - warning_triggered: bool
                - summary_created: bool
                - summary_text: str (if summary_created)
                - current_fill_percentage: float
                - total_tokens: int
                - context_limit: int
        """
        # Add tokens to tracker if provided
        if usage:
            await self.tracker.add_message_tokens(
                session_id,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )

        # Get context limit for model
        context_limit = await self._get_context_limit(model_name)

        # Get current usage
        session_usage = await self.tracker.get_session_usage(session_id)
        total_tokens = session_usage["total_tokens"]

        # Calculate fill percentage
        fill_percentage = total_tokens / context_limit if context_limit > 0 else 0

        result = {
            "warning_triggered": False,
            "summary_created": False,
            "summary_text": "",
            "current_fill_percentage": fill_percentage,
            "total_tokens": total_tokens,
            "context_limit": context_limit,
        }

        # Check thresholds
        if mode == "disabled":
            return result

        if fill_percentage >= self.warning_threshold:
            result["warning_triggered"] = True
            logger.warning(
                "Session %s approaching context limit: %d/%d tokens (%.1f%%)",
                session_id,
                total_tokens,
                context_limit,
                fill_percentage * 100,
            )

        if mode == "auto" and fill_percentage >= self.compress_threshold:
            # Trigger auto-summarization
            if messages:
                summary = await self._create_summary(session_id, messages, model_name)
                if summary:
                    result["summary_created"] = True
                    result["summary_text"] = summary
                    logger.info(
                        "Auto-summarized session %s: %d messages compressed",
                        session_id,
                        len(messages),
                    )
            else:
                logger.warning(
                    "Auto-summarization triggered but no messages provided for session %s",
                    session_id,
                )

        return result

    async def _get_context_limit(self, model_name: str) -> int:
        """Get context window limit for a model.

        Issue #9294: Uses adaptive budget scaling for models not in YAML config.
        Queries llm_shared registry when available, scales to 85% of discovered
        context window, caps at 200k tokens.
        """
        try:
            from context_window_manager import ContextWindowManager

            manager = ContextWindowManager()
            return manager.get_adaptive_context_length(model_name)
        except Exception as e:
            logger.error("Failed to get context limit for %s: %s", model_name, e)
            return 4096  # Safe fallback

    async def _create_summary(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        model_name: str,
    ) -> str:
        """Create summary and reset token counter."""
        # Determine how many messages to summarize (oldest half)
        split_point = len(messages) // 2
        messages_to_summarize = messages[:split_point]

        if not messages_to_summarize:
            return ""

        # Generate summary
        summary = await self.summarizer.summarize_messages(messages_to_summarize, model_name)

        # Reset token tracker (conversation now starts from summary)
        await self.tracker.reset_session(session_id)

        # Re-add tokens for remaining messages
        for msg in messages[split_point:]:
            # Estimate tokens (rough approximation)
            text = msg.get("text", "")
            estimated_tokens = len(text) // 4
            await self.tracker.add_message_tokens(session_id, prompt_tokens=estimated_tokens)

        return summary


__all__ = [
    "SessionTokenTracker",
    "ConversationSummarizer",
    "ContextOverflowProtection",
]
