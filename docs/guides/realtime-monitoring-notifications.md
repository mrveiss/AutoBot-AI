# Real-Time Monitoring and Notification System


## Quick Answer

**How do you set up real-time monitoring with failure detection and notifications in AutoBot?**

Use the `HealthCollector` to poll service status, publish alerts via Redis pub/sub,
and deliver real-time notifications to the frontend via WebSocket. Here is a
complete, self-contained script that monitors a service, detects failure, and sends
a notification through all channels:

```python
#!/usr/bin/env python3
"""Monitor a service, detect failure, send notification -- single cohesive flow."""

import asyncio
import json
import logging
import subprocess  # nosec B404

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import get_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_config = get_config()
BACKEND_URL = f"https://{_config.vm.main}:{_config.port.backend}"


async def monitor_and_notify(service_name: str = "nginx", interval: int = 30):
    """Monitor a systemd service and send alerts on failure.

    1. Checks service status via systemctl
    2. On failure: stores alert in Redis, publishes to pub/sub channel
    3. Publishes a WebSocket live event for real-time frontend notification
    4. Loops every `interval` seconds
    """
    redis = await get_redis_client(async_client=True, database="main")
    last_status = "unknown"

    while True:
        proc = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=5,
        )
        current = proc.stdout.strip()
        is_active = proc.returncode == 0

        if not is_active and current != last_status:
            severity = "CRITICAL" if current == "failed" else "WARNING"
            alert = {
                "type": "service_failure",
                "service": service_name,
                "status": current,
                "severity": severity,
                "message": f"Service {service_name} is {current}",
            }

            # Publish to Redis pub/sub for cross-service alerting
            await redis.publish("system_alerts", json.dumps(alert))

            # Publish to WebSocket live events channel for frontend delivery
            live_event = {"event": "service_failure", "channel": "global", "data": alert}
            await redis.publish("autobot:live_events", json.dumps(live_event))

            logger.warning("ALERT [%s]: %s is %s", severity, service_name, current)

        elif is_active and last_status in ("failed", "inactive"):
            recovery = {"type": "service_recovery", "service": service_name, "status": "active"}
            await redis.publish("system_alerts", json.dumps(recovery))
            logger.info("RECOVERED: %s is active", service_name)

        last_status = current
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(monitor_and_notify("autobot-backend", interval=15))
```

**Verify it works:**

```bash
curl -sk https://<backend-ip>:8443/api/system/health | python3 -m json.tool
redis-cli -h <database-ip> subscribe system_alerts
```

