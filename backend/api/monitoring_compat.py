# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring Compatibility Layer - REST API for Prometheus Metrics
Phase 4: Grafana Integration (Issue #347)

Provides backwards-compatible REST endpoints that query Prometheus
for metrics data. These endpoints are DEPRECATED and will be removed
in a future version. Use Grafana dashboards for visualization.
"""

import logging
import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics-compat"])

# Prometheus server configuration
PROMETHEUS_URL = "http://172.16.168.20:9090"

# Deprecation warning message
DEPRECATION_MSG = (
    "This endpoint is deprecated. "
    "Use Grafana dashboards at http://172.16.168.23:3000 instead. "
    "This endpoint will be removed in v3.0."
)


async def query_prometheus_instant(query: str) -> Optional[float]:
    """
    Execute an instant PromQL query and return the value.

    Args:
        query: PromQL query string

    Returns:
        Float value or None if no data
    """
    try:
        async with aiohttp.ClientSession() as session:
            params = {"query": query}
            async with session.get(
                f"{PROMETHEUS_URL}/api/v1/query", params=params, timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Prometheus query failed: {response.status}")
                    return None

                data = await response.json()
                if data.get("status") != "success":
                    return None

                results = data.get("data", {}).get("result", [])
                if not results:
                    return None

                # Return the first result value
                return float(results[0]["value"][1])

    except aiohttp.ClientError as e:
        logger.error(f"Prometheus connection error: {e}")
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"Error parsing Prometheus response: {e}")
        return None


async def query_prometheus_range(
    query: str, start: datetime, end: datetime, step: str = "15s"
) -> List[Dict[str, Any]]:
    """
    Execute a range PromQL query and return time series data.

    Args:
        query: PromQL query string
        start: Start time
        end: End time
        step: Query resolution step

    Returns:
        List of data points with timestamp and value
    """
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "query": query,
                "start": start.isoformat() + "Z",
                "end": end.isoformat() + "Z",
                "step": step,
            }
            async with session.get(
                f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=30
            ) as response:
                if response.status != 200:
                    logger.warning(f"Prometheus range query failed: {response.status}")
                    return []

                data = await response.json()
                if data.get("status") != "success":
                    return []

                results = data.get("data", {}).get("result", [])
                if not results:
                    return []

                # Format data points
                points = []
                for result in results:
                    metric = result.get("metric", {})
                    values = result.get("values", [])

                    for timestamp, value in values:
                        points.append(
                            {
                                "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                                "value": float(value),
                                "labels": metric,
                            }
                        )

                return points

    except aiohttp.ClientError as e:
        logger.error(f"Prometheus connection error: {e}")
        return []
    except (KeyError, ValueError) as e:
        logger.error(f"Error parsing Prometheus response: {e}")
        return []


@router.get("/system/current")
async def get_system_metrics_current():
    """
    DEPRECATED: Get current system metrics.
    Use Grafana dashboard 'autobot-system' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(f"Deprecated endpoint called: /metrics/system/current - {DEPRECATION_MSG}")

    cpu = await query_prometheus_instant("autobot_cpu_usage_percent")
    memory = await query_prometheus_instant("autobot_memory_usage_percent")
    disk = await query_prometheus_instant('autobot_disk_usage_percent{mount_point="/"}')
    load_1m = await query_prometheus_instant("autobot_load_average_1m")

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "system_metrics": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "disk_percent": disk,
            "load_average_1m": load_1m,
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/system/history")
async def get_system_metrics_history(
    duration: str = Query("1h", description="Time duration (e.g., 1h, 6h, 1d)"),
    step: str = Query("15s", description="Data point interval"),
):
    """
    DEPRECATED: Get historical system metrics.
    Use Grafana dashboard 'autobot-system' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(f"Deprecated endpoint called: /metrics/system/history - {DEPRECATION_MSG}")

    # Parse duration
    duration_map = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
    }

    delta = duration_map.get(duration, timedelta(hours=1))
    end = datetime.utcnow()
    start = end - delta

    cpu_history = await query_prometheus_range("autobot_cpu_usage_percent", start, end, step)
    memory_history = await query_prometheus_range(
        "autobot_memory_usage_percent", start, end, step
    )

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "cpu_history": cpu_history,
        "memory_history": memory_history,
        "time_range": {"start": start.isoformat(), "end": end.isoformat()},
    }


@router.get("/workflow/summary")
async def get_workflow_summary():
    """
    DEPRECATED: Get workflow execution summary.
    Use Grafana dashboard 'autobot-workflow' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(f"Deprecated endpoint called: /metrics/workflow/summary - {DEPRECATION_MSG}")

    total = await query_prometheus_instant("sum(autobot_workflow_executions_total)")
    completed = await query_prometheus_instant(
        'sum(autobot_workflow_executions_total{status="completed"})'
    )
    failed = await query_prometheus_instant(
        'sum(autobot_workflow_executions_total{status="failed"})'
    )
    active = await query_prometheus_instant("autobot_active_workflows")

    # Calculate success rate
    success_rate = None
    if total and total > 0:
        success_rate = (completed or 0) / total * 100

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "workflow_summary": {
            "total_executions": total,
            "completed": completed,
            "failed": failed,
            "active": active,
            "success_rate_percent": success_rate,
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/errors/recent")
async def get_recent_errors(
    limit: int = Query(20, description="Number of recent errors to return"),
):
    """
    DEPRECATED: Get recent error metrics.
    Use Grafana dashboard 'autobot-errors' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(f"Deprecated endpoint called: /metrics/errors/recent - {DEPRECATION_MSG}")

    total_errors = await query_prometheus_instant("sum(autobot_errors_total)")
    error_rate_1m = await query_prometheus_instant("rate(autobot_errors_total[1m])")
    error_rate_5m = await query_prometheus_instant("rate(autobot_errors_total[5m])")

    # Get errors by category
    end = datetime.utcnow()
    start = end - timedelta(hours=1)
    errors_by_category = await query_prometheus_range(
        "autobot_errors_total", start, end, "5m"
    )

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "error_metrics": {
            "total_errors": total_errors,
            "error_rate_1m": error_rate_1m,
            "error_rate_5m": error_rate_5m,
        },
        "errors_by_category": errors_by_category[:limit],
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/claude-api/status")
async def get_claude_api_status():
    """
    DEPRECATED: Get Claude API status.
    Use Grafana dashboard 'autobot-claude-api' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(
        f"Deprecated endpoint called: /metrics/claude-api/status - {DEPRECATION_MSG}"
    )

    rate_limit = await query_prometheus_instant("autobot_claude_api_rate_limit_remaining")
    request_rate = await query_prometheus_instant(
        "rate(autobot_claude_api_requests_total[5m]) * 60"
    )
    p95_latency = await query_prometheus_instant(
        "histogram_quantile(0.95, rate(autobot_claude_api_response_time_seconds_bucket[5m]))"
    )
    failure_rate = await query_prometheus_instant(
        'rate(autobot_claude_api_requests_total{success="false"}[5m]) / rate(autobot_claude_api_requests_total[5m])'
    )

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "claude_api_status": {
            "rate_limit_remaining": rate_limit,
            "requests_per_minute": request_rate,
            "p95_latency_seconds": p95_latency,
            "failure_rate": failure_rate,
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/services/health")
async def get_services_health():
    """
    DEPRECATED: Get service health status.
    Use Grafana dashboard 'autobot-overview' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(f"Deprecated endpoint called: /metrics/services/health - {DEPRECATION_MSG}")

    # Query service status for each service
    services = ["backend", "redis", "ollama", "npu-worker", "frontend"]
    health_data = {}

    for service in services:
        service_status = await query_prometheus_instant(
            f'autobot_service_status{{service_name="{service}",status="online"}}'
        )
        response_time = await query_prometheus_instant(
            f'autobot_service_response_time_seconds{{service_name="{service}"}}'
        )
        health_score = await query_prometheus_instant(
            f'autobot_service_health_score{{service_name="{service}"}}'
        )

        health_data[service] = {
            "online": bool(service_status and service_status == 1),
            "response_time_seconds": response_time,
            "health_score": health_score,
        }

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "services": health_data,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/github/status")
async def get_github_status():
    """
    DEPRECATED: Get GitHub API status.
    Use Grafana dashboard 'autobot-github' instead.
    """
    warnings.warn(DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    logger.warning(f"Deprecated endpoint called: /metrics/github/status - {DEPRECATION_MSG}")

    rate_limit = await query_prometheus_instant("autobot_github_api_rate_limit_remaining")
    total_ops = await query_prometheus_instant("sum(autobot_github_api_operations_total)")
    p95_latency = await query_prometheus_instant(
        "histogram_quantile(0.95, rate(autobot_github_api_duration_seconds_bucket[5m]))"
    )

    return {
        "success": True,
        "deprecated": True,
        "deprecation_message": DEPRECATION_MSG,
        "github_status": {
            "rate_limit_remaining": rate_limit,
            "total_operations": total_ops,
            "p95_latency_seconds": p95_latency,
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/health")
async def get_monitoring_compat_health():
    """
    Health check for monitoring compatibility layer.
    """
    # Check Prometheus connectivity
    try:
        cpu = await query_prometheus_instant("autobot_cpu_usage_percent")
        prometheus_healthy = cpu is not None
    except Exception:
        prometheus_healthy = False

    return {
        "status": "healthy" if prometheus_healthy else "degraded",
        "prometheus_connected": prometheus_healthy,
        "prometheus_url": PROMETHEUS_URL,
        "deprecation_notice": DEPRECATION_MSG,
        "timestamp": datetime.now().isoformat(),
    }
