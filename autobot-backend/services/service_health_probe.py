# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Live service-health probing and the snapshot other planes read (#22273).

``ServiceRegistry.check_all_services_health`` used to run only from the CLI, so every
service stayed UNKNOWN with ``last_check`` 0. The scheduled ``tasks.probe_service_health``
calls :func:`probe_and_store`: it probes through the registry, which updates ``last_check``
and ``failure_count`` on its own health records, then writes one Redis hash entry per
service. The hash is what the backend process, the SLM plane and the self-model read via
:func:`read_service_health_snapshot`; the worker's in-process registry is not visible to them.
"""

import json
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from utils.celery_schedules import SERVICE_HEALTH_PROBE_INTERVAL_SECONDS
from utils.service_registry import get_service_registry

logger = get_logger(__name__)

#: Redis hash (service name -> JSON health record) holding the latest probe of every service.
SERVICE_HEALTH_SNAPSHOT_KEY = "autobot:service_health:snapshot"

#: A snapshot outlives a few missed probes, then expires, so a stopped prober reads as "no data".
_SNAPSHOT_TTL_INTERVALS = 5


def _record(health: Any) -> str:
    """One service's health as the JSON stored in the snapshot."""
    return json.dumps(
        {
            "status": health.status.value,
            "last_check": health.last_check,
            "failure_count": health.failure_count,
            "response_time": health.response_time,
        }
    )


async def _publish_snapshot(redis_client: Any, records: Dict[str, str]) -> None:
    """Replace the snapshot hash and set its expiry in one MULTI/EXEC transaction.

    Delete-then-write makes the stored set exactly the probed set, so a service that left the
    registry drops out; the transaction means readers never see an empty or unexpiring hash.
    """
    ttl = SERVICE_HEALTH_PROBE_INTERVAL_SECONDS * _SNAPSHOT_TTL_INTERVALS
    pipe = redis_client.pipeline(transaction=True)
    pipe.delete(SERVICE_HEALTH_SNAPSHOT_KEY)
    pipe.hset(SERVICE_HEALTH_SNAPSHOT_KEY, mapping=records)
    pipe.expire(SERVICE_HEALTH_SNAPSHOT_KEY, ttl)
    await pipe.execute()


async def probe_and_store() -> Dict[str, Dict[str, Any]]:
    """Probe every registered service, store the snapshot, and return it."""
    report = await get_service_registry().check_all_services_health()
    records = {name: _record(health) for name, health in report.items()}
    redis_client = await get_redis_client(async_client=True, database="main")
    if records and redis_client is not None:
        await _publish_snapshot(redis_client, records)
    logger.info("Service health probe: %d services stored", len(records))
    return {name: json.loads(raw) for name, raw in records.items()}


async def read_service_health_snapshot() -> Dict[str, Dict[str, Any]]:
    """The last stored probe of every service; empty when nothing was probed recently."""
    redis_client = await get_redis_client(async_client=True, database="main")
    if redis_client is None:
        return {}
    raw = await redis_client.hgetall(SERVICE_HEALTH_SNAPSHOT_KEY)
    return {_text(name): json.loads(_text(value)) for name, value in raw.items()}


def _text(value: Any) -> str:
    """A Redis reply as text, whether the client decodes responses or not."""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)
