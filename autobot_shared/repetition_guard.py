# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repetition guard for the production tool seam (#13590).

The guard machinery existed in ``agent_loop/`` and ran nowhere: the live path's
only countermeasure was a sentence in the system prompt
(``chat_workflow/manager.py``: "Do NOT repeat commands already executed"), and
the only counter was ``consecutive_invalid_tool_calls``, which counts
*malformed* calls rather than repeated valid ones. An agent calling the same
tool with the same arguments forever was stopped only by the iteration ceiling.

**The counter key is a pair: (call fingerprint, result hash).** Counting calls
alone would halt a polling loop, which is a legitimate pattern — the same call
re-issued until the result moves. Keying on the pair means the count resets the
moment the result changes, so polling survives any threshold and only a call
literally reproducing a result it already has is halted. That is the definition
of the failure this guard exists for.

Thresholds come from ``agent_loop.guard_profile`` rather than new environment
variables, so ``AUTOBOT_GUARD_PROFILE`` finally governs the live path — it has
read as a hardening control while changing nothing in production.

State is passed in by the caller and lives on the per-turn
``LLMIterationContext``; nothing here is module-global, because the seam is
concurrent across sessions.
"""

from typing import Any, Dict, Optional, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Key under which the caller stores this guard's per-turn state.
REPETITION_STATE_KEY = "_repetition_guard"

# Tools whose whole purpose is to be re-issued until something changes. A
# changing result already exempts them via the pair key; this covers the case
# where the result is legitimately identical between polls.
POLLABLE_TOOLS = frozenset({"sleep", "wait", "poll", "check_status"})


def _canonical_args(tool_call: Dict[str, Any]) -> Any:
    """Return the argument bag under whichever key this call site used."""
    return tool_call.get("params") or tool_call.get("arguments") or {}


def call_fingerprint(tool_call: Dict[str, Any]) -> str:
    """Stable hash of ``(tool name, canonical args)``."""
    from agent_loop.fingerprint import content_hash  # noqa: PLC0415

    return content_hash([tool_call.get("name", ""), _canonical_args(tool_call)])


def last_result_hash(tool_name: str, execution_results: list) -> Optional[str]:
    """Hash of the most recent result recorded for *tool_name*, or ``None``.

    Reads the results the seam has already collected this turn rather than
    requiring a post-dispatch hook, so the guard stays a single pre-dispatch
    check like every other ``_enforce_*`` at this seam.
    """
    from agent_loop.fingerprint import content_hash  # noqa: PLC0415

    for entry in reversed(execution_results or []):
        if isinstance(entry, dict) and entry.get("tool") == tool_name:
            return content_hash(entry.get("result", entry.get("error", "")))
    return None


def max_identical_tool_calls() -> int:
    """Resolve the active threshold from the guard profile (#13590).

    Falls back to the dataclass default when the profile carries no override —
    ``standard`` deliberately carries none, so it reproduces those defaults.
    """
    from agent_loop.guard_profile import resolve_guard_config_overrides  # noqa: PLC0415
    from agent_loop.types import AgentLoopConfig  # noqa: PLC0415

    overrides = resolve_guard_config_overrides()
    value = overrides.get("max_identical_tool_calls", AgentLoopConfig.max_identical_tool_calls)
    try:
        return max(1, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return AgentLoopConfig.max_identical_tool_calls


def register_call(
    tool_call: Dict[str, Any],
    execution_results: list,
    state: Dict[str, Tuple[str, int]],
) -> int:
    """Record this call against *state* and return its repetition count.

    ``state`` maps a call fingerprint to ``(last result hash, count)``. A call
    whose previous result differs from the one before it resets the count to 1 —
    that is what keeps a polling loop alive.
    """
    fingerprint = call_fingerprint(tool_call)
    result_hash = last_result_hash(tool_call.get("name", ""), execution_results)

    previous = state.get(fingerprint)
    if previous is None:
        state[fingerprint] = (result_hash or "", 1)
        return 1

    previous_hash, count = previous
    if result_hash is not None and result_hash != previous_hash:
        # The result moved — this is progress, not repetition.
        state[fingerprint] = (result_hash, 1)
        return 1

    count += 1
    state[fingerprint] = (previous_hash, count)
    return count


def repetition_halt_reason(
    tool_call: Dict[str, Any],
    execution_results: list,
    state: Dict[str, Tuple[str, int]],
    threshold: Optional[int] = None,
) -> Optional[str]:
    """Return a user-facing halt reason, or ``None`` to let the call proceed.

    The message names the tool and the count because a silent iteration-cap exit
    is not actionable — "stopped: repeating the same call" is.
    """
    tool_name = tool_call.get("name", "")
    if tool_name in POLLABLE_TOOLS:
        return None

    limit = max_identical_tool_calls() if threshold is None else threshold
    count = register_call(tool_call, execution_results, state)
    if count < limit:
        return None

    logger.warning(
        "repetition_guard: halting %s after %d identical call(s) with an unchanged result",
        tool_name,
        count,
    )
    return (
        f"Stopped: '{tool_name}' has been called {count} times with the same arguments "
        f"and the same result. Repeating it will not produce new information — "
        f"try a different approach, or explain what you need."
    )


__all__ = [
    "POLLABLE_TOOLS",
    "REPETITION_STATE_KEY",
    "call_fingerprint",
    "last_result_hash",
    "max_identical_tool_calls",
    "register_call",
    "repetition_halt_reason",
]
