# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Realtime Telemetry Service

Per-session cost + duration accounting for OpenAI Realtime WebRTC sessions.

Issue #7421 — Implements:
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
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

# ── Realtime audio pricing (USD per second, gpt-4o-realtime-preview) ────────
# Source: OpenAI pricing page – audio input $0.10/min, output $0.20/min
# Update alongside PRICING_VERSION in llm_cost_tracker.py when prices change.
_AUDIO_COST_PER_SEC: dict[str, float] = {
    "input": 0.10 / 60,  # ~$0.001667/s
    "output": 0.20 / 60,  # ~$0.003333/s
}

# Token pricing for gpt-4o-realtime-preview (USD per 1M tokens)
_TOKEN_COST_PER_1M: dict[str, float] = {
    "input": 5.00,
    "output": 20.00,
    "cached_input": 2.50,
}

# Redis key prefix + TTL
_KEY_PREFIX = "voice_realtime_session"
_SESSION_TTL = config.misc.voice_realtime_session_ttl_days * 86400


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
        record = await self._load_record(session_id)
        if record is None:
            logger.warning("voice_realtime session_end: unknown session_id=%s", session_id)
            return None

        end_time = now_utc()
        started = _parse_iso(record.started_at)
        duration_s = max(0.0, (end_time - started).total_seconds())

        record.ended_at = end_time.isoformat()
        record.duration_s = duration_s
        record.disconnect_reason = reason.value if isinstance(reason, DisconnectReason) else reason

        # Accumulate audio cost if not already computed incrementally
        record.estimated_cost_usd = _estimate_cost(record)

        await self._save_record(record)

        m = self._prom._voice_realtime
        m.sessions_active.labels(model=record.model).dec()
        m.session_seconds_total.labels(model=record.model).inc(duration_s)
        m.session_duration.labels(model=record.model, disconnect_reason=record.disconnect_reason).observe(duration_s)
        m.estimated_cost_usd.labels(model=record.model).inc(record.estimated_cost_usd)

        if reason in (DisconnectReason.DURATION_CAP, DisconnectReason.COST_CAP):
            m.cap_breaches_total.labels(reason=reason.value).inc()

        logger.info(
            "voice_realtime session_end session_id=%s duration_s=%.1f cost_usd=%.4f reason=%s",
            session_id,
            duration_s,
            record.estimated_cost_usd,
            reason.value,
        )
        return record

    async def record_audio(
        self,
        session_id: str,
        direction: str,
        seconds: float,
    ) -> None:
        """Accumulate audio seconds (direction: 'input' | 'output')."""
        record = await self._load_record(session_id)
        if record is None:
            return

        if direction == "input":
            record.audio_in_s += seconds
        else:
            record.audio_out_s += seconds

        await self._save_record(record)
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
        record = await self._load_record(session_id)
        if record is None:
            return

        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.cached_input_tokens += cached_input_tokens
        record.audio_in_s += audio_in_s
        record.audio_out_s += audio_out_s

        await self._save_record(record)

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
        record = await self._load_record(session_id)
        if record is not None:
            record.tool_calls += 1
            await self._save_record(record)

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

    async def _save_record(self, record: RealtimeSessionRecord) -> None:
        redis = await self._get_redis()
        if redis is None:
            return
        key = f"{_KEY_PREFIX}:{record.session_id}"
        await redis.set(key, json.dumps(record.to_dict()), ex=_SESSION_TTL)

    async def _load_record(self, session_id: str) -> RealtimeSessionRecord | None:
        redis = await self._get_redis()
        if redis is None:
            return None
        key = f"{_KEY_PREFIX}:{session_id}"
        raw = await redis.get(key)
        if raw is None:
            return None
        try:
            return RealtimeSessionRecord.from_dict(json.loads(raw))
        except Exception as exc:
            logger.warning(
                "voice_realtime: failed to parse record session_id=%s: %s",
                session_id,
                exc,
            )
            return None


# ── Module-level helpers ──────────────────────────────────────────────────────


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
