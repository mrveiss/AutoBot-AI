# Implement a real-time monitoring task that triggers a notification when a specific Linux service enters a failed state

AutoBot monitors systemd services across your fleet and fires a notification the moment a service transitions to `failed` or `crash-loop` state.  No polling loop is required in your code — the SLM HealthCollector handles discovery; you only need to create a workflow that reacts to the Redis pub/sub event it emits.

## How it works

```
SLM node agent
  └─ HealthCollector.discover_all_services()   ← runs every health-check cycle
       └─ detects state change (e.g. active → failed)
            └─ publishes to Redis:
                 channel: autobot:services:{service_name}:state_change
                 payload: {service, hostname, prev_state, new_state, error_context}

AutoBot backend
  └─ TriggerService (REDIS_PUBSUB trigger)
       └─ fires workflow on matching channel
            └─ NotificationService.send(SERVICE_FAILED, channels=[...])
```

## Quick start — create the workflow via API

```python
import httpx

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN = "your-jwt-token"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,  # dev only
)

# Create a workflow that fires whenever nginx enters a failed state
workflow = client.post("/workflows", json={
    "name": "Alert on nginx failure",
    "trigger": {
        "type": "REDIS_PUBSUB",
        "config": {
            "channel": "autobot:services:nginx:state_change",
            "filter": {"new_state": ["failed", "crash-loop"]},
        },
    },
    "steps": [
        {
            "id": "notify",
            "type": "notification",
            "config": {
                "event": "service_failed",
                "channels": ["slack", "in_app"],
                "template_vars": {
                    "service":       "{{ trigger.payload.service }}",
                    "hostname":      "{{ trigger.payload.hostname }}",
                    "prev_state":    "{{ trigger.payload.prev_state }}",
                    "new_state":     "{{ trigger.payload.new_state }}",
                    "error_context": "{{ trigger.payload.error_context }}",
                },
            },
        }
    ],
}).json()

print(f"Workflow created: {workflow['id']}")
```

## Quick start — use the built-in template

1. Open **Workflow Automation** → **Templates**.
2. Select **Service Health Monitor**.
3. Click **Use Template**.
4. In the trigger, optionally change `autobot:services:*:state_change` to target a specific service, e.g. `autobot:services:postgresql:state_change`.
5. Configure the **Send service-failure notification** step — choose at least one channel (email, Slack, webhook, in_app).
6. Click **Save** and **Enable**.

The template file is at `autobot-backend/workflow_templates/service_health_monitor.yaml`.

## Monitor any service — standalone Python script

```python
"""
Real-time monitoring: triggers a notification when a Linux service enters a
failed state.  Run alongside AutoBot or as a standalone daemon.
"""
import asyncio
import json
import logging

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


async def monitor_service_for_failure(
    service_name: str,
    notification_channels: list[str] | None = None,
) -> None:
    """Subscribe to state-change events for *service_name* and send a
    notification whenever it enters a failed or crash-loop state.

    Args:
        service_name: systemd unit name to watch (e.g. "nginx" or "postgresql")
        notification_channels: list of channels to notify ("slack", "email",
            "webhook", "in_app").  Defaults to ["in_app"].
    """
    channels = notification_channels or ["in_app"]
    redis = await get_redis_client(async_client=True, database="main")

    pubsub = redis.pubsub()
    await pubsub.psubscribe(f"autobot:services:{service_name}:state_change")
    logger.info("Subscribed to state-change events for service: %s", service_name)

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        payload = json.loads(message["data"])
        new_state = payload.get("new_state", "")

        if new_state not in ("failed", "crash-loop"):
            continue

        logger.warning(
            "Service %s on %s entered %s state (was %s). Error: %s",
            payload.get("service"),
            payload.get("hostname"),
            new_state,
            payload.get("prev_state"),
            payload.get("error_context", ""),
        )

        # Publish a live event for the frontend WebSocket
        live_event = {
            "event": "service_failure",
            "channel": "global",
            "data": payload,
        }
        await redis.publish("autobot:live_events", json.dumps(live_event))

        # Send notification via AutoBot NotificationService
        from services.notification_service import (
            NotificationConfig,
            NotificationEvent,
            NotificationService,
        )

        config = NotificationConfig(
            workflow_id="service-monitor",
            channels={NotificationEvent.SERVICE_FAILED.value: channels},
            templates={},
            email_recipients=[],
        )
        svc = NotificationService()
        await svc.send(
            event=NotificationEvent.SERVICE_FAILED,
            config=config,
            template_vars=payload,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(monitor_service_for_failure("nginx", ["slack", "in_app"]))
```

