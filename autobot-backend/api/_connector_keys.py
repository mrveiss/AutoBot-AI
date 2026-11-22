# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where a knowledge connector's config and sync history live in Redis (Issue #1254)."""

import asyncio

from autobot_shared.redis_client import get_redis_client
from knowledge.connectors.job_state import JOB_KEY_SUFFIX

_REDIS_KEY_PREFIX = "connector:"
_HISTORY_KEY_SUFFIX = ":history"
#: Suffixes / infixes that mark non-config Redis keys under the ``connector:`` namespace.
NON_CONFIG_INFIXES = (_HISTORY_KEY_SUFFIX, JOB_KEY_SUFFIX, ":schedule:", "scheduler:")


def is_config_key(key: str) -> bool:
    """True when *key* is a connector's config record, not its history, job state or schedule."""
    stripped = key[len(_REDIS_KEY_PREFIX) :]
    return not any(infix in stripped for infix in NON_CONFIG_INFIXES)


def _connector_key(connector_id: str) -> str:
    return "%s%s" % (_REDIS_KEY_PREFIX, connector_id)


def _history_key(connector_id: str) -> str:
    return "%s%s%s" % (_REDIS_KEY_PREFIX, connector_id, _HISTORY_KEY_SUFFIX)


async def _delete_connector_keys(connector_id: str) -> None:
    """Remove connector config and history from Redis (Issue #1254)."""
    redis = get_redis_client(database="knowledge")
    await asyncio.to_thread(redis.delete, _connector_key(connector_id), _history_key(connector_id))
