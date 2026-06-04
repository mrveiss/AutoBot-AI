# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chain-of-Thought event emission helpers (#3232).

Provides non-blocking helpers to emit structured reasoning-trace events
through the existing EventManager WebSocket broadcast path so the
frontend can render live tool calls, LLM steps, and plan decomposition
without any polling.

Event types:
    agent.step.start    – a graph node or agent step is beginning
    agent.step.complete – a graph node or agent step has finished
    agent.tool.call     – a tool call is about to be dispatched
    agent.tool.result   – the result of a tool call has arrived
    agent.llm.chunk     – a streaming LLM token chunk
    agent.plan          – a plan decomposition from the overseer

Sensitive argument keys are redacted before emission so credentials and
tokens never cross the WebSocket boundary.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Sensitive argument key patterns — values for these keys are replaced with
# the placeholder string before the event is sent over WebSocket.
# ---------------------------------------------------------------------------

_REDACTED = "<redacted>"

_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "auth",
        "credential",
        "private_key",
        "privatekey",
        "access_key",
        "accesskey",
        "bearer",
    }
)


def _is_sensitive(key: str) -> bool:
    """Return True if *key* (case-insensitive) matches any sensitive fragment."""
    lower = key.lower()
    return any(fragment in lower for fragment in _SENSITIVE_KEY_FRAGMENTS)


# ---------------------------------------------------------------------------
# CausalLink — typed causal chain entry for cross-event tracing (#3232)
# ---------------------------------------------------------------------------


@dataclass
class CausalLink:
    """A directed causal relationship between two trace events.

    Used to record *why* one agent step triggered another, enabling the
    frontend to render a causal graph of the reasoning trace.

    Attributes:
        source_event_id: ID of the event that caused the transition.
        target_event_id: ID of the event that was triggered.
        reason:          Short machine-readable label for the causal edge.
                         Sensitive fragments (e.g. "token", "password") are
                         redacted in to_dict() before WebSocket emission.
    """

    source_event_id: str
    target_event_id: str
    reason: str

    def to_dict(self) -> dict:
        """Serialise to a plain dict, redacting sensitive reason strings.

        Returns:
            Dict with keys source_event_id, target_event_id, reason where
            reason is replaced with the redaction placeholder when it contains
            any sensitive key fragment.
        """
        safe_reason = _REDACTED if _is_sensitive(self.reason) else self.reason
        return {
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "reason": safe_reason,
        }


def build_causal_chain(
    links: List[Tuple[str, str, str]] | None,
) -> List[CausalLink] | None:
    """Construct a list of CausalLink objects from a compact tuple representation.

    Convenience factory so callers can pass a list of ``(src, tgt, reason)``
    tuples instead of constructing CausalLink instances manually.

    Args:
        links: List of ``(source_event_id, target_event_id, reason)`` tuples,
               or None / empty list.

    Returns:
        List of CausalLink objects, or None when *links* is falsy.
    """
    if not links:
        return None
    return [CausalLink(src, tgt, reason) for src, tgt, reason in links]


def sanitize_arguments(arguments: Any) -> Any:
    """Recursively redact sensitive values in *arguments*.

    Operates on dicts and nested dicts; non-dict values are returned as-is.

    Args:
        arguments: Tool argument dict (or any value).

    Returns:
        A copy with sensitive values replaced by the redaction placeholder.
    """
    if not isinstance(arguments, dict):
        return arguments
    result: dict[str, Any] = {}
    for key, value in arguments.items():
        if _is_sensitive(key):
            result[key] = _REDACTED
        elif isinstance(value, dict):
            result[key] = sanitize_arguments(value)
        else:
            result[key] = value
    return result


def _truncate(value: Any, max_len: int = 512) -> str:
    """Convert *value* to a string and truncate to *max_len* characters."""
    text = str(value)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


# ---------------------------------------------------------------------------
# Causal chain serialization helper
# ---------------------------------------------------------------------------


def _causal_payload(causal_chain: List[CausalLink] | None) -> dict:
    """Return a dict fragment to merge into an event payload for causal chain.

    Returns an empty dict when *causal_chain* is None or empty, so callers
    can always do ``{**base_payload, **_causal_payload(chain)}``.

    Args:
        causal_chain: Optional list of CausalLink objects.

    Returns:
        Dict with a single ``"causal_chain"`` key, or empty dict.
    """
    if not causal_chain:
        return {}
    return {"causal_chain": [link.to_dict() for link in causal_chain]}


# ---------------------------------------------------------------------------
# Low-level publish helper
# ---------------------------------------------------------------------------


def _try_publish(event_type: str, payload: dict) -> None:
    """Fire-and-forget publish to the global EventManager.

    Wraps the publish call in create_task so it never blocks the caller.
    Silently skips if the event bus is unavailable (e.g. in unit tests).

    Args:
        event_type: Dot-namespaced event type string (e.g. "agent.tool.call").
        payload:    Dict payload that will be broadcast to WebSocket clients.
    """
    try:
        from events.bus import PersistStrategy, get_event_bus

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                get_event_bus().publish("global", event_type, payload, persist=PersistStrategy.NONE)
            )
            task.add_done_callback(
                lambda t: (
                    logger.debug("cot_events: publish error: %s", t.exception())
                    if not t.cancelled() and t.exception()
                    else None
                )
            )
        except RuntimeError:
            # No running loop — caller is in a sync context; skip silently.
            logger.debug("cot_events: no running event loop, skipping %s", event_type)
    except Exception as exc:
        logger.debug("cot_events: publish failed for %s: %s", event_type, exc)


