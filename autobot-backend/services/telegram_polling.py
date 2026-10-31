# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Outbound long-polling ingest for the Telegram bot (#19010).

The webhook needs Telegram to reach AutoBot over public HTTPS, which a local,
LAN-only or NAT install cannot offer. Polling inverts the direction: AutoBot
asks Telegram for updates with ``getUpdates``, so no inbound route is needed.

The ingest mode is one stored value, ``webhook`` or ``polling``, so the two can
never both be live: selecting polling deletes the webhook, selecting webhook
stops the poller at its next tick (and Telegram itself refuses ``getUpdates``
while a webhook is set).

Exactly one backend worker polls, under a :class:`LeaderLease` -- two pollers on
one token take updates from each other and Telegram answers the second with 409.
Each update goes through the same ``process_telegram_update`` the webhook calls,
so there is one routing path, not two.

Delivery is at-most-once: the offset is persisted before an update's reply is
generated, so a restart never replays (and never re-answers) a message, at the
cost of dropping one whose reply was in flight when the worker died.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiohttp

from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.http_client import get_http_client
from autobot_shared.http_egress_guard import EGRESS_POLICY
from autobot_shared.leader_lease import DEFAULT_TTL_MS, LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from services.telegram_bot_service import TelegramBotService

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

TELEGRAM_INGEST_MODE_KEY = "autobot:settings:telegram_ingest_mode"
TELEGRAM_POLL_OFFSET_KEY = "autobot:telegram:poll_offset"
TELEGRAM_POLL_LEASE_KEY = "autobot:telegram:poll_leader"

INGEST_MODE_WEBHOOK = "webhook"
INGEST_MODE_POLLING = "polling"
INGEST_MODES = (INGEST_MODE_WEBHOOK, INGEST_MODE_POLLING)

