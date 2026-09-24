# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Anthropic request-kwargs shaping — pure, no SDK, no I/O (extracted #17305).

``providers/anthropic.py`` was 593 lines against a 600-line ceiling
(``scripts/check_python_file_size.py``); #17305's import and ``output_config``
merge took it to 597, and the two capability declarations it still needed would
have crossed 600. The ceiling's answer is to split, not to raise it
(``docs/developer/RATCHET_BASELINES.md``), so the
request-shaping unit moved here: it is the half of the provider that takes a
kwargs dict and returns a kwargs dict, with no client, no await and no
response in it.

``anthropic.py`` re-exports these names, so
``from llm_shared.providers.anthropic import _route_sampling_kwargs`` keeps
resolving for its existing importers (``providers/vertexai.py``,
``modern_ai_integration.py``, and the two sampling-kwargs test modules) —
the ``agent_loop/pre_action_verifier.py`` precedent, where the decision
surface moved and the old module stayed a true re-export.
"""

from __future__ import annotations

from typing import Any, Dict, List

from constants.model_constants import ANTHROPIC_CLAUDE_OPUS4_6

# #15016: anthropic>=1.0 removed these three from messages.create()/.stream();
# passing one as a keyword now raises TypeError. The API still honours them
# via extra_body for every model this provider targets, so a genuinely-set
# value is routed there instead of being dropped.
_REMOVED_SAMPLING_KWARGS = ("temperature", "top_p", "top_k")

# Models the SDK itself flags as deprecated for thinking.type="enabled" in
# favour of "adaptive" (mirrors anthropic's own
# MODELS_TO_WARN_WITH_THINKING_ENABLED, restricted to models this repo uses).
_MODELS_REQUIRING_ADAPTIVE_THINKING = frozenset({ANTHROPIC_CLAUDE_OPUS4_6})

# budget_tokens -> output_config.effort tiers for models that require adaptive
# thinking; mirrors the low/medium/high buckets reasoning_effort.py already
# maps reasoning_effort levels to, extended with xhigh/max for larger budgets.
_THINKING_EFFORT_TIERS = (
    (2000, "low"),
    (5000, "medium"),
    (10000, "high"),
    (32000, "xhigh"),
)


def _route_sampling_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Move a set temperature/top_p/top_k out of top-level kwargs, in place.

    Returns *kwargs* for convenient chaining. Dropped outright (#15042) when
    extended thinking is active -- current models reject a sampling kwarg
    regardless of its value once thinking is enabled, so extra_body would
    just move the 400 server-side. An explicit ``None`` is also dropped (no
    genuine dependency to preserve); any other value is merged into
    ``extra_body`` so the SDK still forwards it to the API.
    """
    thinking_active = "thinking" in kwargs
    sampling = {}
    for key in _REMOVED_SAMPLING_KWARGS:
        value = kwargs.pop(key, None)
        if value is not None and not thinking_active:
            sampling[key] = value
    if sampling:
        kwargs.setdefault("extra_body", {}).update(sampling)
    return kwargs


def _thinking_budget_to_effort(budget_tokens: int) -> str:
    """Map a legacy ``budget_tokens`` value to an adaptive-thinking effort tier."""
    for ceiling, effort in _THINKING_EFFORT_TIERS:
        if budget_tokens <= ceiling:
            return effort
    return "max"


def _apply_thinking_budget(api_kwargs: Dict[str, Any], model: str, thinking_tokens: int) -> None:
    """Expand a thinking-token budget into the SDK's ``thinking`` kwarg, in place.

    Models in ``_MODELS_REQUIRING_ADAPTIVE_THINKING`` (#15016) get adaptive
    thinking plus an ``output_config`` effort tier instead of ``budget_tokens``;
    every other model keeps the fixed-budget form it still accepts.
    """
    if model in _MODELS_REQUIRING_ADAPTIVE_THINKING:
        api_kwargs["thinking"] = {"type": "adaptive"}
        api_kwargs["output_config"] = {"effort": _thinking_budget_to_effort(thinking_tokens)}
    else:
        api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_tokens}
        api_kwargs.setdefault("betas", ["interleaved-thinking-2025-05-14"])
    api_kwargs.setdefault("max_tokens", max(thinking_tokens + 1000, 8192))


def _build_api_kwargs(
    base: Dict[str, Any],
    api_kwargs: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Merge caller-supplied *api_kwargs* into *base* request parameters.

    Handles the three extended-thinking keys that need special treatment:

    - ``thinking``      — forwarded directly to the SDK call.
    - ``betas``         — converted to ``extra_headers["anthropic-beta"]`` as a
                          comma-joined string; the SDK does not accept a ``betas``
                          kwarg on ``messages.create()``.
    - ``extra_headers`` — collected separately for the SDK ``extra_headers``
                          keyword argument (not part of the messages payload).
    - ``preserve_reasoning`` — consumed here; not forwarded to the SDK.

    All remaining keys in *api_kwargs* (e.g. ``max_tokens``, ``temperature``)
    are merged into *base*, overriding any previously set value.

    Returns:
        (merged_kwargs, extra_headers)
    """
    extra_headers: Dict[str, Any] = {}
    preserved_keys = {"preserve_reasoning", "extra_headers", "betas"}

    for key, value in api_kwargs.items():
        if key in preserved_keys:
            continue
        base[key] = value

    extra_headers = dict(api_kwargs.get("extra_headers") or {})

    betas: List[str] = api_kwargs.get("betas") or []
    if betas:
        existing = extra_headers.get("anthropic-beta", "")
        merged_betas = [b for b in existing.split(",") if b] + list(betas)
        extra_headers["anthropic-beta"] = ",".join(merged_betas)

    return base, extra_headers


__all__ = [
    "_MODELS_REQUIRING_ADAPTIVE_THINKING",
    "_REMOVED_SAMPLING_KWARGS",
    "_THINKING_EFFORT_TIERS",
    "_apply_thinking_budget",
    "_build_api_kwargs",
    "_route_sampling_kwargs",
    "_thinking_budget_to_effort",
]
