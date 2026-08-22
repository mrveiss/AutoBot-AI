# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Durable channel-scoped event stream (#14816, #14817, #14818).

``LiveEventManager`` fans events out to connected WebSocket subscribers, but it
held its sequence numbers in a process-local dict.  That id reset on every
restart and diverged between workers, so it could not anchor a replay request —
and an id a consumer trusts but which silently restarts is worse than no id.

This module backs both concerns with Redis:

* :meth:`next_event_id` allocates the sequence with ``INCR``, so it is monotonic
  per channel across restarts and shared across workers.
* :meth:`append` writes the event into a per-channel Redis Stream trimmed to
  ``CHANNEL_STREAM_MAX_ENTRIES``, giving reconnecting clients something to
  replay from.
* :meth:`replay_since` returns the events a client missed, or reports that the
  gap is wider than the retained window so the caller resyncs instead of
  delivering a silent partial.

Redis is not required.  When it is unreachable the stream degrades to an
in-process counter and reports replay as *unavailable* — the client is told to
resync rather than handed an incomplete history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from constants.event_stream_constants import (
    CHANNEL_SEQ_KEY_PREFIX,
    CHANNEL_STREAM_KEY_PREFIX,
    CHANNEL_STREAM_MAX_ENTRIES,
    CHANNEL_STREAM_TTL_SECONDS,
)

logger = get_logger(__name__)


@dataclass
class ReplayResult:
    """Outcome of a replay request.

    ``resync_required`` carries the weight here: it keeps "you missed nothing"
    and "we cannot tell you what you missed" from collapsing into the same empty
    list, which is the failure mode that makes lost events invisible.
    """

    events: List[Dict[str, Any]] = field(default_factory=list)
    resync_required: bool = False
    reason: str | None = None


class ChannelEventStream:
    """Redis-backed sequence allocation and replay for live-event channels."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._redis_unavailable = False
        # Fallback only.  Never the primary source of ids — it resets on
        # restart, which is the defect this module exists to fix (#14817).
        self._memory_counters: Dict[str, int] = {}

    async def _get_redis(self) -> Any:
        """Return the async Redis client, or ``None`` when unreachable."""
        if self._redis is not None:
            return self._redis
        if self._redis_unavailable:
            return None
        try:
            self._redis = await get_async_redis_client(database="main")
            return self._redis
        except Exception as exc:
            # Log once, then stay quiet: a Redis-less dev run should not spam.
            self._redis_unavailable = True
            logger.warning(
                "Channel event stream falling back to in-process ids — Redis unavailable: %s",
                exc,
            )
            return None

    @property
    def durable(self) -> bool:
        """True when ids and replay are Redis-backed rather than in-process."""
        return self._redis is not None and not self._redis_unavailable

    @staticmethod
    def _seq_key(channel: str) -> str:
        return f"{CHANNEL_SEQ_KEY_PREFIX}{channel}"

    @staticmethod
    def _stream_key(channel: str) -> str:
        return f"{CHANNEL_STREAM_KEY_PREFIX}{channel}"

    async def next_event_id(self, channel: str) -> int:
        """Allocate the next sequence number for ``channel``.

        Redis ``INCR`` is atomic, so this is monotonic across restarts and safe
        across worker processes.  Without Redis it degrades to a process-local
        counter, and :attr:`durable` reports False so callers can tell clients
        that replay is not available.
        """
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                return int(await redis_client.incr(self._seq_key(channel)))
            except Exception as exc:
                logger.warning("Sequence allocation failed for %s, using memory: %s", channel, exc)
        self._memory_counters[channel] = self._memory_counters.get(channel, 0) + 1
        return self._memory_counters[channel]

    async def append(self, channel: str, message: Dict[str, Any]) -> None:
        """Persist ``message`` into the channel's replay window.

        A failure here must not stop live delivery — the event still reaches
        connected clients; only the ability to replay it later is lost.
        """
        redis_client = await self._get_redis()
        if redis_client is None:
            return
        try:
            stream_key = self._stream_key(channel)
            await redis_client.xadd(
                stream_key,
                {
                    "event_id": str(message.get("event_id", 0)),
                    "data": json.dumps(message, ensure_ascii=False, default=str),
                },
                maxlen=CHANNEL_STREAM_MAX_ENTRIES,
                approximate=True,
            )
            await redis_client.expire(stream_key, CHANNEL_STREAM_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Failed to persist event for replay on %s: %s", channel, exc)

    async def replay_since(self, channel: str, last_event_id: int) -> ReplayResult:
        """Return the events on ``channel`` newer than ``last_event_id``.

        Sets ``resync_required`` when a complete history cannot be produced —
        Redis unavailable, or the client's marker already trimmed out of the
        retained window.  Never returns a partial history as if it were whole.
        """
        redis_client = await self._get_redis()
        if redis_client is None:
            return ReplayResult(resync_required=True, reason="replay_unavailable")

        try:
            entries = await redis_client.xrange(self._stream_key(channel))
        except Exception as exc:
            logger.warning("Replay read failed on %s: %s", channel, exc)
            return ReplayResult(resync_required=True, reason="replay_unavailable")

        decoded: List[Dict[str, Any]] = []
        lowest_retained: int | None = None
        for _entry_id, fields in entries or []:
            raw = self._field(fields, "data")
            if raw is None:
                continue
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                # An unparseable entry means the window is not trustworthy.
                # Treat that as a gap, never as "nothing to replay".
                return ReplayResult(resync_required=True, reason="replay_corrupt")
            event_id = int(message.get("event_id", 0))
            if lowest_retained is None or event_id < lowest_retained:
                lowest_retained = event_id
            if event_id > last_event_id:
                decoded.append(message)

        # The client's marker predates everything we still hold, so events
        # between its marker and our oldest entry are gone.  A first-ever
        # subscribe (last_event_id == 0) is not a gap.
        if lowest_retained is not None and last_event_id > 0 and lowest_retained > last_event_id + 1:
            return ReplayResult(resync_required=True, reason="gap_exceeds_retention")

        return ReplayResult(events=decoded)

    @staticmethod
    def _field(fields: Any, name: str) -> str | None:
        """Read one field from a stream entry, tolerating bytes or str keys."""
        if not isinstance(fields, dict):
            return None
        if name in fields:
            value = fields[name]
        elif name.encode() in fields:
            value = fields[name.encode()]
        else:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else value


get_channel_event_stream = lazy_singleton(ChannelEventStream)