# ---------------------------------------------------------------------------
# Public event emitters
# ---------------------------------------------------------------------------


def emit_step_start(
    step_name: str,
    session_id: str | None = None,
    agent_type: str | None = None,
    step_id: str | None = None,
    causal_chain: List[CausalLink] | None = None,
) -> float:
    """Emit an agent.step.start event and return the current monotonic time.

    The returned start_time should be passed to emit_step_complete so the
    duration can be calculated without the caller needing to record it.

    Args:
        step_name:    Human-readable step or node name.
        session_id:   Chat session identifier (forwarded to frontend for routing).
        agent_type:   Optional agent class/type label.
        step_id:      Optional unique identifier for this step instance.
        causal_chain: Optional list of CausalLink objects linking this step to
                      prior trace events.

    Returns:
        Monotonic time float to be passed to emit_step_complete.
    """
    start_time = time.monotonic()
    _try_publish(
        "agent.step.start",
        {
            "step_id": step_id or step_name,
            "step_name": step_name,
            "agent_type": agent_type,
            "session_id": session_id,
            "ts": time.time(),
            **_causal_payload(causal_chain),
        },
    )
    return start_time


def emit_step_complete(
    step_name: str,
    start_time: float,
    output_summary: str | None = None,
    session_id: str | None = None,
    step_id: str | None = None,
    causal_chain: List[CausalLink] | None = None,
) -> None:
    """Emit an agent.step.complete event.

    Args:
        step_name:      Human-readable step name (should match emit_step_start).
        start_time:     Monotonic time returned by emit_step_start.
        output_summary: Optional short description of the step outcome.
        session_id:     Chat session identifier.
        step_id:        Optional unique identifier for this step instance.
        causal_chain:   Optional list of CausalLink objects.
    """
    duration_ms = (time.monotonic() - start_time) * 1000
    _try_publish(
        "agent.step.complete",
        {
            "step_id": step_id or step_name,
            "step_name": step_name,
            "output_summary": _truncate(output_summary) if output_summary else None,
            "duration_ms": round(duration_ms, 1),
            "session_id": session_id,
            "ts": time.time(),
            **_causal_payload(causal_chain),
        },
    )


def emit_tool_call(
    tool_name: str,
    arguments: Any,
    session_id: str | None = None,
    causal_chain: List[CausalLink] | None = None,
) -> float:
    """Emit an agent.tool.call event and return start time.

    Sensitive argument values are automatically redacted before emission.

    Args:
        tool_name:    Name of the tool being called.
        arguments:    Raw tool arguments (may contain sensitive data).
        session_id:   Chat session identifier.
        causal_chain: Optional list of CausalLink objects.

    Returns:
        Monotonic start time to be passed to emit_tool_result.
    """
    start_time = time.monotonic()
    _try_publish(
        "agent.tool.call",
        {
            "tool_name": tool_name,
            "arguments": sanitize_arguments(arguments),
            "session_id": session_id,
            "ts": time.time(),
            **_causal_payload(causal_chain),
        },
    )
    return start_time


def emit_tool_result(
    tool_name: str,
    result: Any,
    start_time: float,
    success: bool = True,
    bridge: str | None = None,
    session_id: str | None = None,
    causal_chain: List[CausalLink] | None = None,
) -> None:
    """Emit an agent.tool.result event.

    Args:
        tool_name:    Name of the tool that was called.
        result:       The tool result (will be truncated for WebSocket safety).
        start_time:   Monotonic time returned by emit_tool_call.
        success:      Whether the tool call succeeded.
        bridge:       Optional MCP bridge identifier.
        session_id:   Chat session identifier.
        causal_chain: Optional list of CausalLink objects.
    """
    duration_ms = (time.monotonic() - start_time) * 1000
    _try_publish(
        "agent.tool.result",
        {
            "tool_name": tool_name,
            "result_summary": _truncate(result),
            "duration_ms": round(duration_ms, 1),
            "success": success,
            "bridge": bridge,
            "session_id": session_id,
            "ts": time.time(),
            **_causal_payload(causal_chain),
        },
    )


def emit_llm_chunk(
    chunk: str,
    session_id: str | None = None,
    causal_chain: List[CausalLink] | None = None,
) -> None:
    """Emit an agent.llm.chunk event for a streaming token.

    This is intentionally lightweight — no start_time or duration tracking.

    Args:
        chunk:        The token or partial token string from the LLM.
        session_id:   Chat session identifier.
        causal_chain: Optional list of CausalLink objects.
    """
    _try_publish(
        "agent.llm.chunk",
        {
            "chunk": chunk,
            "session_id": session_id,
            "ts": time.time(),
            **_causal_payload(causal_chain),
        },
    )


def emit_plan(
    steps: list[Any],
    session_id: str | None = None,
    causal_chain: List[CausalLink] | None = None,
) -> None:
    """Emit an agent.plan event with a list of plan step descriptions.

    Args:
        steps:        List of step dicts or strings from the overseer.
        session_id:   Chat session identifier.
        causal_chain: Optional list of CausalLink objects.
    """
    # Normalise to plain strings for WebSocket safety
    step_labels: list[str] = []
    for step in steps:
        if isinstance(step, dict):
            label = step.get("description") or step.get("name") or str(step)
        else:
            label = str(step)
        step_labels.append(_truncate(label, 200))

    _try_publish(
        "agent.plan",
        {
            "steps": step_labels,
            "step_count": len(step_labels),
            "session_id": session_id,
            "ts": time.time(),
            **_causal_payload(causal_chain),
        },
    )
