# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Gateway Ingest Governance Stage (#14028)

Applied uniformly at every Gateway ingest seam — ``GatewayManager.normalize_message``
(platform adapters: web, slack, discord, whatsapp, teams, telegram, signal, matrix,
imessage) and ``Gateway.receive_message`` (channel adapters: websocket) — so a newly
registered adapter inherits the guard without per-adapter wiring.

Three guards, in order:

1. Bot-self filter — drops an inbound message whose author id equals the
   configured bot identity for that platform (``AUTOBOT_GATEWAY_BOT_ID_<PLATFORM>``).
   No configured id means the filter is a no-op for that platform.
2. Recursion guard — a chain-depth counter carried on the message. Exceeding the
   ceiling (``AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH``, default 5) halts the chain
   with an explicit log line.
3. Dedup — a short-TTL Redis SET NX keyed on (platform, channel, message_id).
   A message already seen within the TTL window is dropped, not re-routed.

Redis-unavailable decision (deliberate, not incidental — see PR #14028 body):
dedup FAILS OPEN. The bot-self filter and recursion guard are both
Redis-independent and keep enforcing even when Redis is down, and those two are
the guards against an *unbounded* loop (the actual "quietly bills tokens
forever" failure mode). Losing dedup during a Redis outage only risks a
single bounded duplicate turn (2x, not Nx) from a webhook redelivery — a much
smaller blast radius than refusing every inbound message on every channel
because one dependency is unhealthy. Every fail-open is logged at ERROR so the
degradation is visible, never silent.
"""

from __future__ import annotations

from dataclasses import dataclass

from autobot_shared.env_utils import blank_to_none
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config, env
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)

# Default recursion ceiling when AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH is unset.
_DEFAULT_MAX_CHAIN_DEPTH = 5


def _resolve_dedup_ttl_seconds() -> int:
    """TTL seconds for gateway:ingest:seen:* Redis keys (#14028)."""
    raw = blank_to_none(config.misc.gateway_ingest_dedup_ttl_seconds)
    if raw is None:
        return TTL_5_MINUTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_GATEWAY_INGEST_DEDUP_TTL_SECONDS=%r is not an integer; falling back to %ds",
            raw,
            TTL_5_MINUTES,
        )
        return TTL_5_MINUTES
    if value <= 0:
        logger.warning(
            "AUTOBOT_GATEWAY_INGEST_DEDUP_TTL_SECONDS=%d must be positive; falling back to %ds",
            value,
            TTL_5_MINUTES,
        )
        return TTL_5_MINUTES
    return value


def _resolve_max_chain_depth() -> int:
    """Recursion ceiling for the agent-to-agent chain-depth guard (#14028)."""
    raw = blank_to_none(config.misc.gateway_ingest_max_chain_depth)
    if raw is None:
        return _DEFAULT_MAX_CHAIN_DEPTH
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH=%r is not an integer; falling back to %d",
            raw,
            _DEFAULT_MAX_CHAIN_DEPTH,
        )
        return _DEFAULT_MAX_CHAIN_DEPTH
    if value <= 0:
        logger.warning(
            "AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH=%d must be positive; falling back to %d",
            value,
            _DEFAULT_MAX_CHAIN_DEPTH,
        )
        return _DEFAULT_MAX_CHAIN_DEPTH
    return value


INGEST_DEDUP_TTL_SECONDS = _resolve_dedup_ttl_seconds()
INGEST_MAX_CHAIN_DEPTH = _resolve_max_chain_depth()


@dataclass(frozen=True)
class IngestVerdict:
    """Result of running the ingest governance stage on one inbound message."""

    allowed: bool
    reason: str = ""


class IngestGovernor:
    """Shared bot-self filter + dedup + recursion guard for Gateway ingest."""

    def _bot_identity(self, platform: str) -> str | None:
        """Configured bot account id for *platform* (``AUTOBOT_GATEWAY_BOT_ID_<PLATFORM>``), or None."""
        return getattr(env, f"gateway_bot_id_{platform}") or None

    def _check_bot_self(self, platform: str, channel_id: str, author_id: str) -> IngestVerdict | None:
        bot_id = self._bot_identity(platform)
        if bot_id and author_id == bot_id:
            logger.warning(
                "Ingest governor dropped self-authored message: platform=%s channel=%s (#14028)",
                platform,
                channel_id,
            )
            return IngestVerdict(False, "bot_self")
        return None

    def _check_recursion(self, platform: str, channel_id: str, chain_depth: int) -> IngestVerdict | None:
        if chain_depth > INGEST_MAX_CHAIN_DEPTH:
            logger.warning(
                "Ingest governor tripped recursion guard: platform=%s channel=%s depth=%d ceiling=%d (#14028)",
                platform,
                channel_id,
                chain_depth,
                INGEST_MAX_CHAIN_DEPTH,
            )
            return IngestVerdict(False, "recursion_ceiling")
        return None

    async def _check_dedup(self, platform: str, channel_id: str, message_id: str) -> IngestVerdict:
        """Redis SET NX dedup. Fails OPEN when Redis is unavailable (see module docstring)."""
        dedup_key = f"gateway:ingest:seen:{platform}:{channel_id}:{message_id}"
        try:
            redis_client = await get_async_redis_client(database="main")
            if redis_client is None:
                raise ConnectionError("get_async_redis_client returned None")
            was_new = await redis_client.set(dedup_key, "1", nx=True, ex=INGEST_DEDUP_TTL_SECONDS)
        except Exception as e:
            logger.error(
                "Ingest governor dedup FAILING OPEN — Redis unavailable for platform=%s channel=%s "
                "message=%s: %s (#14028, duplicate delivery not guaranteed to be caught)",
                platform,
                channel_id,
                message_id,
                e,
            )
            return IngestVerdict(True, "redis_unavailable_fail_open")

        if not was_new:
            logger.warning(
                "Ingest governor dropped duplicate delivery: platform=%s channel=%s message=%s (#14028)",
                platform,
                channel_id,
                message_id,
            )
            return IngestVerdict(False, "duplicate")
        return IngestVerdict(True)

    async def evaluate(
        self,
        *,
        platform: str,
        channel_id: str,
        message_id: str,
        author_id: str,
        chain_depth: int = 0,
    ) -> IngestVerdict:
        """Run the full ingest governance stage on one inbound message."""
        verdict = self._check_bot_self(platform, channel_id, author_id)
        if verdict is not None:
            return verdict

        verdict = self._check_recursion(platform, channel_id, chain_depth)
        if verdict is not None:
            return verdict

        return await self._check_dedup(platform, channel_id, message_id)


# Shared singleton — stateless aside from the module-level TTL/ceiling constants;
# safe to reuse across every GatewayManager/Gateway instance.
ingest_governor = IngestGovernor()