See `docs/examples/service_failure_monitoring.py` for the full standalone example.

## Notification event type

The `NotificationEvent.SERVICE_FAILED` enum value (`"service_failed"`) is defined in `autobot-backend/services/notification_service.py`.  Its default message template is:

```
Service '{service}' on '{hostname}' transitioned {prev_state} -> {new_state}. {error_context}
```

Override it in your workflow step's `templates` config using Python `string.Template` syntax.

## Available notification channels

| Channel    | Config key      | Required env vars          |
|------------|-----------------|----------------------------|
| In-app     | `in_app`        | —                          |
| Slack      | `slack`         | `SLACK_WEBHOOK_URL`        |
| Email      | `email`         | `SMTP_*` vars              |
| Webhook    | `webhook`       | `NOTIFICATION_WEBHOOK_URL` |

## Monitor multiple services simultaneously

Subscribe to `autobot:services:*:state_change` (wildcard) to catch failures on any service across the entire fleet in a single subscription:

```python
"""
Monitor all services across the fleet and route notifications by severity.
"""
import asyncio
import json
import logging

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Map service names to notification channels based on criticality
SERVICE_CHANNELS = {
    "nginx":       ["slack", "in_app"],
    "postgresql":  ["slack", "email", "in_app"],
    "redis-server":["slack", "in_app"],
    "autobot-agent":["in_app"],
}
DEFAULT_CHANNELS = ["in_app"]


async def monitor_all_services() -> None:
    """Subscribe to every service state-change event on the fleet."""
    redis = await get_redis_client(async_client=True, database="main")
    pubsub = redis.pubsub()
    await pubsub.psubscribe("autobot:services:*:state_change")
    logger.info("Monitoring all fleet services for state changes")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        payload  = json.loads(message["data"])
        service  = payload.get("service", "unknown")
        new_state = payload.get("new_state", "")

        if new_state not in ("failed", "crash-loop"):
            continue

        channels = SERVICE_CHANNELS.get(service, DEFAULT_CHANNELS)

        logger.warning(
            "ALERT: %s on %s entered %s (was %s)",
            service, payload.get("hostname"), new_state, payload.get("prev_state"),
        )

        from services.notification_service import (
            NotificationConfig, NotificationEvent, NotificationService,
        )

        config = NotificationConfig(
            workflow_id="fleet-monitor",
            channels={NotificationEvent.SERVICE_FAILED.value: channels},
            templates={},
            email_recipients=[],
        )
        await NotificationService().send(
            event=NotificationEvent.SERVICE_FAILED,
            config=config,
            template_vars=payload,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(monitor_all_services())
```

## Create a multi-service workflow via API

```python
import httpx

client = httpx.Client(
    base_url="https://autobot.example.com:8443/api",
    headers={"Authorization": "Bearer your-jwt-token"},
    verify=False,
)

CRITICAL_SERVICES = ["nginx", "postgresql", "redis-server", "autobot-agent"]

for service in CRITICAL_SERVICES:
    workflow = client.post("/workflows", json={
        "name": f"Alert on {service} failure",
        "trigger": {
            "type": "REDIS_PUBSUB",
            "config": {
                "channel": f"autobot:services:{service}:state_change",
                "filter": {"new_state": ["failed", "crash-loop"]},
            },
        },
        "steps": [{
            "id": "notify",
            "type": "notification",
            "config": {
                "event": "service_failed",
                "channels": ["slack", "in_app"],
                "template_vars": {
                    "service":       "{{ trigger.payload.service }}",
                    "hostname":      "{{ trigger.payload.hostname }}",
                    "prev_state":    "{{ trigger.payload.prev_state }}",
                    "new_state":     "{{ trigger.payload.new_state }}",
                    "error_context": "{{ trigger.payload.error_context }}",
                },
            },
        }],
    }).json()
    print(f"Created workflow {workflow['id']} for {service}")
```

## Redis pub/sub channel patterns

| Pattern | Matches |
|---------|---------|
| `autobot:services:nginx:state_change` | nginx only |
| `autobot:services:*:state_change` | all services on all nodes |
| `autobot:services:postgresql:state_change` | postgresql only |
| `autobot:services:autobot-agent:state_change` | AutoBot agent service only |

## Architecture reference

- **HealthCollector** — `autobot-slm-backend/slm/agent/health_collector.py`
- **TriggerService** (REDIS_PUBSUB) — `autobot-backend/services/trigger_service.py`
- **NotificationService** — `autobot-backend/services/notification_service.py`
- **Workflow template** — `autobot-backend/workflow_templates/service_health_monitor.yaml`
- **Full example** — `docs/examples/service_failure_monitoring.py`
