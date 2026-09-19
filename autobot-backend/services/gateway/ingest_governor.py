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
   configured bot identity for that platform. The identity is resolved from a
   registered dynamic resolver first (``register_bot_id_resolver`` — e.g.
   Telegram's numeric id from ``getMe()``), falling back to
   ``AUTOBOT_GATEWAY_BOT_ID_<PLATFORM>``. Neither resolving means the filter
   is a no-op for that platform, and that fact is logged at WARNING once per
   platform per process — never silently.
2. Recursion guard — a per-``(platform, channel)`` counter kept in Redis,
   incremented by ``record_agent_send()`` every time AutoBot posts to that
   channel, and read (never trusted from the inbound payload) at ingest.
   **This is deliberate, not incidental**: no platform round-trips an
   AutoBot-internal field through its inbound webhook — a fresh Discord
   event, Slack event, or Telegram update carries none of our metadata back
   to us, so a counter carried on the *message* can never survive the hop
   through a real platform. Exceeding the ceiling
   (``AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH``, default 5) halts the chain
   with an explicit log line. The counter itself decays via a sliding TTL
   (``AUTOBOT_GATEWAY_INGEST_CHAIN_WINDOW_SECONDS``, default 120s) — short
   enough that a genuine multi-turn human conversation (turns are seconds to
   minutes apart) rarely trips it, long enough that a machine-speed
   agent-to-agent reply loop (turns are sub-second) blows through the
   ceiling well inside one window.
3. Dedup — a short-TTL Redis SET NX keyed on (platform, channel, message_id).
   A message already seen within the TTL window is dropped, not re-routed.

Redis-unavailable decision (deliberate, not incidental — see PR #14028 body):
dedup and the recursion counter both FAIL OPEN; the bot-self filter alone is
Redis-independent and keeps enforcing regardless. Every fail-open is logged
at ERROR *and* recorded via ``autobot_shared.monitoring.prometheus_metrics``
so the degradation is visible outside logs too, never silent.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Dict

from autobot_shared.env_utils import blank_to_none
from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config, env
from constants.ttl_constants import TTL_5_MINUTES
from services.gateway.types import GovernanceVerdict

logger = get_logger(__name__)

# Default recursion ceiling when AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH is unset.
_DEFAULT_MAX_CHAIN_DEPTH = 5

# Default sliding window (seconds) for the recursion counter when
# AUTOBOT_GATEWAY_INGEST_CHAIN_WINDOW_SECONDS is unset.
_DEFAULT_CHAIN_WINDOW_SECONDS = 120


def _resolve_dedup_ttl_seconds() -> int:
    """TTL seconds for gateway:ingest:seen:* Redis keys (#14028)."""
    return _resolve_positive_int(
        config.misc.gateway_ingest_dedup_ttl_seconds,
        "AUTOBOT_GATEWAY_INGEST_DEDUP_TTL_SECONDS",
        TTL_5_MINUTES,
    )


def _resolve_max_chain_depth() -> int:
    """Recursion ceiling for the agent-to-agent chain-depth guard (#14028)."""
    return _resolve_positive_int(
        config.misc.gateway_ingest_max_chain_depth,
        "AUTOBOT_GATEWAY_INGEST_MAX_CHAIN_DEPTH",
        _DEFAULT_MAX_CHAIN_DEPTH,
    )


def _resolve_chain_window_seconds() -> int:
    """Sliding-window TTL for the recursion counter (#14028)."""
    return _resolve_positive_int(
        config.misc.gateway_ingest_chain_window_seconds,
        "AUTOBOT_GATEWAY_INGEST_CHAIN_WINDOW_SECONDS",
        _DEFAULT_CHAIN_WINDOW_SECONDS,
    )


def _resolve_positive_int(raw: object, env_name: str, default: int) -> int:
    """Shared int(raw)-or-default resolver for the three env-backed constants below.

    ``ssot_config`` declares these as ``str = Field(default="")``; an unset var
    arrives as ``""``, not ``None`` — ``blank_to_none`` collapses that (#12782).
    """
    resolved = blank_to_none(raw)
    if resolved is None:
        return default
    try:
        value = int(resolved)
    except ValueError:
        logger.warning("%s=%r is not an integer; falling back to %d", env_name, resolved, default)
        return default
    if value <= 0:
        logger.warning("%s=%d must be positive; falling back to %d", env_name, value, default)
        return default
    return value


INGEST_DEDUP_TTL_SECONDS = _resolve_dedup_ttl_seconds()
INGEST_MAX_CHAIN_DEPTH = _resolve_max_chain_depth()
INGEST_CHAIN_WINDOW_SECONDS = _resolve_chain_window_seconds()

BotIdResolver = Callable[[], Awaitable[str | None]]


# #14905: IngestVerdict was a fork of the shape EgressVerdict later grew
# (allowed, reason, rule, safe_reason) — this package's shared governance
# type lives in services.gateway.types now; kept as a name so callers and
# tests importing IngestVerdict from this module do not break.
IngestVerdict = GovernanceVerdict


class IngestGovernor:
    """Shared bot-self filter + dedup + recursion guard for Gateway ingest."""

    def __init__(self) -> None:
        self._bot_id_resolvers: Dict[str, BotIdResolver] = {}
        self._warned_no_bot_id: set[str] = set()

    def register_bot_id_resolver(self, platform: str, resolver: BotIdResolver) -> None:
        """Register a dynamic bot-identity resolver for *platform* (#14028).

        Use this when the bot's own account id is only known at runtime (e.g.
        Telegram's numeric id from ``getMe()``, cached in Redis by
        ``api/telegram_bot.py``) rather than fixed in an env var. Checked
        before ``AUTOBOT_GATEWAY_BOT_ID_<PLATFORM>``; falls back to it when no
        resolver is registered or the resolver returns falsy.
        """
        self._bot_id_resolvers[platform] = resolver

    async def _bot_identity(self, platform: str) -> str | None:
        resolver = self._bot_id_resolvers.get(platform)
        if resolver is not None:
            try:
                resolved = await resolver()
            except Exception as e:
                logger.error("Ingest governor bot-id resolver failed for platform=%s: %s (#14028)", platform, e)
                resolved = None
            if resolved:
                return resolved
        return getattr(env, f"gateway_bot_id_{platform}") or None

    async def _check_bot_self(self, platform: str, channel_id: str, author_id: str) -> IngestVerdict | None:
        bot_id = await self._bot_identity(platform)
        if not bot_id:
            if platform not in self._warned_no_bot_id:
                self._warned_no_bot_id.add(platform)
                logger.warning(
                    "Ingest governor: no bot identity resolved for platform=%s — the "
                    "self-reply filter is a no-op until a resolver is registered or "
                    "AUTOBOT_GATEWAY_BOT_ID_%s is set (#14028)",
                    platform,
                    platform.upper(),
                )
            return None
        if author_id == bot_id:
            logger.warning(
                "Ingest governor dropped self-authored message: platform=%s channel=%s (#14028)",
                platform,
                channel_id,
            )
            return IngestVerdict(False, "bot_self", rule="bot_self")
        return None

    async def _check_recursion(self, platform: str, channel_id: str) -> IngestVerdict | None:
        """Read the per-(platform, channel) agent-send counter from Redis.

        Never trusts a payload field — see the module docstring for why.
        Fails OPEN (cannot verify, so does not block) when Redis is down.
        """
        key = f"gateway:ingest:chain_depth:{platform}:{channel_id}"
        try:
            redis_client = await get_async_redis_client(database="main")
            if redis_client is None:
                raise ConnectionError("get_async_redis_client returned None")
            raw_depth = await redis_client.get(key)
        except Exception as e:
            logger.error(
                "Ingest governor recursion check FAILING OPEN — Redis unavailable for "
                "platform=%s channel=%s: %s (#14028)",
                platform,
                channel_id,
                e,
            )
            get_metrics_manager().record_error(
                category="gateway_ingest", component="ingest_governor", error_code="recursion_redis_unavailable"
            )
            return None

        depth = int(raw_depth or 0)
        if depth > INGEST_MAX_CHAIN_DEPTH:
            logger.warning(
                "Ingest governor tripped recursion guard: platform=%s channel=%s depth=%d ceiling=%d (#14028)",
                platform,
                channel_id,
                depth,
                INGEST_MAX_CHAIN_DEPTH,
            )
            return IngestVerdict(False, "recursion_ceiling", rule="recursion_ceiling")
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
            get_metrics_manager().record_error(
                category="gateway_ingest", component="ingest_governor", error_code="dedup_redis_unavailable"
            )
            return IngestVerdict(True, "redis_unavailable_fail_open", rule="dedup_fail_open")

        if not was_new:
            logger.warning(
                "Ingest governor dropped duplicate delivery: platform=%s channel=%s message=%s (#14028)",
                platform,
                channel_id,
                message_id,
            )
            return IngestVerdict(False, "duplicate", rule="duplicate")
        return IngestVerdict(True, rule="dedup")

    async def record_agent_send(self, *, platform: str, channel_id: str) -> None:
        """Increment the per-(platform, channel) recursion counter.

        Call this from every place AutoBot posts an agent-authored message to
        a channel (``api/telegram_bot.py::send_telegram_response``,
        ``api/whatsapp.py::send_whatsapp_response``,
        ``GatewayManager.route_message``, ``Gateway.send_message``) — the
        counter is server-side state precisely because no platform
        round-trips our metadata back through its inbound webhook (#14028).
        Fails OPEN and logs at ERROR: a missed increment only weakens the
        recursion guard for this one turn, it does not block sending.
        """
        key = f"gateway:ingest:chain_depth:{platform}:{channel_id}"
        try:
            redis_client = await get_async_redis_client(database="main")
            if redis_client is None:
                raise ConnectionError("get_async_redis_client returned None")
            await redis_client.incr(key)
            await redis_client.expire(key, INGEST_CHAIN_WINDOW_SECONDS)
        except Exception as e:
            logger.error(
                "Ingest governor could not record agent send (recursion tracking degraded) "
                "for platform=%s channel=%s: %s (#14028)",
                platform,
                channel_id,
                e,
            )
            get_metrics_manager().record_error(
                category="gateway_ingest", component="ingest_governor", error_code="record_send_failed"
            )

    async def evaluate(
        self,
        *,
        platform: str,
        channel_id: str,
        message_id: str,
        author_id: str,
    ) -> IngestVerdict:
        """Run the full ingest governance stage on one inbound message."""
        verdict = await self._check_bot_self(platform, channel_id, author_id)
        if verdict is not None:
            return verdict

        verdict = await self._check_recursion(platform, channel_id)
        if verdict is not None:
            return verdict

        return await self._check_dedup(platform, channel_id, message_id)


# Shared singleton — safe to reuse across every GatewayManager/Gateway instance;
# holds only the bot-id-resolver registry and the warn-once set, both keyed by
# platform, never per-message state.
ingest_governor = IngestGovernor()
