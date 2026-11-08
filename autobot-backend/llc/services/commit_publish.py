# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Publish a Redis notification only once the caller's transaction commits (#21080).

The message rides :func:`~.after_commit.defer_until_commit`: ``after_commit`` sends it, a rollback
(outer or SAVEPOINT) drops what it undid.
"""

import json
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from .after_commit import defer_until_commit

logger = get_logger(__name__)


async def _deliver(channel: str, payload: str) -> None:
    """Publish now; a Redis failure is logged and never raised (the commit already happened)."""
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.publish(channel, payload)
    except Exception:
        logger.warning("Failed to publish notification on %s; non-fatal", channel, exc_info=True)


async def publish_after_commit(session: AsyncSession, channel: str, message: Dict[str, Any]) -> None:
    """Queue *message* for *channel* until *session* commits; a rollback sends nothing.

    An object that is not a real SQLAlchemy session has no commit to follow, so it goes out at once.
    """
    payload = json.dumps(message)
    immediate = defer_until_commit(session, lambda: _deliver(channel, payload), f"publish on {channel}")
    if immediate is not None:
        await immediate
