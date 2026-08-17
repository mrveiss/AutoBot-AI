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

import json
import os
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import decode_redis_value
from autobot_shared.ssot_constants import CategoryDefaults
from autobot_shared.token_count import estimate_fast
from autobot_shared.tool_catalogue import FILE_WRITE_TOOLS, SHELL_EXEC_TOOLS, match_tool_name

logger = get_logger(__name__)

# Redis key prefixes
_TOKEN_TRACKER_KEY_PREFIX = "chat:tokens:"  # nosec B105  # Redis key prefix, not a password
_SUMMARY_MARKER_KEY_PREFIX = "chat:summary_marker:"

# Default thresholds (can be overridden)
_DEFAULT_WARNING_THRESHOLD = 0.80  # 80%
_DEFAULT_COMPRESS_THRESHOLD = 0.90  # 90%

# How long to skip compaction after it fails, so a rate-limited provider costs
# one attempt per window instead of one per turn (#14065 review).
_SUMMARY_FAILURE_BACKOFF_SECONDS = int(os.getenv("AUTOBOT_SUMMARY_FAILURE_BACKOFF_SECONDS", "300"))

# How many of the most recent user messages cross a compaction verbatim (#14066).
# Bounded so repeated compaction cannot grow the preserved set without limit —
# the bound is what makes preserving them unconditionally safe.
_PRESERVED_USER_MESSAGE_CAP = int(os.getenv("AUTOBOT_COMPACTION_USER_MESSAGE_CAP", "40"))

# Tool results in the summarized region are clipped to this many characters
# before the summarizer sees them: a file read many turns ago is cheaper to
# re-read than to carry (#14066).
_TOOL_RESULT_CLIP_CHARS = int(os.getenv("AUTOBOT_COMPACTION_TOOL_RESULT_CLIP_CHARS", "400"))

# How far back to look for a user turn before settling for any turn start.
_BOUNDARY_SEARCH_WINDOW = int(os.getenv("AUTOBOT_COMPACTION_BOUNDARY_WINDOW", "10"))

