# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis persistence for per-workflow notification configuration (#3166).

Key schema::

    autobot:workflow:notif_config:{workflow_id}  — JSON blob, 7-day TTL

The notification config is a simple dataclass so we serialise it with
``dataclasses.asdict`` and reconstruct it with ``NotificationConfig(**data)``.
"""

import json
from dataclasses import asdict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.redis_constants import REDIS_KEY
from constants.ttl_constants import TTL_7_DAYS
from services.notification_service import NotificationConfig

logger = get_logger(__name__)

_NOTIF_CONFIG_TTL = TTL_7_DAYS


def _notif_config_key(workflow_id: str) -> str:
    return f"{REDIS_KEY.NAMESPACE}:workflow:notif_config:{workflow_id}"


async def save_notification_config(
    workflow_id: str,
    config: NotificationConfig | None,
) -> None:
    """Persist *config* to Redis, or delete the key when *config* is None."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        logger.warning(
            "Redis unavailable — notification config not persisted (workflow=%s)",
            workflow_id,
        )
        return
    key = _notif_config_key(workflow_id)
    if config is None:
        await redis.delete(key)
        logger.debug("Deleted notification config from Redis (workflow=%s)", workflow_id)
        return
    payload = json.dumps(asdict(config), ensure_ascii=False)
    await redis.set(key, payload, ex=_NOTIF_CONFIG_TTL)
    logger.debug("Persisted notification config to Redis (workflow=%s)", workflow_id)


async def load_notification_config(
    workflow_id: str,
) -> NotificationConfig | None:
    """Load notification config from Redis; returns None when not found."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        logger.warning(
            "Redis unavailable — cannot load notification config (workflow=%s)",
            workflow_id,
        )
        return None
    key = _notif_config_key(workflow_id)
    raw = await redis.get(key)
    if raw is None:
        return None
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        data = json.loads(text)
        return NotificationConfig(**data)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "Malformed notification config in Redis (workflow=%s): %s",
            workflow_id,
            exc,
        )
        return None
