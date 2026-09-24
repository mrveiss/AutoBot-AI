# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pre-request cumulative token budget gate (Issue #11541).

OpenManus counts tokens per request, accumulates ``total_input_tokens`` and
refuses to send a request that would exceed ``max_input_tokens`` (adopted
from ``app/llm.py:240-262`` per the umbrella research issue #11536). This
module ports that shape to AutoBot: before a provider call is issued, the
cumulative estimated token spend for the current run is checked against a
configurable ceiling — a request that would exceed it is short-circuited
with an error ``LLMResponse`` (never raised, per the must-not-raise contract
established by #11488/#11499).

Scope: cumulative tokens are tracked per "run" — the caller-supplied
``request.metadata["session_id"]`` when threaded through, else the
per-request ``request.request_id`` (no plumbing required from existing
callers; threading a real session id turns per-request tracking into true
per-conversation tracking).

Counters are stored in Redis (shared across all uvicorn workers, mirroring
``LLMCrossWorkerRateLimiter`` / #8170) and fall back to allow-all when Redis
is unavailable — a Redis outage must never hard-block LLM calls.

EXTENDED for #17091 with a second, named scope: AutoBot's own dev-loop
participation (``autobot-backend/agents/dev_loop_issue_gate.py``), rather than
forking a second module for it. The per-run gate above answers "would this one
LLM call blow the run's ceiling"; the dev-loop gate answers "should AutoBot's
own loop act again at all", and adds a dimension the per-run gate has no
concept of: a rate ceiling (actions per hour), not only a spend ceiling.
Spend stays in TOKEN units, matching this module's own convention, rather than
converting through ``autobot_shared.model_pricing`` for a dollar figure — a
token count is already the unit both this gate and #17092's page need.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from autobot_shared.doc_chunking import estimate_tokens
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .models import LLMRequest, LLMResponse

logger = get_logger(__name__)

# Per-run cumulative token ceiling (input + output). 0 disables the gate —
# #11541 acceptance: "Ceiling disabled by default or set high enough to be
# invisible in normal chat".
TOKEN_BUDGET_PER_RUN: int = env_int("AUTOBOT_LLM_TOKEN_BUDGET_PER_RUN", 0)

# TTL (seconds) for a run's cumulative counter — bounds Redis memory for
# abandoned sessions. Refreshed on every increment, so an active run's
# counter never resets mid-conversation. Default: 24h.
TOKEN_BUDGET_TTL_SECONDS: int = env_int("AUTOBOT_LLM_TOKEN_BUDGET_TTL_SECONDS", 86400)

# #17091: AutoBot's own dev-loop spend ceiling, tokens across all its actions
# (not per-run — the dev loop has no "run" boundary a caller threads through).
# 0 disables the gate, matching TOKEN_BUDGET_PER_RUN's convention.
DEV_LOOP_TOKEN_BUDGET: int = env_int("AUTOBOT_DEV_LOOP_TOKEN_BUDGET", 0)

# TTL for the cumulative dev-loop spend counter. Unlike a per-run counter this
# is not tied to any session ending, so the ceiling is effectively "per this
# many seconds" — refreshed on every increment, same as TOKEN_BUDGET_TTL_SECONDS.
# Default: 24h, i.e. a daily spend ceiling.
DEV_LOOP_BUDGET_TTL_SECONDS: int = env_int("AUTOBOT_DEV_LOOP_BUDGET_TTL_SECONDS", 86400)

# #17091: actions per hour. A fixed-window counter (current UTC hour bucket),
# not sliding — simpler, and "at most N in any given clock hour" is what an
# hourly rate ceiling means here. 0 disables the gate.
DEV_LOOP_RATE_PER_HOUR: int = env_int("AUTOBOT_DEV_LOOP_RATE_PER_HOUR", 0)

_DEV_LOOP_SCOPE = "dev_loop"

# Token estimation delegates to autobot_shared.doc_chunking.estimate_tokens
# (chars/4 — accurate tokenisation is unnecessary for a budget *ceiling*
# check). Canonical estimator per #12764; family convergence for #12645.
_KEY_PREFIX = "autobot:llm:token_budget"


def _estimate_request_tokens(request: LLMRequest) -> int:
    """Estimate this request's token cost: input messages + requested output budget."""
    input_text = "".join(str(m.get("content", "")) for m in request.messages)
    return estimate_tokens(input_text) + (request.max_tokens or 0)


def _estimate_response_tokens(response: LLMResponse) -> int:
    """Estimate a completed response's token cost when the provider didn't report usage."""
    return estimate_tokens(response.content or "")


_HOUR_SECONDS = 3600  # the definition of an hour, not a tunable ceiling -- #17091's budgets are the env vars above


def _current_hour_bucket() -> int:
    """The current UTC hour as an integer bucket id, for the fixed-window rate counter."""
    return int(time.time() // _HOUR_SECONDS)


@dataclass(frozen=True)
class DevLoopBudgetRefusal:
    """Why AutoBot's dev loop stopped before this action (#17091 AC 3).

    Exactly one of ``spend``/``rate`` is why: an action never fails both
    checks in the same evaluation, since spend is checked first and a spend
    refusal returns before the rate check runs.
    """

    reason: str


@dataclass(frozen=True)
class DevLoopBudgetStatus:
    """Remaining spend and rate, for #17092's page. ``None`` means "no ceiling configured"."""

    spend_used: int
    spend_budget: Optional[int]
    actions_this_hour: int
    rate_budget: Optional[int]


def _scope_key(request: LLMRequest) -> str:
    """Resolve the cumulative-budget scope for *request* (#11541).

    Uses ``metadata['session_id']`` when the caller threads one through
    (true per-conversation tracking); falls back to ``request_id`` so the
    gate works unconditionally, degrading to a per-request ceiling.
    """
    metadata: Dict[str, Any] = request.metadata or {}
    session_id = metadata.get("session_id")
    return str(session_id) if session_id else request.request_id


class TokenBudgetGate:
    """Redis-backed cumulative token budget gate (#11541).

    Shared across all uvicorn workers via Redis, mirroring
    ``LLMCrossWorkerRateLimiter`` (#8170). Never raises — Redis errors and a
    disabled budget (``TOKEN_BUDGET_PER_RUN <= 0``) both resolve to
    allow-all.
    """

    async def evaluate(self, request: LLMRequest) -> Optional[LLMResponse]:
        """Return an error ``LLMResponse`` when *request* would exceed the
        run's budget; ``None`` when the call may proceed."""
        if TOKEN_BUDGET_PER_RUN <= 0:
            return None

        scope = _scope_key(request)
        estimated = _estimate_request_tokens(request)

        try:
            cumulative = await self._get_cumulative(scope)
        except Exception:
            logger.debug("token budget gate: Redis unavailable — allowing request", exc_info=True)
            return None

        if cumulative + estimated <= TOKEN_BUDGET_PER_RUN:
            return None

        logger.warning(
            "token budget gate: run=%s would exceed ceiling (%d + %d > %d) — blocking",
            scope,
            cumulative,
            estimated,
            TOKEN_BUDGET_PER_RUN,
        )
        return LLMResponse(
            content="",
            model=request.model_name or "",
            request_id=request.request_id,
            error=(f"Token budget exhausted for this run ({cumulative}/{TOKEN_BUDGET_PER_RUN} tokens used)."),
        )

    async def record(self, request: LLMRequest, response: LLMResponse) -> None:
        """Add *response*'s actual (or estimated) token usage to the run's cumulative counter."""
        if TOKEN_BUDGET_PER_RUN <= 0:
            return

        used = response.tokens_used or _estimate_response_tokens(response)
        if used <= 0:
            return

        try:
            await self._increment(_scope_key(request), used, TOKEN_BUDGET_TTL_SECONDS)
        except Exception:
            logger.debug("token budget gate: Redis unavailable — usage not recorded", exc_info=True)

    async def evaluate_dev_loop_action(self, estimated_tokens: int) -> Optional[DevLoopBudgetRefusal]:
        """Return why AutoBot's dev loop must stop before this action; ``None`` to proceed.

        Checked before EVERY dev-loop action (#17091 AC 2/3), never after: the
        caller (``dev_loop_issue_gate.run_dev_loop_action``) never invokes its
        action when this returns non-``None``, so nothing is ever partially
        done. Spend is checked before rate -- an action already over budget
        should not also spend a slot in this hour's rate window.
        """
        if DEV_LOOP_TOKEN_BUDGET <= 0 and DEV_LOOP_RATE_PER_HOUR <= 0:
            return None

        try:
            if DEV_LOOP_TOKEN_BUDGET > 0:
                spent = await self._get_cumulative(_DEV_LOOP_SCOPE)
                if spent + estimated_tokens > DEV_LOOP_TOKEN_BUDGET:
                    reason = (
                        f"dev-loop token budget exhausted ({spent}/{DEV_LOOP_TOKEN_BUDGET} "
                        f"tokens used, this action estimated at {estimated_tokens})"
                    )
                    logger.warning("dev loop budget gate: %s", reason)
                    return DevLoopBudgetRefusal(reason=reason)

            if DEV_LOOP_RATE_PER_HOUR > 0:
                actions = await self._get_hourly_rate()
                if actions >= DEV_LOOP_RATE_PER_HOUR:
                    reason = f"dev-loop rate budget exhausted ({actions}/{DEV_LOOP_RATE_PER_HOUR} actions this hour)"
                    logger.warning("dev loop budget gate: %s", reason)
                    return DevLoopBudgetRefusal(reason=reason)
        except Exception:
            logger.debug("dev loop budget gate: Redis unavailable — allowing action", exc_info=True)
            return None

        return None

    async def record_dev_loop_action(self, tokens_used: int) -> None:
        """Record one dev-loop action: its token spend, and one slot in this hour's rate window."""
        try:
            if DEV_LOOP_TOKEN_BUDGET > 0 and tokens_used > 0:
                await self._increment(_DEV_LOOP_SCOPE, tokens_used, DEV_LOOP_BUDGET_TTL_SECONDS)
            if DEV_LOOP_RATE_PER_HOUR > 0:
                await self._increment_hourly_rate()
        except Exception:
            logger.debug("dev loop budget gate: Redis unavailable — action not recorded", exc_info=True)

    async def remaining_dev_loop_budget(self) -> DevLoopBudgetStatus:
        """Current spend and this hour's action count, for #17092's page.

        Never raises: a Redis outage reads as zero usage rather than failing
        the page, matching this module's allow-all-on-outage contract.
        """
        spend_used = 0
        actions_this_hour = 0
        try:
            if DEV_LOOP_TOKEN_BUDGET > 0:
                spend_used = await self._get_cumulative(_DEV_LOOP_SCOPE)
            if DEV_LOOP_RATE_PER_HOUR > 0:
                actions_this_hour = await self._get_hourly_rate()
        except Exception:
            logger.debug("dev loop budget gate: Redis unavailable — reporting zero usage", exc_info=True)
        return DevLoopBudgetStatus(
            spend_used=spend_used,
            spend_budget=DEV_LOOP_TOKEN_BUDGET if DEV_LOOP_TOKEN_BUDGET > 0 else None,
            actions_this_hour=actions_this_hour,
            rate_budget=DEV_LOOP_RATE_PER_HOUR if DEV_LOOP_RATE_PER_HOUR > 0 else None,
        )

    async def _get_cumulative(self, scope: str) -> int:
        redis = await self._get_redis()
        raw = await redis.get(f"{_KEY_PREFIX}:{scope}")
        return int(raw) if raw else 0

    async def _increment(self, scope: str, amount: int, ttl_seconds: int) -> None:
        redis = await self._get_redis()
        key = f"{_KEY_PREFIX}:{scope}"
        await redis.incrby(key, amount)
        await redis.expire(key, ttl_seconds)

    async def _get_hourly_rate(self) -> int:
        redis = await self._get_redis()
        raw = await redis.get(f"{_KEY_PREFIX}:{_DEV_LOOP_SCOPE}:rate:{_current_hour_bucket()}")
        return int(raw) if raw else 0

    async def _increment_hourly_rate(self) -> None:
        redis = await self._get_redis()
        key = f"{_KEY_PREFIX}:{_DEV_LOOP_SCOPE}:rate:{_current_hour_bucket()}"
        await redis.incrby(key, 1)
        await redis.expire(key, _HOUR_SECONDS)

    async def _get_redis(self):
        from autobot_shared.redis_client import get_async_redis_client  # noqa: PLC0415

        return await get_async_redis_client()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

get_token_budget_gate = lazy_singleton(TokenBudgetGate)


__all__ = [
    "TOKEN_BUDGET_PER_RUN",
    "TOKEN_BUDGET_TTL_SECONDS",
    "DEV_LOOP_TOKEN_BUDGET",
    "DEV_LOOP_BUDGET_TTL_SECONDS",
    "DEV_LOOP_RATE_PER_HOUR",
    "DevLoopBudgetRefusal",
    "DevLoopBudgetStatus",
    "TokenBudgetGate",
    "get_token_budget_gate",
]
