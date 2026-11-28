# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Validation of an LLM-produced routing decision (#19649).

The routing model's reply is untrusted: user text is in the prompt, so injected text
can steer it. A reply is accepted only as a dict of a known strategy, known agents,
and a numeric confidence (clamped to [0, 1]); an agent that runs commands, or that
nobody classified, is never chosen by the model. Anything else is a violation, and
the caller falls back to quick routing.
"""

import math
from typing import Any, Dict, List, Tuple

from autobot_shared.env_utils import env_float

from .capability_requirements import llm_route_refused
from .types import AgentType

#: Seconds the routing LLM call may take before quick routing is used instead.
ROUTING_LLM_TIMEOUT_SECONDS = env_float("AUTOBOT_ROUTING_LLM_TIMEOUT_SECONDS", 8.0)

_STRATEGIES = frozenset({"single_agent", "multi_agent", "orchestrator_analysis"})
_STRATEGIES_NEEDING_PRIMARY = frozenset({"single_agent", "multi_agent"})


def _agents(parsed: Dict[str, Any], key: str) -> List[AgentType]:
    """The named agents under *key* as ``AgentType``; raises ``ValueError`` on a bad shape or name."""
    raw = parsed.get(key)
    if raw is None:
        return []
    names = raw if key == "secondary_agents" else [raw]
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError(f"{key} must be an agent name" + (" list" if key == "secondary_agents" else ""))
    return [AgentType(name) for name in names]


def _confidence(parsed: Dict[str, Any]) -> float | None:
    """The confidence clamped to [0, 1]; None when absent; ``ValueError`` when not a finite number."""
    value = parsed.get("confidence")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("confidence must be a finite number")
    return min(1.0, max(0.0, float(value)))


def _checked_fields(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """The validated decision fields; raises ``ValueError`` naming the first violation."""
    strategy = parsed.get("strategy")
    if strategy not in _STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    primary = _agents(parsed, "primary_agent")
    secondary = _agents(parsed, "secondary_agents")
    if strategy in _STRATEGIES_NEEDING_PRIMARY and not primary:
        raise ValueError(f"strategy {strategy} needs a primary_agent")
    refused = llm_route_refused([a.value for a in [*primary, *secondary]])
    if refused:
        raise ValueError(f"model may not route to {', '.join(refused)}")
    confidence = _confidence(parsed)
    reasoning = parsed.get("reasoning", "")
    fields: Dict[str, Any] = {"strategy": strategy, "reasoning": reasoning if isinstance(reasoning, str) else ""}
    if primary:
        fields["primary_agent"] = primary[0]
    if secondary:
        fields["secondary_agents"] = secondary
    if confidence is not None:
        fields["confidence"] = confidence
    return fields


def validate_routing_decision(parsed: Any) -> Tuple[Dict[str, Any] | None, str]:
    """``(decision, "")`` for a valid reply, ``(None, reason)`` for a violation."""
    if not isinstance(parsed, dict):
        return None, f"reply is {type(parsed).__name__}, not an object"
    try:
        return _checked_fields(parsed), ""
    except ValueError as exc:
        return None, str(exc)
