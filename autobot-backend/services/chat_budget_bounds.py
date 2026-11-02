# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounds on the chat budget gate's reads of the budget store (#16845).

The gate runs before every chat LLM call and every tool-loop iteration, and a
monthly policy reads up to 31 daily keys. Three things keep that cheap and safe:

* a timeout, so a hung store cannot stall every turn;
* a short per-scope spend cache, so a tool loop does not re-read the same keys;
* a throttled failure log, so an outage does not write a traceback per call.

What an unavailable store (error or timeout) does to the request is decided in
exactly one place, :data:`STORE_OUTAGE_ALLOWS_REQUEST`.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from services.budget_policy import get_namespace_period_spend

logger = get_logger(__name__)

#: THE store-outage decision. True: an unreadable budget store lets the request through (fail open, as
#: ``trigger_budget_evaluation`` does). False: the request is refused with ``ChatBudgetUnavailable``.
STORE_OUTAGE_ALLOWS_REQUEST: bool = True

CHECK_TIMEOUT_SECONDS: float = env_float_clamped(
    "AUTOBOT_CHAT_BUDGET_CHECK_TIMEOUT_SECONDS", default=2.0, min_v=0.1, max_v=30.0
)
SPEND_CACHE_TTL_SECONDS: float = env_float_clamped(
    "AUTOBOT_CHAT_BUDGET_SPEND_CACHE_TTL_SECONDS", default=5.0, min_v=0.0, max_v=300.0
)
OUTAGE_LOG_INTERVAL_SECONDS: float = env_float_clamped(
    "AUTOBOT_CHAT_BUDGET_OUTAGE_LOG_INTERVAL_SECONDS", default=60.0, min_v=1.0, max_v=3600.0
)

_spend_cache: Dict[Tuple[str, str, str], Tuple[float, float]] = {}  # key -> (expires_at, spend)
_outage_log = {"last": float("-inf"), "suppressed": 0}


async def cached_spend(namespace: str, subject_id: str, period: str) -> float:
    """``get_namespace_period_spend`` reused for :data:`SPEND_CACHE_TTL_SECONDS`."""
    key, now = (namespace, subject_id, period), time.monotonic()
    hit = _spend_cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    spend = await get_namespace_period_spend(namespace, subject_id, period)
    if SPEND_CACHE_TTL_SECONDS > 0:
        _spend_cache[key] = (now + SPEND_CACHE_TTL_SECONDS, spend)
    return spend


def log_store_failure(what: str, *, exc_info: bool) -> None:
    """Log a budget-store failure at most once per :data:`OUTAGE_LOG_INTERVAL_SECONDS`; count the rest."""
    now = time.monotonic()
    if now - _outage_log["last"] < OUTAGE_LOG_INTERVAL_SECONDS:
        _outage_log["suppressed"] += 1
        return
    skipped, _outage_log["last"], _outage_log["suppressed"] = _outage_log["suppressed"], now, 0
    logger.error("Chat budget store failure: %s (%d similar suppressed)", what, skipped, exc_info=exc_info)


def reset_state() -> None:
    """Forget cached spend and the log throttle (tests, and a policy change that must apply now)."""
    _spend_cache.clear()
    _outage_log.update(last=float("-inf"), suppressed=0)
