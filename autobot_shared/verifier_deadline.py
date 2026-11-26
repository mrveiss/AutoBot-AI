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
RATE_MAX_AGE_S = 900.0

#: Headroom over the time the reply needs at the measured rate (prompt evaluation and load are not in the rate).
HEADROOM_FACTOR = 2.0

_rates: Dict[str, Tuple[float, float]] = {}  # model -> (tokens per second, monotonic time noted)
_last_model: str | None = None


def note_generation_rate(model: str, tokens_per_second: float) -> None:
    """Record the rate one finished generation of *model* ran at; a non-positive rate is no measurement."""
    global _last_model
    if model and tokens_per_second > 0:
        _rates[model] = (tokens_per_second, time.monotonic())
        _last_model = model


def clear_generation_rates() -> None:
    """Forget every measured rate (a test seam)."""
    global _last_model
    _rates.clear()
    _last_model = None


def recent_tokens_per_second(model: str | None) -> float | None:
    """*model*'s measured rate, else the rate of the model the chat last generated with; None when stale or unknown."""
    for name in (model, _last_model):
        entry = _rates.get(name) if name else None
        if entry and time.monotonic() - entry[1] <= RATE_MAX_AGE_S:
            return entry[0]
    return None


def verifier_deadline_s(
    model: str | None,
    reply_tokens: int,
    floor_s: float,
    ceiling_s: float | None = None,
    explicit: bool | None = None,
) -> float:
    """Seconds the verifier call may take: the reply's size at the recent rate, within [*floor_s*, *ceiling_s*].

    *ceiling_s* defaults to ``AUTOBOT_VERIFIER_TIMEOUT_MAX_S``; *explicit* to whether ``VERIFIER_TIMEOUT_S`` is
    set in the environment, in which case *floor_s* is returned as is.
    """
    if explicit is None:
        explicit = "VERIFIER_TIMEOUT_S" in os.environ
    if ceiling_s is None:
        ceiling_s = env_registered("AUTOBOT_VERIFIER_TIMEOUT_MAX_S", positive_finite=True)
    rate = None if explicit else recent_tokens_per_second(model)
    if rate is None:
        return floor_s
    return max(floor_s, min(reply_tokens / rate * HEADROOM_FACTOR, max(ceiling_s, floor_s)))