For the full implementation with SQLite storage, Prometheus metrics, auto-recovery,
and systemd unit setup, see [Section 6](#6-complete-implementation-example).

---


AutoBot provides a comprehensive real-time monitoring, alerting, and notification
system that spans the entire 6-VM distributed fleet. This guide covers every layer
of the stack -- from the low-level `SystemMonitor` class that polls hardware metrics
and stores them in SQLite, through the Prometheus-based alerting pipeline, to the
WebSocket live-event delivery mechanism that pushes notifications to connected
frontend clients in real time.

By following this guide you will be able to implement a monitoring task that detects
when a specific Linux service enters a failed state, triggers an alert, delivers a
WebSocket notification to every connected client, records the alert for historical
analysis, and optionally attempts automatic recovery.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Service Health Monitoring](#2-service-health-monitoring)
3. [API Endpoints for Monitoring](#3-api-endpoints-for-monitoring)
4. [Alert Configuration and Thresholds](#4-alert-configuration-and-thresholds)
5. [Notification Delivery Mechanisms](#5-notification-delivery-mechanisms)
6. [Complete Implementation Example](#6-complete-implementation-example)
7. [Continuous Monitoring Setup](#7-continuous-monitoring-setup)
8. [WebSocket Real-Time Event Stream](#8-websocket-real-time-event-stream)
9. [Prometheus Integration](#9-prometheus-integration)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Architecture Overview

### System Design

AutoBot's monitoring system is a multi-layer architecture composed of four
cooperating subsystems:

```
+---------------------------------------------------------------------+
|                         Frontend (VM1 .21)                           |
|  AdminMonitoringView.vue   WebSocket Client   Grafana Dashboards    |
+------------------+------------------+------------------+------------+
                   |                  |                  |
          REST API |        WebSocket |       iframe     |
                   v                  v                  v
+------------------+------------------+------------------+------------+
|                      Backend (Main .20, port 8443)                  |
|                                                                     |
|  api/system.py         api/monitoring.py        api/live_events.py  |
|  GET /health           MonitoringWebSocket      /ws/live            |
|  GET /health/detailed  Manager                  LiveEventManager    |
|                                                                     |
|  api/error_monitoring.py    api/alertmanager_webhook.py             |
|  GET /statistics            POST /webhook/alertmanager              |
|  GET /recent                                                        |
|  GET /health                api/prometheus_mcp.py                   |
|  POST /metrics/alert-       POST /mcp/{tool_name}                  |
|       threshold             GET  /mcp/tools                        |
|                                                                     |
|  PrometheusMetricsManager (autobot_shared/monitoring/)             |
|  ServiceHealthMetricsRecorder                                       |
+------------------+------------------+------------------+------------+
                   |                  |                  |
        psutil     |      Redis       |    Prometheus    |
        systemctl  |      pub/sub     |    scrape        |
                   v                  v                  v
+------------------+------------------+------------------+------------+
|  SystemMonitor   |  Redis (VM3 .23) |  Prometheus      |  Grafana   |
|  (monitoring_    |  channel:        |  AlertManager    |  (.23)     |
|   system.py)     |  system_alerts   |  alertmanager_   |            |
|  SQLite metrics  |  autobot:live_   |  rules.yml       |            |
|  database        |  events          |                  |            |
+------------------+------------------+------------------+------------+
                                      |
              +----------+------------+-----------+
              |          |            |           |
          VM1 .21    VM2 .22     VM3 .23     VM4 .24     VM5 .25
         Frontend   NPU Worker   Redis      AI Stack    Browser
              |          |            |           |           |
              +----- SLM Agent (health_collector.py) --------+
              |          per-node HealthCollector             |
              +----------------------------------------------+
                         |
                    SLM Admin (.19)
                    /api/health
                    /api/roles/fleet-health
```

### Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SystemMonitor` | `autobot-infrastructure/shared/scripts/monitoring_system.py` | Collects CPU, memory, disk, network metrics via `psutil`. Runs HTTP health checks against backend and Redis. Stores all data in a local SQLite database. |
| `HealthCollector` | `autobot-slm-backend/slm/agent/health_collector.py` | Runs on each fleet node as part of the SLM agent. Checks systemd service status via `systemctl`, discovers all services, collects system metrics, checks port connectivity. Reports failed/crash-looping services with journalctl error context. |
| `PrometheusMetricsManager` | `autobot_shared/monitoring/prometheus_metrics.py` | Thread-safe singleton that defines and records all Prometheus metrics. Delegates to domain-specific recorders (ServiceHealth, System, Redis, WebSocket, etc.). |
| `ServiceHealthMetricsRecorder` | `autobot_shared/monitoring/metrics/service_health.py` | Records service health scores, response times, and status (offline=0, healthy=1, degraded=2) as Prometheus gauges and histograms. |
| `MonitoringWebSocketManager` | `autobot-backend/api/monitoring.py` | Manages real-time WebSocket connections for the monitoring dashboard. Broadcasts performance metrics, alerts, and GPU/NPU utilization to connected clients. |
| `LiveEventManager` | `autobot-backend/live_event_manager.py` | Channel-based pub/sub for scoped WebSocket events. Supports channels: `agent:{id}`, `task:{id}`, `workflow:{id}`, `global`. |
| AlertManager Webhook | `autobot-backend/api/alertmanager_webhook.py` | Receives fired/resolved alerts from Prometheus AlertManager and broadcasts them to WebSocket clients. |
| Error Monitoring API | `autobot-backend/api/error_monitoring.py` | REST API for querying error statistics, recent errors, error categories, component breakdowns, and health status. Stores errors in Redis. |

### Alert Severity Levels

AutoBot uses a four-level severity system across all monitoring subsystems:

| Level | Numeric | When Used | Response Time |
|-------|---------|-----------|---------------|
| `INFO` / `low` | 0 | Informational events, successful recoveries | No immediate action |
| `WARNING` / `medium` | 1 | Approaching thresholds, degraded performance | Investigate within hours |
| `HIGH` / `high` | 2 | Threshold exceeded, service degraded | Investigate within minutes |
| `CRITICAL` / `critical` | 3 | Service down, data at risk, circuit breaker open | Immediate action required |

### Data Storage

**SQLite metrics database** (`reports/monitoring/metrics.db`):

The `SystemMonitor` class initializes and maintains four indexed tables:

| Table | Columns | Retention |
|-------|---------|-----------|
| `system_metrics` | `timestamp`, `cpu_percent`, `memory_percent`, `memory_used_mb`, `disk_percent`, `disk_used_gb`, `network_sent_mb`, `network_recv_mb`, `process_count`, `load_average` | 30 days |
| `application_metrics` | `timestamp`, `service_name`, `response_time_ms`, `error_count`, `success_count`, `active_connections`, `memory_usage_mb`, `cpu_usage_percent` | 30 days |
| `alerts` | `timestamp`, `alert_type`, `severity`, `message`, `resolved`, `resolved_at` | 90 days |
| `health_checks` | `timestamp`, `service_name`, `endpoint`, `status_code`, `response_time_ms`, `status`, `error_message` | 30 days |

All tables have a `timestamp` index for efficient time-range queries. The
`cleanup_old_metrics()` method runs automatically at 2:00 AM during continuous
monitoring and deletes rows older than the retention period.

**Redis error storage** (error monitoring subsystem):

Errors are stored in Redis under the key pattern `autobot:errors:*` with JSON
payloads containing timestamp, category, component, severity, and stack trace.
Errors are retrieved via Redis pipeline batching to avoid N+1 query patterns.

---

## 2. Service Health Monitoring

### Checking systemd Service Status with HealthCollector

The `HealthCollector` class (deployed on every fleet node via the SLM agent) is
the primary mechanism for monitoring Linux service status. It uses `systemctl`
to check service state and maps systemd states to AutoBot's status enum.

**Status mapping:**

| systemd `active_state` | systemd `sub_state` | AutoBot status |
|------------------------|---------------------|----------------|
| `active` | `running` | `running` |
| `failed` | `failed` | `failed` |
| `activating` | `auto-restart` | `crash-loop` |
| `inactive` | any | `stopped` |
| any other | any | `unknown` |

**Basic service check:**

```python
from autobot_slm_backend.slm.agent.health_collector import HealthCollector

# Initialize with specific services to monitor
collector = HealthCollector(
    services=["nginx", "autobot-backend", "redis-server"],
    ports=[
        {"host": "localhost", "port": 8443},
        {"host": "<database-ip>", "port": 6379},
    ],
    discover_services=True,
)

# Collect all health data
health = collector.collect()
# Returns:
# {
#     "timestamp": "2026-03-15T10:30:00",
#     "hostname": "autobot-main",
#     "cpu_percent": 23.4,
#     "memory_percent": 67.2,
#     "disk_percent": 45.1,
#     "load_avg": [1.2, 0.8, 0.5],
#     "uptime_seconds": 432000,
#     "services": {
#         "nginx": {"active": true, "status": "active"},
#         "autobot-backend": {"active": true, "status": "active"},
#         "redis-server": {"active": false, "status": "inactive"}
#     },
#     "ports": {
#         "localhost:8443": true,
#         "<database-ip>:6379": true
#     },
#     "discovered_services": [
#         {
#             "name": "nginx",
#             "status": "running",
#             "active_state": "active",
#             "sub_state": "running",
#             "load_state": "loaded",
#             "main_pid": 1234,
#             "memory_bytes": 8388608,
#             "description": "A high performance web server",
#             "enabled": true,
#             "n_restarts": 0
#         }
#     ]
# }
```

**Checking a single service:**

```python
collector = HealthCollector()

result = collector.check_service("autobot-backend")
# Returns: {"active": true, "status": "active"}
# or:      {"active": false, "status": "inactive"}
# or:      {"active": false, "status": "timeout"}

if not result["active"]:
    # Service is down -- result["status"] contains the systemd state
    print(f"Service is not active: {result['status']}")
```

**Detecting failed services with error context:**

When the `HealthCollector` discovers a service in `failed` or `crash-loop` state,
it automatically captures the last 5 lines of `journalctl` output so the SLM
dashboard can display the failure reason without requiring SSH access:

```python
collector = HealthCollector(discover_services=True)
health = collector.collect()

for svc in health.get("discovered_services", []):
    if svc["status"] in ("failed", "crash-loop"):
        print(f"FAILED: {svc['name']}")
        print(f"  State: {svc['active_state']}/{svc['sub_state']}")
        print(f"  Restarts: {svc.get('n_restarts', 'unknown')}")
        if svc.get("error_message"):
            print(f"  Error log:\n{svc['error_message']}")
```

### Quick Health Check Against Thresholds

```python
collector = HealthCollector(services=["nginx", "autobot-backend"])

# Check with custom thresholds
is_ok = collector.is_healthy(thresholds={
    "cpu_percent": 90,
    "memory_percent": 90,
    "disk_percent": 90,
})

if not is_ok:
    # At least one threshold exceeded or a monitored service is down
    print("Node is unhealthy")
```

### Monitoring with SystemMonitor

The `SystemMonitor` class provides a higher-level monitoring loop that combines
system metrics, application metrics, health checks, and alerting into a single
cycle:

```python
import asyncio
from pathlib import Path

# SystemMonitor lives in the infrastructure scripts
import sys
sys.path.insert(0, "/opt/autobot/autobot-infrastructure/shared/scripts")
from monitoring_system import SystemMonitor

async def run_single_check():
    """Run a single monitoring cycle and inspect results."""
    monitor = SystemMonitor(project_root=Path("/opt/autobot"))

    # Single cycle collects system metrics, app metrics, health checks
    results = await monitor.run_monitoring_cycle()

    system = results.get("system_metrics", {})
    health = results.get("health_results", {})

    print(f"CPU: {system.get('cpu_percent', 0):.1f}%")
    print(f"Memory: {system.get('memory_percent', 0):.1f}%")
    print(f"Overall health: {health.get('overall_status', 'unknown')}")

    # Check for triggered alerts
    if monitor.alerts_triggered:
        for alert in monitor.alerts_triggered:
            print(f"  ALERT [{alert['severity']}]: {alert['message']}")

asyncio.run(run_single_check())
```

**Continuous monitoring:**

```python
async def run_continuous():
    monitor = SystemMonitor()
    # Runs every 60 seconds, cleans up old data at 2 AM
    await monitor.start_monitoring(continuous=True)

asyncio.run(run_continuous())
```

---

## 3. API Endpoints for Monitoring

All backend endpoints are served over HTTPS on port 8443. The base URL is
`https://<backend-ip>:8443` (configured via `autobot_shared.ssot_config`).

### System Health Endpoints

#### `GET /api/system/health`

Public endpoint (no authentication required). Returns basic health status used by
frontend health monitors before login.

**Request:**

```bash
curl -sk https://<backend-ip>:8443/api/system/health | python3 -m json.tool
```

**Response (200 OK):**

```json
{
    "status": "healthy",
    "timestamp": "2026-03-15T10:30:00.123456",
    "initialization": {
        "status": "complete",
        "message": "Backend fully initialized"
    },
    "components": {
        "backend": "healthy",
        "config": "healthy",
        "logging": "healthy",
        "conversation_files_db": "healthy"
    }
}
```

**Possible `status` values:** `healthy`, `degraded`, `unhealthy`

The response is cached for 30 seconds via `@cache_response(ttl=30)`.

#### `GET /api/system/health/detailed`

Requires admin authentication. Returns comprehensive health including Redis,
LLM, knowledge base, system resources, and per-service status.

**Request:**

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
    https://<backend-ip>:8443/api/system/health/detailed | python3 -m json.tool
```

**Response (200 OK):**

```json
{
    "status": "healthy",
    "timestamp": "2026-03-15T10:30:00.123456",
    "detailed": true,
    "initialization": {
        "status": "complete",
        "message": "Backend fully initialized"
    },
    "components": {
        "backend": "healthy",
        "config": "healthy",
        "logging": "healthy",
        "redis": "healthy",
        "llm": "available",
        "knowledge_base": "available",
        "conversation_files_db": "healthy",
        "cpu_usage": "23.4%",
        "memory_usage": "67.2%",
        "disk_usage": "45.1%"
    },
    "cpu_percent": 23.4,
    "memory_percent": 67.2,
    "disk_percent": 45.1,
    "uptime_seconds": 432000,
    "services": [
        {"name": "redis", "status": "healthy"},
        {"name": "llm", "status": "healthy"},
        {"name": "knowledge_base", "status": "healthy"}
    ]
}
```

#### `GET /api/system/metrics`

Requires admin authentication. Returns system performance metrics including CPU,
memory, disk, and cache statistics.

**Request:**

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
    https://<backend-ip>:8443/api/system/metrics | python3 -m json.tool
```

**Response (200 OK):**

```json
{
    "timestamp": "2026-03-15T10:30:00.123456",
    "system": {
        "cpu_percent": 23.4,
        "memory": {
            "total": 34359738368,
            "available": 11264131072,
            "percent": 67.2,
            "used": 23095607296,
            "free": 2147483648
        },
        "disk": {
            "total": 536870912000,
            "used": 241591910400,
            "free": 295279001600,
            "percent": 45.0
        }
    },
    "python": {
        "version": "3.12.2",
        "executable": "/opt/autobot/autobot-backend/venv/bin/python3"
    },
    "cache": {
        "status": "active",
        "entries": 142,
        "hit_rate": 0.87
    }
}
```

### Error Monitoring Endpoints

All error monitoring endpoints are mounted under `/api/error-monitoring/`.

#### `GET /api/error-monitoring/statistics`

Returns system-wide error statistics aggregated from the error boundary system.

```bash
curl -sk https://<backend-ip>:8443/api/error-monitoring/statistics | python3 -m json.tool
```

```json
{
    "status": "success",
    "data": {
        "total_errors": 42,
        "categories": {
            "network": 15,
            "database": 8,
            "llm": 12,
            "server_error": 7
        },
        "severities": {
            "critical": 2,
            "high": 10,
            "medium": 18,
            "low": 12
        },
        "components": {
            "chat": 8,
            "knowledge_base": 6,
            "llm_interface": 12
        }
    }
}
```

#### `GET /api/error-monitoring/recent?limit=20`

Returns the most recent error reports stored in Redis (max 100).

```bash
curl -sk "https://<backend-ip>:8443/api/error-monitoring/recent?limit=5" | python3 -m json.tool
```

```json
{
    "status": "success",
    "data": {
        "errors": [
            {
                "timestamp": 1710489000,
                "category": "network",
                "component": "ai_stack_client",
                "severity": "high",
                "message": "Connection refused to AI Stack VM4",
                "trace_id": "abc-123-def"
            }
        ],
        "total_count": 42
    }
}
```

#### `GET /api/error-monitoring/health`

Returns the error system's own health assessment with a 0-100 score.

```bash
curl -sk https://<backend-ip>:8443/api/error-monitoring/health | python3 -m json.tool
```

```json
{
    "status": "success",
    "data": {
        "health_status": "healthy",
        "health_score": 90,
        "total_errors": 42,
        "critical_errors": 0,
        "high_errors": 3,
        "recommendations": [
            "System error handling is working well - continue monitoring"
        ]
    }
}
```

Health score computation:

| Condition | Status | Score |
|-----------|--------|-------|
| `critical_errors > 0` | `critical` | 0 |
| `high_errors > 5` | `degraded` | 30 |
| `total_errors > 20` | `warning` | 70 |
| `total_errors > 0` | `healthy` | 90 |
| No errors | `excellent` | 100 |

#### `GET /api/error-monitoring/categories`

Error breakdown by category with percentages.

#### `GET /api/error-monitoring/components`

Error breakdown by component, sorted by error count.

#### `GET /api/error-monitoring/metrics/summary`

Comprehensive error metrics summary from the metrics collector.

#### `GET /api/error-monitoring/metrics/timeline?hours=24&component=chat`

Time-bucketed error data for visualization. Hours range: 1-168.

#### `GET /api/error-monitoring/metrics/top-errors?limit=10`

Most frequent errors ranked by occurrence count. Limit range: 1-50.

#### `POST /api/error-monitoring/metrics/alert-threshold`

Set custom alert thresholds per component:

```bash
curl -sk -X POST \
    -H "Content-Type: application/json" \
    -d '{"component": "redis", "threshold": 5}' \
    https://<backend-ip>:8443/api/error-monitoring/metrics/alert-threshold
```

#### `POST /api/error-monitoring/metrics/resolve/{trace_id}`

Mark a specific error as resolved by its trace ID.

#### `POST /api/error-monitoring/metrics/cleanup`

Remove metrics older than the configured retention period.

### SLM Health Endpoints

The SLM admin server on `.19` provides fleet-wide health:

#### `GET /api/health`

```bash
curl -sk https://<slm-manager-ip>:8000/api/health | python3 -m json.tool
```

```json
{
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 86400,
    "database": "healthy",
    "nodes_online": 5,
    "nodes_total": 6
}
```

#### `GET /api/metrics` (authenticated)

```json
{
    "cpu_percent": 12.3,
    "memory_percent": 45.6,
    "disk_percent": 34.2,
    "load_average": [0.5, 0.3, 0.2]
}
```

#### `GET /api/ready` and `GET /api/live`

Kubernetes-style readiness and liveness probes.

#### `GET /api/health/database`

Detailed database health check for the SLM database layer.

---

## 4. Alert Configuration and Thresholds

### SystemMonitor Default Thresholds

The `SystemMonitor` class defines its thresholds in the `self.config` dictionary
at initialization:

```python
self.config = {
    "collection_interval": 60,  # seconds between monitoring cycles
    "retention_days": 30,       # system/app metrics retention
    # Alert retention is always 90 days (hardcoded in cleanup_old_metrics)
    "alert_thresholds": {
        "cpu_usage": 80,        # percent -- severity: warning
        "memory_usage": 85,     # percent -- severity: warning
        "disk_usage": 90,       # percent -- severity: critical
        "response_time": 5000,  # milliseconds
        "error_rate": 5,        # percentage
    },
}
```

When a threshold is exceeded, the `_check_system_alerts` method creates an alert
record with `severity: "warning"` (for CPU and memory) or `severity: "critical"`
(for disk) and stores it in the SQLite `alerts` table.

### HealthCollector Default Thresholds

The `HealthCollector.is_healthy()` method uses these defaults:

```python
defaults = {
    "cpu_percent": 90,
    "memory_percent": 90,
    "disk_percent": 90,
}
```

Additionally, any monitored service that is not `active` causes `is_healthy()`
to return `False`.

### Prometheus AlertManager Rules

The production alerting rules are defined in
`autobot-infrastructure/shared/config/prometheus/alertmanager_rules.yml` and
cover the following alert groups:

#### System Resource Alerts (`autobot_system_resources`)

| Alert | PromQL Expression | Duration | Severity |
|-------|-------------------|----------|----------|
| `HighCPUUsage` | `autobot_cpu_usage_percent > 80` | 5 min | high |
| `CriticalCPUUsage` | `autobot_cpu_usage_percent > 95` | 2 min | critical |
| `HighMemoryUsage` | `autobot_memory_usage_percent > 85` | 10 min | high |
| `CriticalMemoryUsage` | `autobot_memory_usage_percent > 95` | 3 min | critical |
| `HighDiskUsage` | `autobot_disk_usage_percent{mount_point="/"} > 85` | 1 hour | medium |
| `CriticalDiskUsage` | `autobot_disk_usage_percent{mount_point="/"} > 95` | 15 min | critical |

#### Service Health Alerts (`autobot_service_health`)

| Alert | PromQL Expression | Duration | Severity |
|-------|-------------------|----------|----------|
| `BackendAPIDown` | `autobot_service_status{service_name="backend",status="offline"} == 1` | 1 min | critical |
| `RedisUnavailable` | `autobot_service_status{service_name="redis",status="offline"} == 1` | 1 min | critical |
| `OllamaDown` | `autobot_service_status{service_name="ollama",status="offline"} == 1` | 2 min | high |
| `ServiceHighResponseTime` | `autobot_service_response_time_seconds > 5.0` | 5 min | medium |
| `ServiceLowHealthScore` | `autobot_service_health_score < 50` | 5 min | high |

#### Circuit Breaker Alerts (`autobot_circuit_breaker`)

| Alert | PromQL Expression | Duration | Severity |
|-------|-------------------|----------|----------|
| `CircuitBreakerOpen` | `autobot_circuit_breaker_state == 1` | 30 sec | critical |
| `CircuitBreakerHalfOpen` | `autobot_circuit_breaker_state == 2` | 2 min | warning |
| `CircuitBreakerHighFailures` | `autobot_circuit_breaker_failure_count >= 3` | 1 min | warning |
| `CircuitBreakerEventSpike` | `rate(autobot_circuit_breaker_events_total{event="opened"}[5m]) > 0.1` | 2 min | high |

#### Redis Alerts (`autobot_redis_alerts`)

| Alert | PromQL Expression | Duration | Severity |
|-------|-------------------|----------|----------|
| `RedisServerDown` | `autobot_redis_server_available == 0` | 30 sec | critical |
| `RedisConnectionErrors` | `rate(autobot_redis_connection_errors_total[5m]) > 1` | 2 min | high |
| `RedisHighMemory` | `autobot_redis_memory_used_bytes / autobot_redis_memory_peak_bytes > 0.9` | 10 min | warning |
| `RedisPoolExhausted` | `autobot_redis_connections_available / autobot_redis_connections_max < 0.1` | 1 min | high |
| `RedisHighLatency` | `histogram_quantile(0.95, ...) > 0.1` | 5 min | medium |

#### Error Rate Alerts (`autobot_error_monitoring`)

| Alert | PromQL Expression | Duration | Severity |
|-------|-------------------|----------|----------|
| `HighErrorRate` | `rate(autobot_errors_total[5m]) > 10` | 5 min | high |
| `CriticalErrorSpike` | `rate(autobot_errors_total[1m]) > 50` | 1 min | critical |
| `ComponentErrorRate` | `autobot_error_rate{time_window="1m"} > 0.1` | 5 min | medium |

#### Additional Alert Groups

The rules file also defines alerts for:

- **Claude API** (`autobot_claude_api`): High failure rate, slow responses, rate limit low
- **Workflow Monitoring** (`autobot_workflow_monitoring`): High failure rate, long duration
- **Network Monitoring** (`autobot_network_monitoring`): High network traffic
- **NPU Alerts** (`autobot_npu_alerts`): NPU circuit breaker open, high failure rate
- **Resource Exhaustion** (`autobot_resource_exhaustion`): Connection exhaustion, high timeout rate
- **Security Alerts** (`autobot_security_alerts`): Security violations, unusual error patterns

### Custom Threshold Configuration via API

Set component-specific alert thresholds at runtime:

```python
import aiohttp

async def set_custom_threshold(component: str, threshold: int):
    """Set a custom alert threshold for a component."""
    async with aiohttp.ClientSession() as session:
        await session.post(
            "https://<backend-ip>:8443/api/error-monitoring/metrics/alert-threshold",
            json={
                "component": component,
                "error_code": None,  # any error in component
                "threshold": threshold,
            },
            ssl=False,
        )

# Example: alert when redis errors exceed 3 in the window
await set_custom_threshold("redis", 3)
```

---

## 5. Notification Delivery Mechanisms

AutoBot provides four complementary notification channels. Each serves a
different use case and can be used independently or in combination.

### 5.1 WebSocket Live Events (Real-Time UI)

The `LiveEventManager` provides channel-scoped real-time event delivery to
connected frontend clients. This is the primary mechanism for instant
notifications in the web UI.

**How it works:**

1. Client connects to `wss://backend:8443/ws/live?token=<jwt>`
2. Client subscribes to channels: `{"action": "subscribe", "channel": "global"}`
3. Server publishes events to channels, which are delivered to all subscribers
4. Events also fan out to `global` channel subscribers automatically
5. Events include an auto-incrementing `event_id` per channel

**Publishing an alert from backend code:**

```python
from live_event_manager import publish_live_event

# Publish to all global subscribers
sent_count = await publish_live_event(
    channel="global",
    event_type="service_failure",
    payload={
        "service": "nginx",
        "status": "failed",
        "severity": "CRITICAL",
        "message": "Service nginx has entered failed state",
        "timestamp": "2026-03-15T10:30:00",
        "node": "<frontend-ip>",
    },
)
# sent_count = number of WebSocket clients that received the event
```

**Valid channels:** `global`, `agent:{id}`, `task:{id}`, `workflow:{id}`

### 5.2 Redis Pub/Sub (Cross-Service Alerting)

Redis pub/sub enables alert distribution across services that are not directly
connected via WebSocket. The monitoring alerts subsystem publishes to a
configurable channel (default: `system_alerts`).

```python
from autobot_shared.redis_client import get_redis_client
import json

async def publish_redis_alert(alert_data: dict):
    """Publish alert to Redis for cross-service consumption."""
    redis = await get_redis_client(async_client=True, database="main")
    await redis.publish("system_alerts", json.dumps(alert_data))
```

**Subscribing to alerts from another service:**

```python
async def listen_for_alerts():
    """Subscribe to Redis alert channel."""
    redis = await get_redis_client(async_client=True, database="main")
    pubsub = redis.pubsub()
    await pubsub.subscribe("system_alerts")

    async for message in pubsub.listen():
        if message["type"] == "message":
            alert = json.loads(message["data"])
            print(f"Alert received: [{alert['severity']}] {alert['message']}")
```

### 5.3 Prometheus Metrics + AlertManager (External Alerting)

Prometheus scrapes metrics from the backend at regular intervals. When a PromQL
rule expression evaluates to true for the configured duration, AlertManager fires
an alert to the backend webhook endpoint.

**Alert flow:**

```
Prometheus scrapes autobot_service_status metric
    -> PromQL rule evaluates: autobot_service_status{status="offline"} == 1
    -> AlertManager groups and routes the alert
    -> POST /api/webhook/alertmanager (AlertManagerWebhook payload)
    -> _process_alert() converts to frontend format
    -> ws_manager.broadcast_update() sends to all WebSocket clients
```

**AlertManager webhook payload structure:**

```json
{
    "version": "4",
    "groupKey": "{}:{alertname=\"BackendAPIDown\"}",
    "truncatedAlerts": 0,
    "status": "firing",
    "receiver": "autobot-webhook",
    "groupLabels": {"alertname": "BackendAPIDown"},
    "commonLabels": {
        "alertname": "BackendAPIDown",
        "severity": "critical",
        "component": "service",
        "service": "backend"
    },
    "commonAnnotations": {
        "summary": "Backend API Unavailable",
        "description": "Backend API is not responding",
        "recommendation": "Check backend service logs and restart if necessary"
    },
    "externalURL": "http://<backend-ip>:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "BackendAPIDown",
                "severity": "critical",
                "component": "service",
                "service": "backend"
            },
            "annotations": {
                "summary": "Backend API Unavailable",
                "description": "Backend API is not responding",
                "recommendation": "Check backend service logs and restart if necessary"
            },
            "startsAt": "2026-03-15T10:30:00.000Z",
            "endsAt": null,
            "generatorURL": "http://<backend-ip>:9090/graph?...",
            "fingerprint": "abc123def456"
        }
    ]
}
```

The webhook converts this to the frontend format with `type: "system_alert"` (for
firing) or `type: "alert_recovery"` (for resolved) and broadcasts via
`ws_manager.broadcast_update()`.

### 5.4 Monitoring WebSocket Dashboard (Performance Metrics)

The `MonitoringWebSocketManager` provides a dedicated WebSocket endpoint for
the admin monitoring dashboard with auto-updating metrics every 2 seconds
(configurable 0.5-30s):

```
wss://backend:8443/ws/monitoring
```

This broadcasts periodic updates containing performance dashboard data, GPU/NPU
metrics, and any performance alerts detected during the monitoring cycle.

---

## 6. Complete Implementation Example

The following is a complete, production-ready script that monitors a specific
Linux service, detects failure, triggers notifications through all available
channels, stores the alert, and optionally attempts automatic recovery.

```python
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Service Failure Monitor with Auto-Notification

Monitors a specified systemd service and triggers multi-channel notifications
when the service enters a failed state. Integrates with:
- SystemMonitor (SQLite alert storage)
- Redis pub/sub (cross-service alerting)
- LiveEventManager WebSocket (real-time UI notifications)
- Prometheus metrics (external alerting via ServiceHealthMetricsRecorder)
- REST API error reporting

Usage:
    python3 service_failure_monitor.py --service nginx --interval 30
    python3 service_failure_monitor.py --service autobot-backend --auto-recover
"""

import argparse
import asyncio
import json
import logging
import subprocess  # nosec B404 - required for systemctl
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Load configuration from SSOT
_config = get_config()
BACKEND_URL = f"https://{_config.vm.main}:{_config.port.backend}"
ALERT_CHANNEL = "system_alerts"
LIVE_EVENTS_CHANNEL = "autobot:live_events"


def check_service_status(service_name: str) -> dict:
    """
    Check systemd service status using systemctl.

    Args:
        service_name: Name of the systemd service (e.g., "nginx").

    Returns:
        Dict with keys: active (bool), status (str), details (dict).
    """
    result_data = {"active": False, "status": "unknown", "details": {}}

    # Check if service is active
    try:
        proc = subprocess.run(  # nosec B607 - systemctl is trusted
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = proc.stdout.strip()
        result_data["active"] = proc.returncode == 0
        result_data["status"] = status
    except subprocess.TimeoutExpired:
        result_data["status"] = "timeout"
        return result_data
    except FileNotFoundError:
        result_data["status"] = "systemctl_not_found"
        return result_data

    # Get detailed service properties
    try:
        detail_proc = subprocess.run(  # nosec B607
            [
                "systemctl", "show", service_name,
                "--property=MainPID,MemoryCurrent,NRestarts,"
                "ActiveEnterTimestamp,InactiveEnterTimestamp",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if detail_proc.returncode == 0:
            for line in detail_proc.stdout.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    result_data["details"][key] = value
    except Exception as exc:
        logger.debug("Could not get service details: %s", exc)

    # If failed, capture recent journal entries
    if not result_data["active"]:
        try:
            journal_proc = subprocess.run(  # nosec B607
                [
                    "journalctl", "-u", service_name,
                    "-n", "10", "--no-pager", "-q",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if journal_proc.returncode == 0:
                result_data["details"]["recent_logs"] = (
                    journal_proc.stdout.strip()
                )
        except Exception as exc:
            logger.debug("Could not get journal entries: %s", exc)

    return result_data


async def store_alert_sqlite(
    service_name: str,
    status: str,
    severity: str,
    message: str,
    db_path: Optional[Path] = None,
) -> None:
    """
    Store an alert in the SystemMonitor SQLite database.

    Args:
        service_name: Name of the failed service.
        status: Current service status string.
        severity: Alert severity (warning, critical).
        message: Human-readable alert message.
        db_path: Optional path to metrics.db. Defaults to standard location.
    """
    import sqlite3

    if db_path is None:
        db_path = Path("/opt/autobot/reports/monitoring/metrics.db")
    if not db_path.exists():
        logger.warning("Metrics database not found at %s", db_path)
        return

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO alerts (alert_type, severity, message)
                VALUES (?, ?, ?)
                """,
                (f"service_failure:{service_name}", severity, message),
            )
        logger.info("Alert stored in SQLite: %s", message)
    except Exception as exc:
        logger.error("Failed to store alert in SQLite: %s", exc)


async def publish_redis_alert(
    service_name: str,
    status: str,
    severity: str,
) -> None:
    """
    Publish alert to Redis pub/sub for cross-service consumption.

    Args:
        service_name: Name of the failed service.
        status: Current service status string.
        severity: Alert severity level.
    """
    alert_data = {
        "type": "service_failure",
        "service": service_name,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "severity": severity,
        "message": f"Service {service_name} is {status}",
    }

    try:
        redis = await get_redis_client(async_client=True, database="main")
        # Publish to the system alerts channel
        await redis.publish(ALERT_CHANNEL, json.dumps(alert_data))
        logger.info("Alert published to Redis channel: %s", ALERT_CHANNEL)

        # Also publish to the live events channel for WebSocket relay
        live_event = {
            "event": "service_failure",
            "channel": "global",
            "data": alert_data,
        }
        await redis.publish(LIVE_EVENTS_CHANNEL, json.dumps(live_event))
        logger.info("Live event published to Redis: %s", LIVE_EVENTS_CHANNEL)
    except Exception as exc:
        logger.error("Failed to publish Redis alert: %s", exc)


async def report_to_api(
    service_name: str,
    status: str,
    severity: str,
) -> None:
    """
    Report the alert to the backend error monitoring API.

    Args:
        service_name: Name of the failed service.
        status: Current service status string.
        severity: Alert severity level.
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Report to the error monitoring test endpoint in dev mode
            # In production, errors flow through the error boundary system
            await session.post(
                f"{BACKEND_URL}/api/error-monitoring/test-error",
                json={
                    "error_type": "ConnectionError",
                    "message": (
                        f"Service {service_name} entered {status} state"
                    ),
                },
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            logger.info("Alert reported to error monitoring API")
    except Exception as exc:
        logger.error("Failed to report to API: %s", exc)


async def update_prometheus_metrics(
    service_name: str,
    is_healthy: bool,
) -> None:
    """
    Update Prometheus service health metrics.

    The PrometheusMetricsManager singleton records service status as a gauge
    (0=offline, 1=online, 2=degraded) which Prometheus scrapes and evaluates
    against the alertmanager_rules.yml rules.

    Args:
        service_name: Name of the service.
        is_healthy: Whether the service is currently healthy.
    """
    try:
        from autobot_shared.monitoring.prometheus_metrics import (
            get_metrics_manager,
        )

        metrics = get_metrics_manager()
        status_str = "healthy" if is_healthy else "offline"
        metrics.update_service_status(service_name, status_str)
        metrics.update_service_health(
            service_name,
            100.0 if is_healthy else 0.0,
        )
        logger.info(
            "Prometheus metrics updated: %s = %s",
            service_name,
            status_str,
        )
    except ImportError:
        logger.debug("Prometheus metrics not available in this environment")
    except Exception as exc:
        logger.error("Failed to update Prometheus metrics: %s", exc)


async def attempt_recovery(service_name: str) -> bool:
    """
    Attempt to restart a failed service via systemctl.

    Args:
        service_name: Name of the service to restart.

    Returns:
        True if restart succeeded, False otherwise.
    """
    logger.info("Attempting to restart service: %s", service_name)
    try:
        proc = subprocess.run(  # nosec B607
            ["sudo", "systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            # Wait briefly then verify
            await asyncio.sleep(3)
            check = check_service_status(service_name)
            if check["active"]:
                logger.info(
                    "Service %s restarted successfully", service_name
                )
                return True
            else:
                logger.warning(
                    "Service %s restart completed but service is still %s",
                    service_name,
                    check["status"],
                )
        else:
            logger.error(
                "systemctl restart failed: %s", proc.stderr.strip()
            )
    except subprocess.TimeoutExpired:
        logger.error("Service restart timed out after 30 seconds")
    except Exception as exc:
        logger.error("Failed to restart service: %s", exc)

    return False


async def monitor_service_with_notification(
    service_name: str,
    check_interval: int = 30,
    auto_recover: bool = False,
    max_recovery_attempts: int = 3,
) -> None:
    """
    Monitor a Linux service and trigger multi-channel notifications on failure.

    This function runs in a continuous loop, checking the specified service at
    regular intervals. When a failure is detected, it:
    1. Stores the alert in the SQLite metrics database
    2. Publishes to Redis pub/sub for cross-service consumption
    3. Publishes a live event for WebSocket delivery to the frontend
    4. Reports the error through the REST API
    5. Updates Prometheus metrics for AlertManager evaluation
    6. Optionally attempts automatic recovery

    Args:
        service_name: systemd service name to monitor.
        check_interval: Seconds between health checks.
        auto_recover: Whether to attempt automatic restart on failure.
        max_recovery_attempts: Maximum restart attempts before giving up.
    """
    logger.info(
        "Starting service monitor: service=%s interval=%ds recover=%s",
        service_name,
        check_interval,
        auto_recover,
    )

    last_status = "unknown"
    recovery_attempts = 0

    while True:
        try:
            check = check_service_status(service_name)
            current_status = check["status"]

            if check["active"]:
                # Service is healthy
                if last_status != "active":
                    logger.info("Service %s is active", service_name)
                    # If recovering from failure, publish recovery event
                    if last_status in ("inactive", "failed", "timeout"):
                        await publish_redis_alert(
                            service_name, "recovered", "INFO"
                        )
                    recovery_attempts = 0

                # Update Prometheus: service is healthy
                await update_prometheus_metrics(service_name, True)
                last_status = "active"

            else:
                # Service is NOT active
                severity = (
                    "CRITICAL" if current_status == "failed" else "WARNING"
                )
                message = f"Service {service_name} is {current_status}"

                if current_status != last_status:
                    logger.warning(
                        "SERVICE ALERT [%s]: %s", severity, message
                    )

                    # 1. Store alert in SQLite
                    await store_alert_sqlite(
                        service_name,
                        current_status,
                        severity.lower(),
                        message,
                    )

                    # 2. Publish to Redis pub/sub
                    await publish_redis_alert(
                        service_name, current_status, severity
                    )

                    # 3. Report to REST API
                    await report_to_api(
                        service_name, current_status, severity
                    )

                    # 4. Update Prometheus metrics
                    await update_prometheus_metrics(service_name, False)

                # 5. Attempt auto-recovery if enabled
                if (
                    auto_recover
                    and recovery_attempts < max_recovery_attempts
                ):
                    recovery_attempts += 1
                    logger.info(
                        "Recovery attempt %d/%d for %s",
                        recovery_attempts,
                        max_recovery_attempts,
                        service_name,
                    )
                    recovered = await attempt_recovery(service_name)
                    if recovered:
                        current_status = "active"
                        recovery_attempts = 0
                elif (
                    auto_recover
                    and recovery_attempts >= max_recovery_attempts
                ):
                    logger.error(
                        "Max recovery attempts (%d) reached for %s. "
                        "Manual intervention required.",
                        max_recovery_attempts,
                        service_name,
                    )

                last_status = current_status

        except Exception as exc:
            logger.error(
                "Error in monitoring loop for %s: %s", service_name, exc
            )

        await asyncio.sleep(check_interval)


def main():
    """Parse arguments and start the service monitor."""
    parser = argparse.ArgumentParser(
        description="AutoBot Service Failure Monitor"
    )
    parser.add_argument(
        "--service",
        required=True,
        help=(
            "systemd service name to monitor "
            "(e.g., nginx, autobot-backend)"
        ),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--auto-recover",
        action="store_true",
        help="Attempt automatic service restart on failure",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum recovery attempts (default: 3)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            monitor_service_with_notification(
                service_name=args.service,
                check_interval=args.interval,
                auto_recover=args.auto_recover,
                max_recovery_attempts=args.max_retries,
            )
        )
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

### Running the Monitor

```bash
# Monitor nginx, check every 30 seconds
python3 /opt/autobot/scripts/service_failure_monitor.py \
    --service nginx --interval 30

# Monitor the backend with auto-recovery enabled
python3 /opt/autobot/scripts/service_failure_monitor.py \
    --service autobot-backend --interval 15 --auto-recover --max-retries 5

# Monitor Redis on the database VM
python3 /opt/autobot/scripts/service_failure_monitor.py \
    --service redis-server --interval 10
```

---

## 7. Continuous Monitoring Setup

### Running as a systemd Service

Create a systemd unit file to run the service monitor as a persistent daemon:

```ini
# /etc/systemd/system/autobot-service-monitor.service
[Unit]
Description=AutoBot Service Failure Monitor
Documentation=https://github.com/mrveiss/AutoBot-AI
After=network.target redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=autobot
Group=autobot
WorkingDirectory=/opt/autobot
Environment=PYTHONPATH=/opt/autobot/autobot-backend:/opt/autobot/autobot_shared:/opt/autobot
ExecStart=/opt/autobot/venv/bin/python3 \
    /opt/autobot/scripts/service_failure_monitor.py \
    --service autobot-backend \
    --interval 30 \
    --auto-recover \
    --max-retries 3
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=autobot-service-monitor

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/autobot/reports /opt/autobot/logs

[Install]
WantedBy=multi-user.target
```

**Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable autobot-service-monitor.service
sudo systemctl start autobot-service-monitor.service

# Check status
sudo systemctl status autobot-service-monitor.service
journalctl -u autobot-service-monitor -f
```

### Monitoring Multiple Services with Template Units

To monitor multiple services, use a systemd template unit:

```ini
# /etc/systemd/system/autobot-monitor@.service
[Unit]
Description=AutoBot Monitor for %i
After=network.target

[Service]
Type=simple
User=autobot
Group=autobot
WorkingDirectory=/opt/autobot
Environment=PYTHONPATH=/opt/autobot/autobot-backend:/opt/autobot/autobot_shared:/opt/autobot
ExecStart=/opt/autobot/venv/bin/python3 \
    /opt/autobot/scripts/service_failure_monitor.py \
    --service %i \
    --interval 30 \
    --auto-recover
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable for multiple services:**

```bash
sudo systemctl enable autobot-monitor@nginx.service
sudo systemctl enable autobot-monitor@autobot-backend.service
sudo systemctl enable autobot-monitor@redis-server.service

sudo systemctl start autobot-monitor@nginx.service
sudo systemctl start autobot-monitor@autobot-backend.service
sudo systemctl start autobot-monitor@redis-server.service
```

### Using SystemMonitor for Continuous Monitoring

The built-in `SystemMonitor` class supports continuous monitoring natively:

```python
#!/usr/bin/env python3
"""Run SystemMonitor in continuous mode as a daemon."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/opt/autobot/autobot-infrastructure/shared/scripts")
from monitoring_system import SystemMonitor


async def main():
    monitor = SystemMonitor(project_root=Path("/opt/autobot"))

    # Override defaults if needed
    monitor.config["collection_interval"] = 30
    monitor.config["alert_thresholds"]["cpu_usage"] = 75

    # Runs indefinitely: collects metrics, checks health,
    # generates dashboards, cleans up old data at 2 AM
    await monitor.start_monitoring(continuous=True)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. WebSocket Real-Time Event Stream

### Live Events WebSocket Protocol

AutoBot uses the `LiveEventManager` for scoped real-time event streaming. The
WebSocket endpoint is at `/ws/live` and requires JWT authentication.

**Protocol specification:**

| Direction | Message | Purpose |
|-----------|---------|---------|
| Client -> Server | `{"action": "subscribe", "channel": "global"}` | Subscribe to a channel |
| Client -> Server | `{"action": "unsubscribe", "channel": "task:abc"}` | Unsubscribe from channel |
| Client -> Server | `{"action": "ping"}` | Client keepalive |
| Server -> Client | `{"type": "connection_established", "message": "..."}` | Initial handshake |
| Server -> Client | `{"type": "subscribed", "channel": "global"}` | Subscription confirmed |
| Server -> Client | `{"type": "unsubscribed", "channel": "task:abc"}` | Unsubscription confirmed |
| Server -> Client | `{"type": "pong"}` | Pong response |
| Server -> Client | `{"type": "ping"}` | Server keepalive (every 30s) |
| Server -> Client | `{"type": "error", "message": "..."}` | Error notification |
| Server -> Client | `{"type": "live_event", ...}` | Event delivery |

**Live event payload structure:**

```json
{
    "type": "live_event",
    "channel": "global",
    "event_type": "service_failure",
    "event_id": 42,
    "payload": {
        "service": "nginx",
        "status": "failed",
        "severity": "CRITICAL",
        "message": "Service nginx has entered failed state",
        "timestamp": "2026-03-15T10:30:00",
        "node": "<frontend-ip>"
    }
}
```

### JavaScript Client Example

```javascript
// Connect to the live events WebSocket
const token = localStorage.getItem('auth_token');
const ws = new WebSocket(`wss://<backend-ip>:8443/ws/live?token=${token}`);

ws.onopen = () => {
    console.log('Connected to live events');

    // Subscribe to global alerts
    ws.send(JSON.stringify({
        action: 'subscribe',
        channel: 'global'
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case 'connection_established':
            console.log('Connection established:', data.message);
            break;

        case 'subscribed':
            console.log(`Subscribed to channel: ${data.channel}`);
            break;

        case 'live_event':
            handleLiveEvent(data);
            break;

        case 'ping':
            // Server keepalive -- no response needed
            break;

        case 'error':
            console.error('Server error:', data.message);
            break;
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
    console.log(`WebSocket closed: code=${event.code} reason=${event.reason}`);
    // Implement reconnection with exponential backoff
    setTimeout(() => reconnect(), 5000);
};

function handleLiveEvent(data) {
    const { event_type, payload, channel, event_id } = data;

    if (event_type === 'service_failure' && payload.severity === 'CRITICAL') {
        // Show a browser notification
        if (Notification.permission === 'granted') {
            new Notification('AutoBot Service Alert', {
                body: payload.message,
                icon: '/favicon.ico',
                tag: `alert-${event_id}`,
            });
        }

        // Update the UI alert panel
        addAlertToPanel({
            id: event_id,
            severity: payload.severity,
            message: payload.message,
            service: payload.service,
            timestamp: payload.timestamp,
        });
    }
}
```

### Monitoring WebSocket Dashboard

The dedicated monitoring dashboard WebSocket at `/ws/monitoring` automatically
broadcasts performance updates:

```javascript
const monitoringWs = new WebSocket('wss://<backend-ip>:8443/ws/monitoring');

monitoringWs.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'monitoring_update') {
        updateDashboard(data.data);
    }

    if (data.type === 'performance_alerts') {
        data.data.forEach(alert => {
            showAlertBanner(alert);
        });
    }
};

// Change update interval (0.5-30 seconds)
monitoringWs.send(JSON.stringify({
    type: 'command',
    command: 'set_interval',
    interval: 5.0
}));
```

### Vue.js Integration

```typescript
// Example usage in a Vue component
import { ref, onMounted, onUnmounted } from 'vue'

interface Alert {
    service: string
    severity: string
    message: string
    timestamp: string
}

export function useServiceAlerts() {
    const alerts = ref<Alert[]>([])
    let ws: WebSocket | null = null

    function connect() {
        const token = localStorage.getItem('auth_token')
        ws = new WebSocket(
            `wss://${window.location.host}/ws/live?token=${token}`
        )

        ws.onopen = () => {
            ws?.send(JSON.stringify({
                action: 'subscribe',
                channel: 'global'
            }))
        }

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data)
            if (
                data.type === 'live_event'
                && data.event_type === 'service_failure'
            ) {
                alerts.value.unshift(data.payload)
                if (alerts.value.length > 50) {
                    alerts.value = alerts.value.slice(0, 50)
                }
            }
        }

        ws.onclose = () => {
            setTimeout(connect, 5000)
        }
    }

    onMounted(() => connect())
    onUnmounted(() => ws?.close())

    return { alerts }
}
```

---

## 9. Prometheus Integration

### Metrics Architecture

AutoBot uses the `PrometheusMetricsManager` singleton to expose metrics to
Prometheus. The manager delegates to domain-specific recorders, each handling a
set of related metrics.

**Service health metrics** (from `ServiceHealthMetricsRecorder`):

```python
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

metrics = get_metrics_manager()

# Record service health score (0-100 gauge)
metrics.update_service_health("nginx", 100.0)      # healthy
metrics.update_service_health("nginx", 0.0)         # down

# Record service response time (histogram with buckets)
# Buckets: 10ms, 50ms, 100ms, 500ms, 1s, 2s, 5s, 10s
metrics.record_service_response_time("backend", 0.045)  # 45ms

# Update service status gauge (0=offline, 1=online, 2=degraded)
metrics.update_service_status("redis", "healthy")   # sets gauge to 1
metrics.update_service_status("redis", "offline")   # sets gauge to 0
metrics.update_service_status("redis", "degraded")  # sets gauge to 2
```

**Status value mapping** (from `ServiceHealthMetricsRecorder`):

```python
_SERVICE_STATUS_VALUES = {
    "offline": 0, "error": 0, "critical": 0,   # down states
    "online": 1, "healthy": 1, "up": 1,         # healthy states
    "warning": 2, "degraded": 2,                 # degraded states
}
```

**System metrics:**

```python
metrics.update_system_cpu(23.4)
metrics.update_system_memory(67.2)
metrics.update_system_disk("/", 45.1)
metrics.record_network_bytes("sent", 1048576)
metrics.record_network_bytes("recv", 2097152)
```

**Error metrics:**

```python
metrics.record_error("network", "ai_stack_client", "CONNECTION_REFUSED")
metrics.update_error_rate("redis", "1m", 0.05)
```

### Key Prometheus Metric Definitions

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `autobot_service_health_score` | Gauge | `service_name` | Health score 0-100 |
| `autobot_service_response_time_seconds` | Histogram | `service_name` | Response time (buckets: 10ms-10s) |
| `autobot_service_status` | Gauge | `service_name`, `status` | Status code (0/1/2) |
| `autobot_cpu_usage_percent` | Gauge | -- | CPU utilization percentage |
| `autobot_memory_usage_percent` | Gauge | -- | Memory utilization percentage |
| `autobot_disk_usage_percent` | Gauge | `mount_point` | Disk utilization percentage |
| `autobot_errors_total` | Counter | `category`, `component`, `error_code` | Total error count |
| `autobot_error_rate` | Gauge | `component`, `time_window` | Error rate per window |
| `autobot_circuit_breaker_state` | Gauge | `database` | 0=closed, 1=open, 2=half_open |
| `autobot_circuit_breaker_failure_count` | Gauge | `database` | Current failure count |
| `autobot_redis_server_available` | Gauge | `database` | 0=down, 1=up |
| `autobot_timeout_total` | Counter | `operation_type`, `database`, `status` | Timeout events |
| `autobot_operation_duration_seconds` | Histogram | `operation_type`, `database` | Operation latency |

### Prometheus Configuration

Add the AutoBot backend as a scrape target:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'autobot-backend'
    scheme: https
    tls_config:
      insecure_skip_verify: true
    static_configs:
      - targets: ['<backend-ip>:8443']
    metrics_path: '/metrics'
    scrape_interval: 15s

  - job_name: 'node'
    static_configs:
      - targets:
        - '<backend-ip>:9100'
        - '<frontend-ip>:9100'
        - '<npu-ip>:9100'
        - '<database-ip>:9100'
        - '<aiml-ip>:9100'
        - '<browser-ip>:9100'
```

### AlertManager Configuration

Route alerts to the AutoBot webhook:

```yaml
# alertmanager.yml
route:
  receiver: 'autobot-webhook'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: 'autobot-webhook'
      group_wait: 10s
      repeat_interval: 1h

receivers:
  - name: 'autobot-webhook'
    webhook_configs:
      - url: 'https://<backend-ip>:8443/api/webhook/alertmanager'
        tls_config:
          insecure_skip_verify: true
        send_resolved: true
```

### Querying Metrics via the Prometheus MCP Bridge

AutoBot's LLM agents can query Prometheus metrics through the MCP bridge API:

```bash
# Get current system metrics across all VMs
curl -sk -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    https://<backend-ip>:8443/api/prometheus/mcp/get_system_metrics

# Query a specific metric
curl -sk -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "autobot_service_health_score"}' \
    https://<backend-ip>:8443/api/prometheus/mcp/query_metric

# Get service health status
curl -sk -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    https://<backend-ip>:8443/api/prometheus/mcp/get_service_health

# Get metrics for a specific VM
curl -sk -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"vm_ip": "<database-ip>"}' \
    https://<backend-ip>:8443/api/prometheus/mcp/get_vm_metrics

# List all available metrics
curl -sk -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"filter": "autobot_service"}' \
    https://<backend-ip>:8443/api/prometheus/mcp/list_available_metrics
```

### Grafana Dashboard Integration

Prometheus metrics are visualized in Grafana (hosted on the Redis VM .23). Key
dashboard panels for service monitoring:

```
Service Health Overview Panel:
  Query: autobot_service_health_score
  Visualization: Gauge (0-100)
  Thresholds: 0-50 red, 50-80 yellow, 80-100 green

Service Status Panel:
  Query: autobot_service_status
  Visualization: State timeline
  Value mappings: 0="Offline" red, 1="Online" green, 2="Degraded" yellow

Response Time Panel:
  Query: histogram_quantile(0.95,
           rate(autobot_service_response_time_seconds_bucket[5m]))
  Visualization: Time series graph

Error Rate Panel:
  Query: rate(autobot_errors_total[5m])
  Visualization: Time series with threshold line at 10
```

---

## 10. Troubleshooting

### Common Issues and Solutions

#### 1. Health check endpoint returns `"status": "degraded"`

**Symptom:** `GET /api/system/health` returns `degraded` status.

**Diagnosis:**

```bash
# Check detailed health to identify which component is degraded
curl -sk -H "Authorization: Bearer $TOKEN" \
    https://<backend-ip>:8443/api/system/health/detailed | python3 -m json.tool

# Look for components with "error" in their status
```

**Common causes:**
- Redis is unreachable: Check `systemctl status redis-server` on VM .23
- Conversation files DB not initialized: Backend startup still in progress
  (takes approximately 6 minutes)
- Config error: Check `/opt/autobot/.env` for correct SSOT settings

#### 2. WebSocket connection rejected with code 4001

**Symptom:** Live events WebSocket closes immediately with `code=4001`.

**Cause:** Invalid or expired JWT token.

**Fix:**

```bash
# Get a fresh token
TOKEN=$(curl -sk -X POST \
    https://<backend-ip>:8443/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "..."}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Use the token in the WebSocket URL
wscat -c "wss://<backend-ip>:8443/ws/live?token=$TOKEN" --no-check
```

#### 3. Alerts not appearing in the monitoring dashboard

**Diagnosis path:**

```bash
# 1. Check if Prometheus is scraping the backend
curl -s http://<backend-ip>:9090/api/v1/targets \
    | python3 -m json.tool | grep autobot

# 2. Check if AlertManager is receiving alerts
curl -s http://<backend-ip>:9093/api/v2/alerts | python3 -m json.tool

# 3. Check the webhook endpoint health
curl -sk https://<backend-ip>:8443/api/webhook/alertmanager/health

# 4. Check if WebSocket manager has connected clients
# (visible in backend logs)
journalctl -u autobot-backend --since "5 minutes ago" | grep -i websocket
```

#### 4. `systemctl` commands fail with "No such file or directory"

**Cause:** The monitoring script is running in a container or non-systemd
environment.

**Fix:** The `HealthCollector.check_service()` method catches `FileNotFoundError`
and returns `{"active": False, "status": "systemctl_not_found"}`. For container
environments, use HTTP health checks instead:

```python
# Use SystemMonitor's HTTP health check instead of systemctl
monitor = SystemMonitor()
health = await monitor.perform_health_checks()
```

#### 5. SQLite metrics database grows too large

**Cause:** Automatic cleanup is not running (continuous monitoring not in use,
or the 2 AM window was missed).

**Fix:**

```python
from monitoring_system import SystemMonitor
monitor = SystemMonitor()
monitor.cleanup_old_metrics()  # Manual cleanup
```

Or via cron:

```bash
# Run cleanup daily at 2 AM
0 2 * * * cd /opt/autobot && python3 -c "
import sys; sys.path.insert(0, 'autobot-infrastructure/shared/scripts')
from monitoring_system import SystemMonitor
SystemMonitor().cleanup_old_metrics()
"
```

#### 6. Redis pub/sub alerts not delivered

**Diagnosis:**

```bash
# Check Redis connectivity
redis-cli -h <database-ip> -p 6379 ping

# Monitor the alert channel in real time
redis-cli -h <database-ip> subscribe system_alerts

# From another terminal, publish a test alert
redis-cli -h <database-ip> publish system_alerts '{"type":"test","message":"ping"}'
```

**Common causes:**
- Redis server down on VM .23
- Network firewall blocking port 6379
- Wrong Redis database selected (alerts use `database="main"`)

#### 7. Prometheus metrics not updating

**Diagnosis:**

```bash
# Check if metrics endpoint is responding
curl -sk https://<backend-ip>:8443/metrics | head -20

# Check for autobot-specific metrics
curl -sk https://<backend-ip>:8443/metrics | grep autobot_service

# Verify Prometheus can reach the backend
curl -s http://<backend-ip>:9090/api/v1/targets \
    | python3 -c "
import sys, json
targets = json.load(sys.stdin)['data']['activeTargets']
for t in targets:
    print(t['labels']['job'], t['health'])
"
```

#### 8. Monitor systemd unit keeps restarting

**Diagnosis:**

```bash
# Check the journal for the specific monitor unit
journalctl -u autobot-service-monitor --since "10 minutes ago" --no-pager
```

**Common causes and fixes:**
- `ImportError: autobot_shared not found` -- Ensure `PYTHONPATH` in the unit
  file includes `/opt/autobot/autobot_shared`
- `ConnectionRefusedError` -- Redis on .23 not reachable; the monitor will retry
  on next interval automatically
- `PermissionError` -- Ensure `ReadWritePaths` includes the reports directory
  and the `autobot` user owns it

#### 9. HealthCollector discovers phantom services

**Symptom:** `discovered_services` includes services with `load_state: "not-found"`
or `load_state: "masked"`.

**Fix:** This is already handled. The `_parse_service_line()` method filters out
entries with `load_state` of `not-found` or `masked`. If you still see unexpected
services, they have valid unit files but may be stopped/failed.

#### 10. Backend returns 502 after restart

**Cause:** Normal behavior. The backend takes approximately 6 minutes to fully
initialize. During this time, health checks may return `degraded` or `unhealthy`.

**Fix:** Wait for initialization to complete. Monitor with:

```bash
# Watch health status until it becomes "healthy"
watch -n 5 'curl -sk https://<backend-ip>:8443/api/system/health 2>/dev/null \
    | python3 -m json.tool 2>/dev/null || echo "Not ready yet"'
```

### Diagnostic Commands Quick Reference

```bash
# Check all failed services on current node
systemctl list-units --type=service --state=failed --no-pager

# Check backend health
curl -sk https://<backend-ip>:8443/api/system/health | python3 -m json.tool

# Check SLM fleet health (requires auth)
curl -sk -H "Authorization: Bearer $SLM_TOKEN" \
    https://<slm-manager-ip>:8000/api/roles/fleet-health | python3 -m json.tool

# Check recent errors
curl -sk "https://<backend-ip>:8443/api/error-monitoring/recent?limit=5" \
    | python3 -m json.tool

# Check Prometheus alert rules
curl -s http://<backend-ip>:9090/api/v1/rules | python3 -m json.tool

# Check firing alerts
curl -s http://<backend-ip>:9093/api/v2/alerts | python3 -m json.tool

# Monitor backend logs for alerts in real time
journalctl -u autobot-backend -f | grep -i "alert\|CRITICAL\|failed"

# Check latest monitoring dashboard data
ls -lt /opt/autobot/reports/monitoring/dashboard_*.json | head -5

# Query SQLite alerts directly
sqlite3 /opt/autobot/reports/monitoring/metrics.db \
    "SELECT datetime(timestamp), severity, message
     FROM alerts ORDER BY timestamp DESC LIMIT 10;"
```

---

## Related Documentation

- [Advanced Monitoring System](../architecture/Advanced_Monitoring_System.md) --
  Architecture design document
- [WebSocket Integration Guide](../api/WEBSOCKET_INTEGRATION_GUIDE.md) --
  WebSocket API reference
- [Redis Service Management](../api/REDIS_SERVICE_MANAGEMENT_API.md) --
  Redis operations and pub/sub
- [Comprehensive Troubleshooting Guide](../troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md) --
  Full troubleshooting reference

---

**Source files referenced in this guide:**

| File | Purpose |
|------|---------|
| `autobot-infrastructure/shared/scripts/monitoring_system.py` | `SystemMonitor` class |
| `autobot-slm-backend/slm/agent/health_collector.py` | `HealthCollector` for systemd service monitoring |
| `autobot_shared/monitoring/prometheus_metrics.py` | `PrometheusMetricsManager` singleton |
| `autobot_shared/monitoring/metrics/service_health.py` | `ServiceHealthMetricsRecorder` |
| `autobot-backend/api/system.py` | `/api/system/health` and `/api/system/metrics` endpoints |
| `autobot-backend/api/error_monitoring.py` | Error monitoring REST API |
| `autobot-backend/api/monitoring.py` | `MonitoringWebSocketManager` and dashboard endpoints |
| `autobot-backend/api/alertmanager_webhook.py` | AlertManager webhook receiver |
| `autobot-backend/api/prometheus_mcp.py` | Prometheus MCP bridge for LLM agents |
| `autobot-backend/live_event_manager.py` | `LiveEventManager` channel-based pub/sub |
| `autobot-backend/api/live_events.py` | `/ws/live` WebSocket endpoint |
| `autobot-infrastructure/shared/config/prometheus/alertmanager_rules.yml` | Alert rule definitions |
