# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Voice Realtime Telemetry Service

Per-session cost + duration accounting for OpenAI Realtime WebRTC sessions.

Issue #7421 — Implements:
Issue #9035 — Respects telemetry opt-out configuration
- Session lifecycle tracking (start/end/duration)
- Audio seconds accounting (input + output)
- Token counts from response.done events
- Tool-call count + per-tool latency
- Cost estimation (per-second audio + per-token)
- Soft-cap enforcement with auto-disconnect signal
- Prometheus metrics via VoiceRealtimeMetricsRecorder
- Redis persistence (analytics database)
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

from redis.exceptions import WatchError

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config
from autobot_shared.store_authority import system_of_record
from autobot_shared.time_utils import now_utc
from services.telemetry_settings import get_telemetry_settings

logger = get_logger(__name__)

# With telemetry on and Redis reachable, Redis holds the session; the local map is only the fallback (#21678).
SYSTEM_OF_RECORD = system_of_record("voice_realtime_session")

# ── Realtime audio pricing (USD per second, gpt-4o-realtime-preview) ────────
# Source: OpenAI pricing page – audio input $0.10/min, output $0.20/min
# #16230: not sourced from llm_shared.pricing.sync_cache -- LiteLLM/OpenRouter
# price LLM API calls per token, not Realtime WebRTC audio seconds, so this
# axis has no live-catalogue equivalent to read. Update by hand when OpenAI's
# published Realtime pricing changes.
_AUDIO_COST_PER_SEC: dict[str, float] = {
    "input": 0.10 / 60,  # ~$0.001667/s
    "output": 0.20 / 60,  # ~$0.003333/s
}

# Token pricing for gpt-4o-realtime-preview (USD per 1M tokens)
# #16230: kept alongside _AUDIO_COST_PER_SEC rather than split onto the live
# catalogue -- one session's estimated_cost_usd below sums both axes for one
# fixed model, and sourcing only this half live while audio stays hardcoded
# would mix a live number with a frozen one in the same total for no benefit.
_TOKEN_COST_PER_1M: dict[str, float] = {
    "input": 5.00,
    "output": 20.00,
    "cached_input": 2.50,
}

# Redis key prefix + TTL
_KEY_PREFIX = "voice_realtime_session"
_SESSION_TTL = config.misc.voice_realtime_session_ttl_days * 86400
#: An in-memory session that never ended (dropped connection) is evicted after this long; the cap checks
#: end a live one well before (#21678). Never effective below the duration cap plus the margin below.
_ABANDONED_SESSION_MAX_AGE_S = env_int_clamped("AUTOBOT_VOICE_REALTIME_ABANDONED_SESSION_SECONDS", 7200, 60, 604800)
#: Slack added past the duration cap so a session the cap is about to end is never evicted first.
_ABANDONED_SESSION_CAP_MARGIN_S = 300
#: WATCH/MULTI attempts for one cross-worker update before giving up (one session is rarely written by >1 worker).
_UPDATE_MAX_ATTEMPTS = 8


class DisconnectReason(str, Enum):
    NORMAL = "normal"
    DURATION_CAP = "duration_cap"
    COST_CAP = "cost_cap"
    ERROR = "error"