# Most recent shell commands named in the extracted state block.
_STATE_COMMAND_CAP = int(os.getenv("AUTOBOT_COMPACTION_STATE_COMMAND_CAP", "10"))


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

            # add_message_tokens hincrby's str field names and the shared client is
            # decode_responses=True, so hgetall yields str keys. Probing with bytes
            # literals always missed and every counter read back 0 (#13274).
            return {
                "total_tokens": int(decode_redis_value(data.get("total_tokens")) or 0),
                "prompt_tokens": int(decode_redis_value(data.get("prompt_tokens")) or 0),
                "completion_tokens": int(decode_redis_value(data.get("completion_tokens")) or 0),
                "message_count": int(decode_redis_value(data.get("message_count")) or 0),
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

    async def mark_summarization_failed(self, session_id: str) -> None:
        """Back off compaction for this session after a failure (#14065 review).

        Without this, a failing provider wedges the session permanently.
        Compaction is awaited *inline* on the chat request path, under the
        ``chat_timeout`` budget (``api/chat.py``), and the token tracker is
        correctly left un-reset on failure — so fill never drops and every
        subsequent turn spends the same time failing the same way, timing out a
        turn whose answer was already generated and stored.

        The marker bounds that to one attempt per backoff window. It is
        deliberately best-effort: with Redis down the marker cannot be written,
        and retrying every turn is the safer of the two failures.
        """
        redis = await self._ensure_redis()
        if not redis:
            return

        try:
            await redis.setex(f"{_SUMMARY_MARKER_KEY_PREFIX}{session_id}", _SUMMARY_FAILURE_BACKOFF_SECONDS, "failed")
        except Exception as e:
            logger.error("Failed to mark summarization failure for session %s: %s", session_id, e)

    async def summarization_recently_failed(self, session_id: str) -> bool:
        """True while the backoff window from a previous failure is still open."""
        redis = await self._ensure_redis()
        if not redis:
            return False

        try:
            return bool(await redis.exists(f"{_SUMMARY_MARKER_KEY_PREFIX}{session_id}"))
        except Exception as e:
            logger.error("Failed to read summarization marker for session %s: %s", session_id, e)
            return False


def _message_text(msg: object) -> str:
    """The text of a message, for token estimation, on any input (#14065 review).

    ``estimate_fast`` needs a string. A non-dict entry or a non-string ``text``
    (a provider emitting ``None``, an int, a content-part list) used to raise
    here — after the token tracker had already been reset.

    #14066: reads **both** schemas. This used to read only ``text``, so every
    API-schema message (``role``/``content``) estimated as 0 tokens and the
    post-compaction refill under-counted the retained half — which delays the
    next compaction rather than triggering it early, so nothing surfaced it.
    ``_format_messages`` already handled both; this did not.
    """
    if not isinstance(msg, dict):
        return ""
    value = msg.get("content")
    if isinstance(value, list):
        value = " ".join(_text_parts(value))
    if not isinstance(value, str) or not value:
        value = msg.get("text", "")
    return value if isinstance(value, str) else ""


def _text_parts(parts: list) -> List[str]:
    """The string ``text`` fields of a multimodal content list.

    Non-dict entries, non-text parts, and a ``text`` that is not a string are
    all skipped rather than joined: providers genuinely emit ``text: None``, and
    this helper runs outside ``summarize_messages``' try, so raising here 500s a
    turn whose answer was already generated and stored (#14065 review).
    """
    out: List[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = part.get("text")
        if isinstance(text, str):
            out.append(text)
    return out


def _role_of(msg: object) -> str:
    """Role across both schemas: ``role`` (API) or ``sender`` (display)."""
    if not isinstance(msg, dict):
        return ""
    role = msg.get("role") or msg.get("sender") or ""
    return role if isinstance(role, str) else ""


def _pick_boundary(messages: List[Dict], target: int) -> int:
    """Snap *target* back to a turn start, preferring a user turn (#14066).

    ``len(messages) // 2`` is an index, not a boundary: it can land on a
    ``role="tool"`` message whose assistant parent sits earlier, orphaning the
    responses in the kept half. A tool message is therefore never a valid cut
    point; anything else is, because a batch cut *before* its assistant parent
    keeps the whole batch together.

    Both searches floor at index 1, never 0. Returning 0 would summarize *no*
    messages while the caller's early return skips the tracker reset — so the
    session stays over threshold and re-attempts compaction every single turn.
    A short history whose only user turn is its first message hits this
    immediately, and it reads as "compaction is enabled" the whole time.
    Index 0 is returned only when no valid cut point exists at all.
    """
    if not messages:
        return 0
    target = max(0, min(target, len(messages) - 1))
    floor = max(1, target - _BOUNDARY_SEARCH_WINDOW)
    for idx in range(target, floor - 1, -1):
        if _role_of(messages[idx]) == CategoryDefaults.ROLE_USER:
            return idx
    for idx in range(target, 0, -1):
        if _role_of(messages[idx]) != "tool":
            return idx
    return 0


def _preserved_user_messages(messages: List[Dict], cap: int) -> List[str]:
    """The most recent *cap* user messages, verbatim (#14066).

    Never summarized within the round that summarizes them, so a constraint the
    user stated once cannot be dropped by that pass; the cap is what keeps this
    unconditionally bounded.

    Scoped to raw ``role == "user"`` turns, not to a *prior* compaction's own
    composed summary (#14322). That artifact is injected with ``sender ==
    "system"`` (``overflow_integration.create_summary_message``), so it is
    never picked up here — and it should not be: its "### User messages
    (verbatim)" block is prose to a later summarization call, not a
    deterministic structure this function can re-extract without re-parsing
    the model's own markdown, which is the "prose, not guarantee" failure mode
    #14066 introduced this deterministic path to avoid. A user turn already
    protected once and later swept — inside its parent summary — into a
    further compaction window is not re-protected by a second pass.
    """
    if cap <= 0:
        return []
    texts = [_message_text(m) for m in messages if _role_of(m) == CategoryDefaults.ROLE_USER]
    return [t for t in texts if t][-cap:]


def _clip_tool_results(messages: List[Dict], max_chars: int) -> List[Dict]:
    """Clip oversized tool results before summarization (#14066).

    Returns a new list; the caller's messages are never mutated — the persisted
    transcript is untouched and only the summarizer's input is reduced.
    """
    clipped: List[Dict] = []
    for msg in messages:
        body = _message_text(msg)
        if _role_of(msg) != "tool" or len(body) <= max_chars:
            clipped.append(msg)
            continue
        copy = dict(msg)
        copy[_body_key(msg)] = body[:max_chars] + "… [clipped]"
        clipped.append(copy)
    return clipped


def _body_key(msg: Dict) -> str:
    """The key whose value ``_message_text`` read, so a rewrite lands where it is read.

    Keying on ``isinstance(content, str)`` alone was wrong twice: a tool result
    whose ``content`` is a multimodal *list* would have its clipped body written
    to ``text`` while ``_format_messages`` still read the untouched list, and an
    empty-string ``content`` beside a populated ``text`` would have the clip
    written to ``content`` where the ``content or text`` fallback skips it. Both
    leave the full body reaching the summarizer while the clip looks applied —
    an empty result reading as a clean one.
    """
    content = msg.get("content")
    if isinstance(content, list):
        return "content" if _text_parts(content) else "text"
    return "content" if isinstance(content, str) and content else "text"


def _tool_calls_of(msg: object) -> List[Dict]:
    """The tool calls on a message, or an empty list on any other shape."""
    if not isinstance(msg, dict):
        return []
    calls = msg.get("tool_calls")
    return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []


def _call_name_and_args(call: Dict) -> "tuple[str, Dict]":
    """``(name, arguments)`` for one tool call; ``("", {})`` on any bad shape."""
    fn = call.get("function") if isinstance(call.get("function"), dict) else call
    name = fn.get("name")
    raw = fn.get("arguments", fn.get("args", {}))
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    return (name if isinstance(name, str) else ""), (raw if isinstance(raw, dict) else {})


def _extract_state(messages: List[Dict]) -> Dict[str, List[str]]:
    """State that crosses the boundary without a model call (#14066).

    Deterministic: files written, shell commands run, tools used — read straight
    off the tool calls. This is the part that still works when the summary is
    bad, which is the whole reason it exists. Tool-name matching reuses the
    canonical catalogue rather than a local literal list.
    """
    files: List[str] = []
    commands: List[str] = []
    tools: List[str] = []
    for msg in messages:
        for call in _tool_calls_of(msg):
            name, args = _call_name_and_args(call)
            if not name:
                continue
            if name not in tools:
                tools.append(name)
            if match_tool_name(name, FILE_WRITE_TOOLS):
                path = args.get("path") or args.get("file_path")
                if isinstance(path, str) and path and path not in files:
                    files.append(path)
            elif match_tool_name(name, SHELL_EXEC_TOOLS):
                command = args.get("command")
                if isinstance(command, str) and command:
                    commands.append(command)
    return {"files_written": files, "commands": commands, "tools_used": tools}


def _render_state_block(state: Dict[str, List[str]]) -> str:
    """Render extracted state, or "" when nothing was extracted."""
    lines = []
    if state["files_written"]:
        lines.append("**Files written:** " + ", ".join(state["files_written"]))
    if state["commands"]:
        lines.append("**Commands run:** " + "; ".join(state["commands"][-_STATE_COMMAND_CAP:]))
    if state["tools_used"]:
        lines.append("**Tools used:** " + ", ".join(state["tools_used"]))
    if not lines:
        return ""
    return "### Retained state (extracted, not inferred)\n" + "\n".join(lines)


def _compose_summary(summary: str, summarized: List[Dict]) -> str:
    """Model summary + extracted state + verbatim user turns (#14066)."""
    parts = [summary]
    block = _render_state_block(_extract_state(summarized))
    if block:
        parts.append(block)
    preserved = _preserved_user_messages(summarized, _PRESERVED_USER_MESSAGE_CAP)
    if preserved:
        parts.append("### User messages (verbatim)\n" + "\n".join(f"- {t}" for t in preserved))
    return "\n\n".join(parts)


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
        # #14065 review: this runs outside summarize_messages' try, so a
        # non-dict entry here would escape as an AttributeError and 500 a turn
        # whose answer was already generated and stored. Malformed history is
        # data, not a programming error — skip the entry and keep compacting.
        if not isinstance(m, dict):
            logger.warning("Skipping non-dict message during tool sanitization: %r", type(m).__name__)
            in_batch = False
            continue
        role = m.get("role")
        if role == "tool":
            if in_batch:
                cleaned.append(m)
            # else: orphan — drop silently
            continue
        if role == CategoryDefaults.ROLE_ASSISTANT and m.get("tool_calls"):
            in_batch = True
        else:
            in_batch = False
        cleaned.append(m)
    return cleaned


class SummarizationFailed(RuntimeError):
    """Summarization did not produce a usable summary (#14065).

    Raised instead of returning a placeholder string. The placeholder read like
    a successful compaction — "[Summary: N earlier message(s) were summarized to
    preserve context.]" — so the caller reset the token tracker, reported
    ``summary_created: True`` and logged "messages compressed" while the oldest
    half of the conversation had in fact been replaced by a sentence containing
    none of the goals, decisions, file paths or state the summarization prompt
    exists to preserve.

    Failure has to be *shaped* differently from success, not merely logged
    differently. A ``logger.error`` in one line and a truthy return value in the
    next is a failure the caller cannot see.
    """


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
            Summary text.

        Raises:
            SummarizationFailed: The gateway errored, or returned nothing usable.
                Never a placeholder — see that exception's docstring (#14065).
        """
        # Deliberately outside the try: these are pure, local transformations of
        # the caller's own data. A bug in _sanitize_tool_messages or
        # _format_messages is a programming error and must surface as itself,
        # not be relabelled "summarization failed" and retried forever (#14065).
        safe_messages = _sanitize_tool_messages(messages)
        conversation_text = self._format_messages(safe_messages)
        prompt = self._SUMMARIZATION_PROMPT.replace("{{conversation}}", conversation_text).replace(
            "{{count}}", str(len(messages))
        )

        try:
            gateway = await self._get_gateway()
            response = await gateway.chat_completion(
                messages=[{"role": CategoryDefaults.ROLE_USER, "content": prompt}],
                model=model_name,
                temperature=0.3,  # Low temp for consistent summaries
                max_tokens=500,  # Cap summary length
            )
            summary = (getattr(response, "content", None) or "").strip()
        except Exception as exc:
            logger.error("Summarization failed for %d messages: %s", len(messages), exc, exc_info=True)
            raise SummarizationFailed(f"summarization call failed: {exc}") from exc

        if not summary:
            logger.error("Summarization returned an empty completion for %d messages", len(messages))
            raise SummarizationFailed("LLM returned empty summary")

        logger.info(
            "Generated summary for %d messages (%d → %d tokens est.)",
            len(messages),
            sum(len(_message_text(m)) for m in messages) // 4,
            len(summary) // 4,
        )
        return summary

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages into readable conversation text.

        Handles both API schema (role/content) and display schema (sender/text).
        """
        lines = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") or msg.get("sender", "unknown")
            content = msg.get("content") or msg.get("text", "")
            if isinstance(content, list):
                # #14065 review: a multimodal part with ``text: None`` is a shape
                # providers genuinely emit, and ``" ".join`` raises TypeError on
                # it. This method runs outside the try, so that escaped as a 500
                # on the live chat path. Skip the part instead — a summary
                # missing one empty fragment is not a failure.
                content = " ".join(
                    p["text"]
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str)
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
            # Always present so a caller can branch on it without a KeyError.
            # Empty means "no attempt failed", not "no attempt was made" —
            # summary_created distinguishes those two (#14065).
            "summary_error": "",
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
                await self._attempt_summary(session_id, messages, model_name, result)
            else:
                logger.warning(
                    "Auto-summarization triggered but no messages provided for session %s",
                    session_id,
                )

        return result

    async def _attempt_summary(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        model_name: str,
        result: Dict[str, Any],
    ) -> None:
        """Run compaction once and record the outcome into *result* (#14065)."""
        if await self.tracker.summarization_recently_failed(session_id):
            # Compaction is awaited inline under the chat request's wall-clock
            # budget. Retrying every turn against a provider that is already
            # rate-limiting turns a degraded session into a dead one.
            result["summary_error"] = "summarization recently failed; backing off"
            logger.warning("Skipping auto-summarization for session %s: recent failure, backing off", session_id)
            return

        try:
            summary = await self._create_summary(session_id, messages, model_name)
        except SummarizationFailed as exc:
            # The history is intact and the tracker was not reset, so the session
            # is still over threshold. Reporting this instead of swallowing it is
            # the point: a caller that cannot see the failure keeps talking to an
            # agent that has silently forgotten half the work (#14065).
            result["summary_error"] = str(exc)
            await self.tracker.mark_summarization_failed(session_id)
            logger.error(
                "Auto-summarization FAILED for session %s: %s — history left intact, token counter not reset",
                session_id,
                exc,
            )
            return

        if summary:
            result["summary_created"] = True
            result["summary_text"] = summary
            logger.info("Auto-summarized session %s: %d messages compressed", session_id, len(messages))

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
        # #14066: snap the midpoint back to a turn start. The raw index could
        # fall between an assistant's tool_calls and its tool responses, leaving
        # orphans in the *kept* half — _sanitize_tool_messages repairs only the
        # summarizer's input, never the half that continues to the provider.
        split_point = _pick_boundary(messages, len(messages) // 2)
        messages_to_summarize = messages[:split_point]

        if not messages_to_summarize:
            return ""

        # Generate summary. A SummarizationFailed propagates deliberately: the
        # tracker reset below must not run when the history it claims to have
        # compressed is still uncompressed (#14065). Leaving the counter high is
        # what makes the next turn retry instead of proceeding on a lie.
        summary = await self.summarizer.summarize_messages(
            _clip_tool_results(messages_to_summarize, _TOOL_RESULT_CLIP_CHARS), model_name
        )

        # Estimate BEFORE resetting. #14065 review: this loop used to run after
        # the reset, so a malformed entry in the second half raised with the
        # counter already cleared and the paid-for summary discarded — the same
        # counter-reset-without-a-delivered-summary shape this method exists to
        # prevent, one layer down and not a SummarizationFailed, so the caller's
        # handler did not cover it.
        #
        # #13694: estimate_fast rather than an inline `len(text) // 4` — these
        # are the numbers the 80/90% trigger runs on until the next provider
        # response supplies an authoritative count, so they use the shared path.
        retained_tokens = [estimate_fast(_message_text(msg)) for msg in messages[split_point:]]

        # #14322: composed BEFORE the reset below, same reason as
        # retained_tokens above — every helper behind _compose_summary reads
        # `messages_to_summarize`, the pre-reset history, so it belongs on the
        # same side of the #14065 invariant. Composing after the reset does not
        # raise today (each helper is isinstance-guarded and falls back on an
        # unexpected shape), but it silently violates that invariant one call
        # deeper: a future edit to _extract_state, _render_state_block or
        # _preserved_user_messages that starts reading tracker-derived state
        # would reintroduce #14065 past the caller's `except SummarizationFailed`.
        summary_text = _compose_summary(summary, messages_to_summarize)

        # Reset token tracker (conversation now starts from summary)
        await self.tracker.reset_session(session_id)
        for tokens in retained_tokens:
            await self.tracker.add_message_tokens(session_id, prompt_tokens=tokens)

        return summary_text


__all__ = [
    "SessionTokenTracker",
    "ConversationSummarizer",
    "ContextOverflowProtection",
    "SummarizationFailed",
]
