#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Example: Service Failure Monitoring via Redis Pub/Sub (#3404)

Demonstrates how to subscribe to HealthCollector state-change events
and react to systemd service failures in real time.

The SLM HealthCollector publishes to:
    autobot:services:{service_name}:state_change

each time a monitored service transitions between states (e.g. running ->
failed).  This script shows a standalone monitoring loop that:

1. Subscribes to all service state-change channels using a glob pattern.
2. Parses each message and logs the transition.
3. Sends an in-app notification via NotificationService for failure states.

Run this script directly to verify the integration end-to-end in a
development environment where Redis is available.
"""

import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# States that should trigger an alert.
_ALERT_STATES = frozenset({"failed", "crash-loop"})

# Pub/sub pattern that matches every service on every host.
_SUBSCRIPTION_PATTERN = "autobot:services:*:state_change"


async def _send_failure_notification(payload: dict) -> None:
    """Send an in-app SERVICE_FAILED notification for the given payload."""
    try:
        from services.notification_service import (
            NotificationChannel,
            NotificationConfig,
            NotificationEvent,
            NotificationService,
        )

        config = NotificationConfig(
            workflow_id=f"svc-monitor:{payload['service']}",
            channels={
                NotificationEvent.SERVICE_FAILED.value: [
                    NotificationChannel.IN_APP.value,
                ]
            },
            # Replace with the operator's user ID or fetch from config.
            user_id="admin",
        )
        svc = NotificationService()
        await svc.send(
            event=NotificationEvent.SERVICE_FAILED,
            workflow_id=config.workflow_id,
            payload=payload,
            config=config,
        )
        logger.info(
            "Notification sent for service=%s state=%s",
            payload.get("service"),
            payload.get("new_state"),
        )
    except Exception as exc:
        logger.error("Failed to send notification: %s", exc)


async def monitor_service_health() -> None:
    """Subscribe to HealthCollector state-change events and react to failures."""
    from autobot_shared.redis_client import get_redis_client

    redis = await get_redis_client(async_client=True, database="main")
    if redis is None:
        logger.error("Could not connect to Redis — aborting monitor loop.")
        return

    pubsub = redis.pubsub()
    await pubsub.psubscribe(_SUBSCRIPTION_PATTERN)
    logger.info("Subscribed to pattern: %s", _SUBSCRIPTION_PATTERN)

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        raw_data = message.get("data", b"")
        try:
            payload = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Skipping malformed message on %s: %s", message["channel"], exc)
            continue

        service = payload.get("service", "<unknown>")
        hostname = payload.get("hostname", "<unknown>")
        prev_state = payload.get("prev_state", "")
        new_state = payload.get("new_state", "")
        error_context = payload.get("error_context", "")

        logger.info(
            "State change: host=%s service=%s %s -> %s",
            hostname,
            service,
            prev_state,
            new_state,
        )

        if new_state in _ALERT_STATES:
            logger.warning(
                "ALERT: service=%s entered state=%s on host=%s — %s",
                service,
                new_state,
                hostname,
                error_context or "(no error context)",
            )
            await _send_failure_notification(payload)


def main() -> None:
    """Entry point for running the monitor loop."""
    try:
        asyncio.run(monitor_service_health())
    except KeyboardInterrupt:
        logger.info("Monitor stopped by operator.")


if __name__ == "__main__":
    main()