#: The lease is renewed at the start of every tick and a tick is at most one
#: long poll or one idle wait, so both must end well inside the lease lifetime
#: -- otherwise a second worker could take the lease while this one still polls.
_LEASE_TTL_S = DEFAULT_TTL_MS // 1000
_LEASE_MARGIN_S = env_int_clamped("AUTOBOT_TELEGRAM_POLL_LEASE_MARGIN_SECONDS", 5, min_v=1, max_v=_LEASE_TTL_S // 2)
_MAX_TICK_S = _LEASE_TTL_S - _LEASE_MARGIN_S
#: HTTP round-trip allowance on top of the long poll; poll + slack is the whole
#: HTTP budget and is capped at _MAX_TICK_S, so even a stalled request ends
#: inside the lease.
_POLL_HTTP_SLACK_S = env_int_clamped("AUTOBOT_TELEGRAM_POLL_HTTP_SLACK_SECONDS", 5, min_v=1, max_v=_MAX_TICK_S // 2)
POLL_TIMEOUT_S = env_int_clamped(
    "AUTOBOT_TELEGRAM_POLL_TIMEOUT_SECONDS", 20, min_v=1, max_v=_MAX_TICK_S - _POLL_HTTP_SLACK_S
)
#: Wait between ingest-mode checks while not polling, so webhook mode does not
#: have the leader re-reading Redis every second for ever.
POLL_IDLE_S = env_float_clamped("AUTOBOT_TELEGRAM_POLL_IDLE_SECONDS", 15.0, min_v=1.0, max_v=float(_MAX_TICK_S))
MAX_CONCURRENT_REPLIES = env_int_clamped("AUTOBOT_TELEGRAM_MAX_CONCURRENT_REPLIES", 4, min_v=1, max_v=64)
#: Most polled updates held in memory (queued or replying) at once. While the
#: queue is full the poller fetches nothing, so a backlog stays with Telegram
#: instead of in memory, where a restart would drop all of it.
MAX_PENDING_REPLIES = env_int_clamped("AUTOBOT_TELEGRAM_MAX_PENDING_REPLIES", 16, min_v=1, max_v=1000)
#: Telegram's own ceiling on ``getUpdates`` ``limit``.
_GET_UPDATES_MAX_LIMIT = 100
#: Pause between ticks. The long poll itself is the wait, so this only spaces
#: out back-to-back batches; it is not a tuning knob.
_LEASE_REFRESH_S = 1.0
#: The shared client's 10s socket-read limit would cut every long poll short.
_POLL_HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=POLL_TIMEOUT_S + _POLL_HTTP_SLACK_S, sock_read=POLL_TIMEOUT_S + _POLL_HTTP_SLACK_S
)

#: Only message updates are routed (``process_telegram_update`` ignores the rest),
#: so asking Telegram for anything else would only advance the offset past it.
_ALLOWED_UPDATES = ["message"]


async def get_ingest_mode() -> str:
    """The stored ingest mode; ``webhook`` when never set, as before polling existed."""
    redis = await get_redis_client(async_client=True)
    if redis is None:
        return INGEST_MODE_WEBHOOK
    mode = await redis.get(TELEGRAM_INGEST_MODE_KEY)
    mode = mode.decode("utf-8") if isinstance(mode, bytes) else mode
    return mode if mode in INGEST_MODES else INGEST_MODE_WEBHOOK


async def save_ingest_mode(mode: str) -> None:
    """Persist the ingest mode. Raises ValueError for an unknown mode."""
    if mode not in INGEST_MODES:
        raise ValueError(f"Unknown Telegram ingest mode: {mode!r}")
    redis = await get_redis_client(async_client=True)
    if redis is None:
        raise RuntimeError("Redis client not available")
    await redis.set(TELEGRAM_INGEST_MODE_KEY, mode)


def offset_key(bot_token: str) -> str:
    """The offset key for one bot: ``update_id`` sequences are per bot.

    Keyed by the bot's numeric id (the public token prefix before ``:``), so a
    token swap starts from the new bot's own offset instead of confirming its
    pending updates away. A token without that shape is keyed by a digest; the
    token itself is never stored or logged.
    """
    bot_id = bot_token.split(":", 1)[0]
    if not bot_id.isdigit():
        bot_id = "sha256-" + hashlib.sha256(bot_token.encode("utf-8")).hexdigest()[:16]
    return f"{TELEGRAM_POLL_OFFSET_KEY}:{bot_id}"


async def _load_offset(redis: Any, key: str) -> int:
    raw = await redis.get(key)
    return int(raw) if raw else 0


async def _call_bot_api(service: TelegramBotService, method: str, payload: Dict[str, Any], **kwargs: Any) -> Any:
    """POST one Bot API method; returns ``result`` or raises on ``ok: false``."""
    if not service.bot_token or not service.base_url:
        raise ValueError("Telegram bot token not configured")
    url = f"{service.base_url}/{method}"
    try:
        async with get_http_client().tracked_request(
            "POST", url, json=payload, guard_egress=EGRESS_POLICY, **kwargs
        ) as response:
            body = await response.json()
    except aiohttp.ClientError as exc:
        # aiohttp errors carry the request URL, and the URL carries the bot token;
        # the lease loop logs whatever propagates, so only the type leaves here.
        raise RuntimeError(f"Telegram {method} request failed: {type(exc).__name__}") from None
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {body.get('description')}")
    return body.get("result")


async def delete_webhook(service: TelegramBotService) -> None:
    """Remove any registered webhook so ``getUpdates`` is allowed."""
    await _call_bot_api(service, "deleteWebhook", {"drop_pending_updates": False})
    logger.info("Deleted Telegram webhook for polling ingest")


async def fetch_updates(
    service: TelegramBotService, offset: int, limit: int = _GET_UPDATES_MAX_LIMIT
) -> List[Dict[str, Any]]:
    """One ``getUpdates`` long-poll starting at *offset*, at most *limit* updates."""
    payload = {
        "offset": offset,
        "limit": max(1, min(limit, _GET_UPDATES_MAX_LIMIT)),
        "timeout": POLL_TIMEOUT_S,
        "allowed_updates": _ALLOWED_UPDATES,
    }
    return await _call_bot_api(service, "getUpdates", payload, timeout=_POLL_HTTP_TIMEOUT) or []


async def poll_once(app: "FastAPI") -> Optional[int]:
    """Fetch and dispatch one batch; the count dispatched, or None when not polling.

    The offset is saved before each update is handed off, so a crash mid-reply
    cannot cause the same message to be answered twice after restart.

    Backpressure: a batch is at most the room left under ``MAX_PENDING_REPLIES``
    (Telegram's ``limit``), and nothing is fetched while that room is zero, so
    the offset only ever advances past updates that were actually queued.

    A flip to webhook mode is seen at the next tick; a ``getUpdates`` already in
    flight then ends early, because Telegram fails it once ``setWebhook`` lands.
    """
    if await get_ingest_mode() != INGEST_MODE_POLLING:
        return None
    redis = await get_redis_client(async_client=True)
    service = await TelegramBotService.from_redis()
    if redis is None or not service.bot_token:
        return None
    dispatcher = _dispatcher_for(app)
    room = MAX_PENDING_REPLIES - len(dispatcher.tasks)
    if room <= 0:
        return 0
    key = offset_key(service.bot_token)
    updates = (await fetch_updates(service, await _load_offset(redis, key), room))[:room]
    for update in updates:
        await redis.set(key, int(update["update_id"]) + 1)
        dispatcher.submit(app, update)
    return len(updates)


class _ReplyDispatcher:
    """Runs polled updates off the poll loop: in order per chat, bounded overall.

    A reply can take as long as the LLM does; awaiting it in the poll would hold
    the poller past its lease and let a second worker poll the same token. Each
    chat gets one lock, taken in submission order, so a chat's messages are
    answered in the order they were sent; the semaphore caps replies across chats.
    """

    def __init__(self, limit: int) -> None:
        self._slots = asyncio.Semaphore(limit)
        self._chats: Dict[str, List[Any]] = {}  # chat id -> [lock, pending count]
        self.tasks: set = set()

    def submit(self, app: "FastAPI", update: Dict[str, Any]) -> None:
        chat_id = str((update.get("message") or {}).get("chat", {}).get("id", ""))
        entry = self._chats.setdefault(chat_id, [asyncio.Lock(), 0])
        entry[1] += 1
        task = asyncio.create_task(self._run(app, update, chat_id, entry[0]), name="telegram-update")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, app: "FastAPI", update: Dict[str, Any], chat_id: str, lock: asyncio.Lock) -> None:
        from api.telegram_bot import process_telegram_update

        try:
            async with lock, self._slots:
                await process_telegram_update(app, update)
        except Exception:
            logger.exception("Failed to process polled Telegram update in chat %s", chat_id)
        finally:
            entry = self._chats[chat_id]
            entry[1] -= 1
            if entry[1] == 0:
                del self._chats[chat_id]


