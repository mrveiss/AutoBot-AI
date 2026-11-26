# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The scheduled probe populates service health outside the CLI (#22273)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from autobot_shared.service_registry_core import ServiceHealth
from autobot_shared.status_enums import HealthStatus
from services import service_health_probe as probe


def _registry(report: dict) -> MagicMock:
    registry = MagicMock()
    registry.check_all_services_health = AsyncMock(return_value=report)
    return registry


def test_probe_stores_last_check_and_failure_count_per_service():
    report = {
        "backend": ServiceHealth(status=HealthStatus.HEALTHY, last_check=100.0, failure_count=0, response_time=0.1),
        "redis": ServiceHealth(status=HealthStatus.UNHEALTHY, last_check=101.0, failure_count=2),
    }
    redis_client = MagicMock(hset=AsyncMock(), expire=AsyncMock())
    with (
        patch.object(probe, "get_service_registry", return_value=_registry(report)),
        patch.object(probe, "get_redis_client", return_value=redis_client),
    ):
        snapshot = asyncio.run(probe.probe_and_store())

    assert snapshot["redis"] == {"status": "unhealthy", "last_check": 101.0, "failure_count": 2, "response_time": 0}
    stored = redis_client.hset.await_args.kwargs["mapping"]
    assert json.loads(stored["backend"])["last_check"] == 100.0
    redis_client.expire.assert_awaited_once()


def test_read_snapshot_decodes_bytes_and_text_replies():
    raw = {b"backend": b'{"status": "healthy", "failure_count": 0}', "redis": '{"status": "unhealthy"}'}
    redis_client = MagicMock(hgetall=AsyncMock(return_value=raw))
    with patch.object(probe, "get_redis_client", return_value=redis_client):
        snapshot = asyncio.run(probe.read_service_health_snapshot())
    assert snapshot == {"backend": {"status": "healthy", "failure_count": 0}, "redis": {"status": "unhealthy"}}


def test_probe_is_on_the_beat_schedule():
    from celery_app import celery_app
    from tasks.service_health_probe_task import probe_service_health

    assert probe_service_health.name == "tasks.probe_service_health"
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "tasks.probe_service_health" in scheduled