@dataclass
class RealtimeSessionRecord:
    """Persisted record for a single Realtime WebRTC session."""

    session_id: str
    user_id: str | None
    model: str
    started_at: str
    ended_at: str | None = None
    duration_s: float = 0.0
    audio_in_s: float = 0.0
    audio_out_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    tool_calls: int = 0
    estimated_cost_usd: float = 0.0
    disconnect_reason: str = DisconnectReason.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RealtimeSessionRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CapBreachError(Exception):
    """Raised when a soft-cap is exceeded; callers should close the session."""

    def __init__(self, reason: DisconnectReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class VoiceRealtimeTelemetry(AsyncRedisClientMixin):
    """Tracks cost + duration telemetry for Realtime WebRTC sessions.

    Typical lifecycle
    -----------------
    telemetry = VoiceRealtimeTelemetry()
    await telemetry.session_start(session_id, user_id, model)
    # ... session events ...
    await telemetry.record_response_done(session_id, input_tokens=..., output_tokens=...)
    await telemetry.record_tool_call(session_id, tool="search", latency_s=0.3)
    await telemetry.check_caps(session_id)   # raises CapBreachError if over limit
    await telemetry.session_end(session_id)

    Raises CapBreachError from check_caps(); the caller should close the WebRTC
    connection and surface the reason to the user.

    Issue #9035: When config.telemetry.enabled=False, all persistence methods
    return early without writing to Redis. Cap checks still work (in-memory only).
    """

    _redis_database = "analytics"

    def __init__(self) -> None:
        self._model = config.misc.voice_realtime_model
        self._max_seconds = config.misc.voice_realtime_max_seconds
        self._max_cost_usd = config.misc.voice_realtime_max_cost_usd

        # Lazy import to avoid circular dependency with prometheus_metrics module
        from autobot_shared.monitoring.prometheus_metrics import (
            PrometheusMetricsManager,
        )

        self._prom = PrometheusMetricsManager()
        # Active sessions only (released when finished); cap checks read here
        self._in_memory_sessions: dict[str, RealtimeSessionRecord] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def session_start(
        self,
        session_id: str,
        user_id: str | None = None,
        model: str | None = None,
    ) -> RealtimeSessionRecord:
        """Create and persist an in-progress session record."""
        model = model or self._model
        record = RealtimeSessionRecord(
            session_id=session_id,
            user_id=user_id,
            model=model,
            started_at=now_utc().isoformat(),
        )
        await self._save_record(record)

        self._prom._voice_realtime.sessions_total.labels(model=model).inc()
        self._prom._voice_realtime.sessions_active.labels(model=model).inc()
        logger.info("voice_realtime session_start session_id=%s model=%s", session_id, model)
        return record

    async def session_end(
        self,
        session_id: str,
        reason: DisconnectReason = DisconnectReason.NORMAL,
    ) -> RealtimeSessionRecord | None:
        """Finalise the session record and flush Prometheus counters."""
        record = await self._update_record(session_id, lambda r: _apply_end(r, reason))
        if record is None:
            logger.warning("voice_realtime session_end: unknown session_id=%s", session_id)
            return None
        self._emit_session_end_metrics(record, reason)
        logger.info(
            "voice_realtime session_end session_id=%s duration_s=%.1f cost_usd=%.4f reason=%s",
            session_id,
            record.duration_s,
            record.estimated_cost_usd,
            record.disconnect_reason,
        )
        return record

    def _emit_session_end_metrics(self, record: RealtimeSessionRecord, reason: DisconnectReason) -> None:
        m = self._prom._voice_realtime
        m.sessions_active.labels(model=record.model).dec()
        m.session_seconds_total.labels(model=record.model).inc(record.duration_s)
        m.session_duration.labels(model=record.model, disconnect_reason=record.disconnect_reason).observe(
            record.duration_s
        )
        m.estimated_cost_usd.labels(model=record.model).inc(record.estimated_cost_usd)
        if reason in (DisconnectReason.DURATION_CAP, DisconnectReason.COST_CAP):
            m.cap_breaches_total.labels(reason=reason.value).inc()

    async def record_audio(
        self,
        session_id: str,
        direction: str,
        seconds: float,
    ) -> None:
        """Accumulate audio seconds (direction: 'input' | 'output')."""

        def apply(record: RealtimeSessionRecord) -> None:
            if direction == "input":
                record.audio_in_s += seconds
            else:
                record.audio_out_s += seconds

        if await self._update_record(session_id, apply) is None:
            return
        self._prom._voice_realtime.audio_seconds_total.labels(direction=direction).inc(seconds)

    async def record_response_done(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        audio_in_s: float = 0.0,
        audio_out_s: float = 0.0,
    ) -> None:
        """Handle a response.done event — update token counts and audio."""

        def apply(record: RealtimeSessionRecord) -> None:
            record.input_tokens += input_tokens
            record.output_tokens += output_tokens
            record.cached_input_tokens += cached_input_tokens
            record.audio_in_s += audio_in_s
            record.audio_out_s += audio_out_s

        if await self._update_record(session_id, apply) is None:
            return

        m = self._prom._voice_realtime
        if input_tokens:
            m.tokens_total.labels(type="input").inc(input_tokens)
        if output_tokens:
            m.tokens_total.labels(type="output").inc(output_tokens)
        if cached_input_tokens:
            m.tokens_total.labels(type="cached_input").inc(cached_input_tokens)
        if audio_in_s:
            m.audio_seconds_total.labels(direction="input").inc(audio_in_s)
        if audio_out_s:
            m.audio_seconds_total.labels(direction="output").inc(audio_out_s)

    async def record_tool_call(
        self,
        session_id: str,
        tool: str,
        latency_s: float = 0.0,
        outcome: str = "success",
    ) -> None:
        """Record a single tool-call event."""

        def apply(record: RealtimeSessionRecord) -> None:
            record.tool_calls += 1

        await self._update_record(session_id, apply)

        m = self._prom._voice_realtime
        m.tool_calls_total.labels(tool=tool, outcome=outcome).inc()
        if latency_s > 0:
            m.tool_call_duration.labels(tool=tool).observe(latency_s)

    async def check_caps(self, session_id: str) -> None:
        """Check soft-caps and raise CapBreachError if exceeded.

        Callers (e.g. the SDP proxy or heartbeat task) should catch
        CapBreachError, close the WebRTC session, and surface the reason
        to the user.
        """
        record = await self._load_record(session_id)
        if record is None:
            return

        elapsed = _elapsed_seconds(record)

        if elapsed >= self._max_seconds:
            msg = f"session ended: {self._max_seconds // 60} minute limit reached"
            raise CapBreachError(DisconnectReason.DURATION_CAP, msg)

        cost = _estimate_cost(record)
        if cost >= self._max_cost_usd:
            msg = f"session ended: ${self._max_cost_usd:.2f} cost limit reached"
            raise CapBreachError(DisconnectReason.COST_CAP, msg)

    async def get_session(self, session_id: str) -> RealtimeSessionRecord | None:
        """Return the current (or completed) record for a session."""
        return await self._load_record(session_id)

    async def list_recent_sessions(
        self,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[RealtimeSessionRecord]:
        """Return recent session records, optionally filtered by user."""
        redis = await self._get_redis()
        if redis is None:
            return []

        pattern = f"{_KEY_PREFIX}:*"
        keys = []
        async for key in redis.scan_iter(match=pattern, count=100):
            keys.append(key)
            if len(keys) >= limit * 5:  # fetch extra for filtering
                break

        records = []
        for key in keys:
            raw = await redis.get(key)
            if raw is None:
                continue
            try:
                data = json.loads(raw)
                rec = RealtimeSessionRecord.from_dict(data)
                if user_id is not None and rec.user_id != user_id:
                    continue
                records.append(rec)
            except Exception:
                logger.debug("voice_realtime: failed to parse record key=%s", key)

        records.sort(key=lambda r: r.started_at, reverse=True)
        return records[:limit]

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _authoritative_redis(self) -> Any | None:
        """Redis when telemetry is on and reachable (it is then the system of record), else None."""
        if not get_telemetry_settings()["enabled"]:
            return None
        return await self._get_redis()

    def _hold_locally(self, record: RealtimeSessionRecord) -> None:
        """Keep the active record as the fallback copy; release a finished one on every path."""
        self._evict_abandoned_sessions()
        if record.ended_at:
            self._in_memory_sessions.pop(record.session_id, None)
        else:
            self._in_memory_sessions[record.session_id] = record

    async def _save_record(self, record: RealtimeSessionRecord) -> None:
        # The local copy is kept whatever the consent: cap checks and session_end need it when Redis is off or
        # down, even after an opt-out/opt-in flips mid-session (#9035). It is never read ahead of Redis.
        self._hold_locally(record)
        redis = await self._authoritative_redis()
        if redis is None:
            return
        await redis.set(_session_key(record.session_id), json.dumps(record.to_dict()), ex=_SESSION_TTL)

    async def _update_record(
        self, session_id: str, mutate: Callable[[RealtimeSessionRecord], None]
    ) -> RealtimeSessionRecord | None:
        """Apply *mutate* to the session atomically across workers; None when the session is unknown."""
        redis = await self._authoritative_redis()
        if redis is not None:
            record = await self._update_in_redis(redis, session_id, mutate)
            if record is not None:
                if record.ended_at or session_id in self._in_memory_sessions:
                    self._hold_locally(record)
                return record
        local = self._in_memory_sessions.get(session_id)  # started while Redis was off or down
        if local is None:
            return None
        mutate(local)
        await self._save_record(local)
        return local

    @staticmethod
    async def _update_in_redis(
        redis: Any, session_id: str, mutate: Callable[[RealtimeSessionRecord], None]
    ) -> RealtimeSessionRecord | None:
        """Read-modify-write under WATCH/MULTI so another worker's concurrent update is never overwritten."""
        key = _session_key(session_id)
        for _ in range(_UPDATE_MAX_ATTEMPTS):
            async with redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    record = _parse_record(await pipe.get(key), session_id)
                    if record is None:
                        await pipe.unwatch()
                        return None
                    mutate(record)
                    pipe.multi()
                    pipe.set(key, json.dumps(record.to_dict()), ex=_SESSION_TTL)
                    await pipe.execute()
                    return record
                except WatchError:
                    continue  # another worker wrote first: re-read its state and apply ours on top
        raise RuntimeError(f"voice_realtime: session {session_id} contended for {_UPDATE_MAX_ATTEMPTS} attempts")

    def _evict_abandoned_sessions(self) -> None:
        """Drop in-memory sessions that never ended and are older than the max age (a dropped connection)."""
        now = now_utc()
        max_age = abandoned_session_max_age_s(self._max_seconds)
        stale = [
            sid
            for sid, rec in self._in_memory_sessions.items()
            if (now - _parse_iso(rec.started_at)).total_seconds() > max_age
        ]
        for sid in stale:
            del self._in_memory_sessions[sid]
            logger.warning("voice_realtime: evicted abandoned session session_id=%s", sid)

    async def _load_record(self, session_id: str) -> RealtimeSessionRecord | None:
        # Redis first when it is the system of record: another worker's updates land there, so a local copy
        # may be stale. The local map answers only when Redis is off, down, or never saw the session.
        record = await self._read_redis_record(session_id)
        return record if record is not None else self._in_memory_sessions.get(session_id)

    async def _read_redis_record(self, session_id: str) -> RealtimeSessionRecord | None:
        """The Redis copy, or None when absent or unreadable (logged, so the caller falls back to the local one)."""
        try:
            redis = await self._authoritative_redis()
            if redis is None:
                return None
            return _parse_record(await redis.get(_session_key(session_id)), session_id)
        except Exception as exc:
            logger.warning(
                "voice_realtime: redis read failed session_id=%s, using the local record: %s", session_id, exc
            )
            return None


# ── Module-level helpers ──────────────────────────────────────────────────────


def abandoned_session_max_age_s(max_seconds: int) -> int:
    """Effective age past which an unended in-memory session is evicted (never below the duration cap + margin)."""
    return max(_ABANDONED_SESSION_MAX_AGE_S, max_seconds + _ABANDONED_SESSION_CAP_MARGIN_S)


def _session_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}"


def _parse_record(raw: str | bytes | None, session_id: str) -> RealtimeSessionRecord | None:
    if raw is None:
        return None
    try:
        return RealtimeSessionRecord.from_dict(json.loads(raw))
    except Exception as exc:
        logger.warning("voice_realtime: failed to parse record session_id=%s: %s", session_id, exc)
        return None


def _apply_end(record: RealtimeSessionRecord, reason: DisconnectReason) -> None:
    """Stamp the final duration, reason and cost onto *record* (computed from the freshest usage)."""
    end_time = now_utc()
    record.ended_at = end_time.isoformat()
    record.duration_s = max(0.0, (end_time - _parse_iso(record.started_at)).total_seconds())
    record.disconnect_reason = reason.value if isinstance(reason, DisconnectReason) else reason
    record.estimated_cost_usd = _estimate_cost(record)


def _estimate_cost(record: RealtimeSessionRecord) -> float:
    """Compute estimated USD cost from the session record."""
    audio_cost = record.audio_in_s * _AUDIO_COST_PER_SEC["input"] + record.audio_out_s * _AUDIO_COST_PER_SEC["output"]
    token_cost = (
        record.input_tokens * _TOKEN_COST_PER_1M["input"] / 1_000_000
        + record.output_tokens * _TOKEN_COST_PER_1M["output"] / 1_000_000
        + record.cached_input_tokens * _TOKEN_COST_PER_1M["cached_input"] / 1_000_000
    )
    return audio_cost + token_cost


def _elapsed_seconds(record: RealtimeSessionRecord) -> float:
    if record.ended_at:
        return record.duration_s
    started = _parse_iso(record.started_at)
    return max(0.0, (now_utc() - started).total_seconds())


def _parse_iso(iso_str: str):
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


get_voice_realtime_telemetry = lazy_singleton(VoiceRealtimeTelemetry)
