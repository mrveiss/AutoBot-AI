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
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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

# Chars-per-token estimate — the same rough approximation already used by
# chat_workflow/compact_hook.py and context_window_manager.py. Accurate
# tokenisation is unnecessary for a budget *ceiling* check.
_CHARS_PER_TOKEN: int = 4

_KEY_PREFIX = "autobot:llm:token_budget"


def _estimate_tokens(char_count: int) -> int:
    """Cheap chars/4 token estimate (matches compact_hook.py convention)."""
    return max(0, char_count // _CHARS_PER_TOKEN)


def _estimate_request_tokens(request: LLMRequest) -> int:
    """Estimate this request's token cost: input messages + requested output budget."""
    input_chars = sum(len(str(m.get("content", ""))) for m in request.messages)
    return _estimate_tokens(input_chars) + (request.max_tokens or 0)


def _estimate_response_tokens(response: LLMResponse) -> int:
    """Estimate a completed response's token cost when the provider didn't report usage."""
    return _estimate_tokens(len(response.content or ""))


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
            await self._increment(_scope_key(request), used)
        except Exception:
            logger.debug("token budget gate: Redis unavailable — usage not recorded", exc_info=True)

    async def _get_cumulative(self, scope: str) -> int:
        redis = await self._get_redis()
        raw = await redis.get(f"{_KEY_PREFIX}:{scope}")
        return int(raw) if raw else 0

    async def _increment(self, scope: str, amount: int) -> None:
        redis = await self._get_redis()
        key = f"{_KEY_PREFIX}:{scope}"
        await redis.incrby(key, amount)
        await redis.expire(key, TOKEN_BUDGET_TTL_SECONDS)

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
    "TokenBudgetGate",
    "get_token_budget_gate",
]
