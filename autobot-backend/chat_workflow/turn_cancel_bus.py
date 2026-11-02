# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deliver a turn cancel to whichever worker holds the turn (#18448).

``turn_control``'s registry is per process, and the backend can run several
workers, so a cancel landing on the wrong one used to answer "no turn" while the
model kept generating. Here a worker running a turn subscribes to a channel keyed
by the session id; a cancel is published on it and each subscriber runs the same
local teardown, then acks with how many turns it stopped.

The answer is honest: ``PUBLISH`` returns how many workers were listening, so the
requester waits for exactly that many acks, and reports ``confirmed=False`` when
the bus is unreachable or an ack does not arrive within
``AUTOBOT_CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS``. The local worker is cancelled
directly first, so a single-worker deployment never depends on Redis for a stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

CHANNEL_PREFIX = "autobot:chat:turn-cancel:"
ACK_PREFIX = "autobot:chat:turn-cancel-ack:"

#: How long the requester waits for the workers that were listening to ack (#18448).
CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS: float = env_float_clamped(
    "AUTOBOT_CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS", default=5.0, positive_finite=True
)

#: This process's identity on the bus; a message it published itself is not re-run.
WORKER_ID: str = uuid.uuid4().hex

LocalCancel = Callable[[str, str], Awaitable[int]]


@dataclass(frozen=True)
class CancelOutcome:
    """How many turns were stopped across workers, and whether every worker answered."""

    cancelled: int
    confirmed: bool


def _decode(raw: Any) -> dict:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def _close(pubsub: Any, channel: str) -> None:
    for step in (pubsub.unsubscribe(channel), pubsub.aclose()):
        try:
            await step
        except Exception as exc:  # noqa: BLE001 - teardown must not mask the real outcome
            logger.debug("turn-cancel bus teardown step failed: %s", exc)


async def _serve(pubsub: Any, redis: Any, session_id: str, on_cancel: LocalCancel) -> None:
    """Handle cancels published for *session_id* until cancelled."""
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            request = _decode(message["data"])
            own = request["origin"] == WORKER_ID
            cancelled = 0 if own else await on_cancel(session_id, request["reason"])
            ack = json.dumps({"worker": WORKER_ID, "cancelled": cancelled})
            await redis.publish(ACK_PREFIX + request["request_id"], ack)
        except Exception as exc:  # noqa: BLE001 - one bad message must not end the listener
            logger.warning("turn-cancel request for session %s failed: %s", session_id, exc)


@contextlib.asynccontextmanager
async def listening(session_id: str, on_cancel: LocalCancel) -> AsyncIterator[None]:
    """While a turn runs here, answer cancels published for its session.

    Failing to subscribe never fails the turn: it only means a cancel arriving at
    another worker cannot reach this one, which the requester reports as unconfirmed.
    """
    pubsub, task = None, None
    channel = CHANNEL_PREFIX + session_id
    try:
        redis = await get_async_redis_client(database="main")
        if redis is not None:
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            task = asyncio.create_task(_serve(pubsub, redis, session_id, on_cancel))
    except Exception as exc:  # noqa: BLE001
        logger.warning("turn-cancel bus unavailable for session %s: %s", session_id, exc)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if pubsub is not None:
            await _close(pubsub, channel)


async def _collect_acks(pubsub: Any, expected: int) -> tuple[int, bool]:
    total, seen = 0, 0
    try:
        async with asyncio.timeout(CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS):
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                total += int(_decode(message["data"])["cancelled"])
                seen += 1
                if seen >= expected:
                    return total, True
    except TimeoutError:
        logger.warning("turn-cancel: %d of %d workers acked in time", seen, expected)
    return total, False


async def _publish_and_collect(session_id: str, reason: str, origin: str) -> tuple[int, bool]:
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return 0, False
    request_id = uuid.uuid4().hex
    ack_channel = ACK_PREFIX + request_id
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(ack_channel)  # before publishing, or a fast ack is missed
        request = json.dumps({"request_id": request_id, "origin": origin, "reason": reason})
        listeners = int(await redis.publish(CHANNEL_PREFIX + session_id, request))
        if listeners == 0:
            return 0, True
        return await _collect_acks(pubsub, listeners)
    finally:
        await _close(pubsub, ack_channel)


async def request_cancel(
    session_id: str, reason: str, local_cancel: LocalCancel, worker_id: str | None = None
) -> CancelOutcome:
    """Cancel *session_id*'s turn on this worker, then on every other worker holding one."""
    local = await local_cancel(session_id, reason)
    try:
        remote, confirmed = await _publish_and_collect(session_id, reason, worker_id or WORKER_ID)
    except Exception as exc:  # noqa: BLE001
        logger.warning("turn-cancel bus failed for session %s: %s", session_id, exc)
        remote, confirmed = 0, False
    return CancelOutcome(cancelled=local + remote, confirmed=confirmed)
