# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Publish a Redis notification only once the caller's transaction commits (#21080).

Same hooks as ``activity_log`` and the checkout-fence release in ``work_item_own_task``: the message is
queued on the session, ``after_commit`` sends it, a rollback (outer or SAVEPOINT) drops what it undid.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from autobot_shared.redis_client import get_async_redis_client

from ..scheduler.event_wake import within_transaction

logger = logging.getLogger(__name__)

_PENDING_KEY = "llc_commit_publish_pending"
_HOOKED_KEY = "llc_commit_publish_hooked"
#: Strong references so a publish task is not collected before it runs.
_publish_tasks: "set[asyncio.Task[None]]" = set()


@dataclass(frozen=True)
class _Pending:
    channel: str
    payload: str
    transaction: Optional[SessionTransaction]


async def _deliver(channel: str, payload: str) -> None:
    """Publish now; a Redis failure is logged and never raised (the commit already happened)."""
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.publish(channel, payload)
    except Exception:
        logger.exception("Failed to publish notification on %s — non-fatal", channel)


def _spawn(channel: str, payload: str) -> None:
    try:
        task = asyncio.get_running_loop().create_task(_deliver(channel, payload))
    except RuntimeError:
        logger.warning("No event loop to publish a notification on %s; it is dropped", channel)
        return
    _publish_tasks.add(task)
    task.add_done_callback(_publish_tasks.discard)


def _send_committed(sync: Session) -> None:
    """``after_commit``: send each queued message. Also fires on a SAVEPOINT release, which can still roll back."""
    if sync.in_nested_transaction():
        return
    for pending in sync.info.pop(_PENDING_KEY, []):
        _spawn(pending.channel, pending.payload)


def _drop_undone(sync: Session, previous_transaction: SessionTransaction) -> None:
    """``after_soft_rollback``: drop the messages whose transaction this rollback undid."""
    pending = sync.info.get(_PENDING_KEY, [])
    pending[:] = [p for p in pending if not within_transaction(p.transaction, previous_transaction)]


async def publish_after_commit(session: AsyncSession, channel: str, message: Dict[str, Any]) -> None:
    """Queue *message* for *channel* until *session* commits; a rollback sends nothing.

    An object that is not a real SQLAlchemy session has no commit to follow, so it goes out at once.
    """
    payload = json.dumps(message)
    sync = getattr(session, "sync_session", None)
    if not isinstance(sync, Session):
        await _deliver(channel, payload)
        return
    if not sync.info.get(_HOOKED_KEY):
        event.listen(sync, "after_commit", _send_committed)
        event.listen(sync, "after_soft_rollback", _drop_undone)
        sync.info[_HOOKED_KEY] = True
    txn = sync.get_nested_transaction() or sync.get_transaction()
    sync.info.setdefault(_PENDING_KEY, []).append(_Pending(channel, payload, txn))