def _dispatcher_for(app: "FastAPI") -> _ReplyDispatcher:
    dispatcher = getattr(app.state, "telegram_dispatcher", None)
    if dispatcher is None:
        dispatcher = _ReplyDispatcher(MAX_CONCURRENT_REPLIES)
        app.state.telegram_dispatcher = dispatcher
        app.state.telegram_update_tasks = dispatcher.tasks
    return dispatcher


async def start_polling(app: "FastAPI") -> None:
    """Start the leader-elected poller (NON-CRITICAL); idle unless mode is polling."""
    lease = LeaderLease(key=TELEGRAM_POLL_LEASE_KEY, refresh_s=_LEASE_REFRESH_S, label="telegram-poller")

    async def _tick() -> None:
        if await poll_once(app) is None:
            await asyncio.sleep(POLL_IDLE_S)

    async def _run() -> None:
        try:
            await lease.run(on_tick=_tick)
        finally:
            # Hand the lease over at once on shutdown rather than after its TTL.
            await lease.release()

    app.state.telegram_poller_task = asyncio.create_task(_run(), name="telegram-poller")
    logger.info("Telegram poller started (active only in polling ingest mode)")


__all__ = [
    "INGEST_MODES",
    "INGEST_MODE_POLLING",
    "INGEST_MODE_WEBHOOK",
    "delete_webhook",
    "fetch_updates",
    "get_ingest_mode",
    "offset_key",
    "poll_once",
    "save_ingest_mode",
    "start_polling",
]
