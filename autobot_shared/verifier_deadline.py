# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-action verifier's deadline, scaled from how fast the model has recently generated (#22254).

A fixed deadline (``VERIFIER_TIMEOUT_S``) is right for a fast model and wrong for a slow local one: on a model that
makes a few tokens per second the verifier's reply cannot fit in it, so every pass times out and is skipped. The
chat loop records each finished generation's measured rate (``[iteration_timing]``); the verifier's own deadline is
the time its reply needs at that rate, with headroom, bounded below by the configured ``VERIFIER_TIMEOUT_S`` and
above by ``AUTOBOT_VERIFIER_TIMEOUT_MAX_S`` (default 512 s: a 512-token reply at 2 tok/s is 256 s, times
the headroom factor). A ``VERIFIER_TIMEOUT_S`` set in the environment is the
operator's explicit value and always wins. With no measured rate the configured value stands.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Tuple

from autobot_shared.env_utils import env_registered

#: How long a measured rate stays usable: a model's speed changes with load, offload and thermal state.
RATE_MAX_AGE_S = env_registered("AUTOBOT_VERIFIER_RATE_MAX_AGE_S", positive_finite=True)

#: Headroom over the time the reply needs at the measured rate (prompt evaluation and load are not in the rate).
HEADROOM_FACTOR = env_registered("AUTOBOT_VERIFIER_HEADROOM_FACTOR", positive_finite=True)

_rates: Dict[str, Tuple[float, float]] = {}  # model -> (tokens per second, monotonic time noted); per model only


def note_generation_rate(model: str, tokens_per_second: float) -> None:
    """Record the rate one finished generation of *model* ran at; a non-positive rate is no measurement."""
    if model and tokens_per_second > 0:
        _rates[model] = (tokens_per_second, time.monotonic())


def clear_generation_rates() -> None:
    """Forget every measured rate (a test seam)."""
    _rates.clear()


def _chat_model_names() -> list[str]:
    """The chat model of this request, then the configured one: the names the chat's own rate may be noted under."""
    from autobot_shared.chat_model_context import _last_turn_model
    from autobot_shared.ssot_config import config

    return [name for name in (_last_turn_model.get(), config.default_llm_model) if name]


def recent_tokens_per_second(model: str | None, reuses_chat: bool = False) -> float | None:
    """*model*'s own measured rate; None when stale or unknown.

    The chat model's rate stands in ONLY when the verifier reuses the chat model (*reuses_chat*): a different
    verifier model runs at its own speed, and the chat's would mis-size its deadline (#22254).
    """
    names = [model] if model else []
    if reuses_chat:
        names += _chat_model_names()
    for name in names:
        entry = _rates.get(name)
        if entry and time.monotonic() - entry[1] <= RATE_MAX_AGE_S:
            return entry[0]
    return None


def verifier_deadline_s(
    model: str | None,
    reply_tokens: int,
    floor_s: float,
    ceiling_s: float | None = None,
    explicit: bool | None = None,
    reuses_chat: bool = False,
) -> float:
    """Seconds the verifier call may take: the reply's size at the recent rate, within [*floor_s*, *ceiling_s*].

    *ceiling_s* defaults to ``AUTOBOT_VERIFIER_TIMEOUT_MAX_S``; *explicit* to whether ``VERIFIER_TIMEOUT_S`` is
    set in the environment, in which case *floor_s* is returned as is. *reuses_chat*: the verifier asks the chat
    model, so that model's rate applies.
    """
    if explicit is None:
        explicit = "VERIFIER_TIMEOUT_S" in os.environ
    if ceiling_s is None:
        ceiling_s = env_registered("AUTOBOT_VERIFIER_TIMEOUT_MAX_S", positive_finite=True)
    rate = None if explicit else recent_tokens_per_second(model, reuses_chat)
    if rate is None:
        return floor_s
    return max(floor_s, min(reply_tokens / rate * HEADROOM_FACTOR, max(ceiling_s, floor_s)))
