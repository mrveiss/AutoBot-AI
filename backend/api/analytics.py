# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Backend Analytics API Controller for AutoBot
Provides comprehensive analytics endpoints for the monitoring dashboard
Supports real-time analytics, communication patterns, and code analysis integration
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

# Import models from dedicated module (Issue #185 - split oversized files)
from backend.api.analytics_models import (
    AnalyticsOverview,
    RealTimeEvent,
)
from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import TimingConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import RedisDatabase

# Import existing monitoring infrastructure (extracted to monitoring_hardware.py - Issue #213)
from .monitoring_hardware import hardware_monitor

# Import controller class (extracted from this file - Issue #212)
from backend.api.analytics_controller import (
    analytics_controller,
    analytics_state,
    get_service_address,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

# Module-level constants for O(1) lookups (Issue #326)
ANALYTICS_REDIS_DATABASES = {RedisDatabase.METRICS, RedisDatabase.KNOWLEDGE, RedisDatabase.MAIN}


# ============================================================================
# DASHBOARD OVERVIEW ENDPOINTS
# ============================================================================


def _handle_task_exception(result: Any, name: str) -> Any:
    """Handle exception from asyncio task (Issue #398: extracted)."""
    return {"error": str(result)} if isinstance(result, Exception) else result


async def _get_realtime_metrics() -> Dict[str, Any]:
    """Get real-time metrics from monitoring (Issue #398: extracted)."""
    try:
        current_metrics = await analytics_controller.metrics_collector.collect_all_metrics()
        return {
            name: {"value": metric.value, "unit": metric.unit, "category": metric.category}
            for name, metric in current_metrics.items()
        }
    except Exception as e:
        return {"error": str(e)}


async def _get_code_analysis_status() -> Dict[str, Any]:
    """Get code analysis tool status (Issue #398: extracted)."""
    code_analysis_exists = await asyncio.to_thread(analytics_controller.code_analysis_path.exists)
    code_index_exists = await asyncio.to_thread(analytics_controller.code_index_path.exists)
    return {
        "last_analysis": analytics_state.get("last_analysis_time"),
        "cache_available": bool(analytics_state.get("code_analysis_cache")),
        "tools_available": {"code_analysis_suite": code_analysis_exists, "code_index_mcp": code_index_exists},
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_overview",
    error_code_prefix="ANALYTICS",
)
@router.get("/dashboard/overview", response_model=AnalyticsOverview)
async def get_dashboard_overview():
    """Get comprehensive dashboard overview (Issue #398: refactored)."""
    timestamp = datetime.now().isoformat()

    results = await asyncio.gather(
        hardware_monitor.get_system_health(),
        analytics_controller.collect_performance_metrics(),
        analytics_controller.analyze_communication_patterns(),
        analytics_controller.get_usage_statistics(),
        analytics_controller.detect_trends(),
        return_exceptions=True,
    )

    system_health = _handle_task_exception(results[0], "system_health")
    performance_metrics = _handle_task_exception(results[1], "performance")
    communication_patterns = _handle_task_exception(results[2], "communication")
    usage_statistics = _handle_task_exception(results[3], "usage")
    trends = _handle_task_exception(results[4], "trends")

    return AnalyticsOverview(
        timestamp=timestamp, system_health=system_health, performance_metrics=performance_metrics,
        communication_patterns=communication_patterns, code_analysis_status=await _get_code_analysis_status(),
        usage_statistics=usage_statistics, realtime_metrics=await _get_realtime_metrics(), trends=trends,
    )


async def _check_redis_db(db) -> Tuple[str, str]:
    """Check connectivity for a single Redis database (Issue #398: extracted)."""
    try:
        redis_conn = await analytics_controller.get_redis_connection(db)
        if redis_conn:
            await redis_conn.ping()
            return db.name, "connected"
        return db.name, "failed"
    except Exception as e:
        return db.name, f"error: {str(e)}"


async def _check_service(
    client, service_name: str, service_url: str
) -> Tuple[str, Dict[str, Any]]:
    """Check connectivity for a single service (Issue #398: extracted)."""
    try:
        start_time = time.time()
        response = await client.get(f"{service_url}/health")
        response_time = time.time() - start_time
        return service_name, {
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "response_time": response_time,
            "status_code": response.status_code,
        }
    except Exception as e:
        return service_name, {"status": "unreachable", "error": str(e)}


def _check_resource_alerts(system_resources: Dict) -> List[Dict[str, Any]]:
    """Generate resource alerts based on thresholds (Issue #398: extracted).

    Issue #596: Fixed key names to match hardware_monitor.get_system_resources() output.
    - CPU key: usage_percent (not percent_overall)
    - Memory key: usage_percent (not percent)
    """
    alerts = []

    # Issue #596: Use .get() with defaults to prevent KeyError
    cpu_data = system_resources.get("cpu", {})
    cpu_usage = cpu_data.get("usage_percent", 0)
    if cpu_usage > 90:
        alerts.append({
            "type": "cpu_high",
            "message": f"CPU usage at {cpu_usage:.1f}%",
            "severity": "warning",
        })

    memory_data = system_resources.get("memory", {})
    memory_usage = memory_data.get("usage_percent", 0)
    if memory_usage > 90:
        alerts.append({
            "type": "memory_high",
            "message": f"Memory usage at {memory_usage:.1f}%",
            "severity": "warning",
        })

    return alerts


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_system_health",
    error_code_prefix="ANALYTICS",
)
@router.get("/system/health-detailed")
async def get_detailed_system_health():
    """Get detailed system health with enhanced analytics (Issue #398: refactored)."""
    base_health = await hardware_monitor.get_system_health()

    detailed_health = {
        "base_health": base_health,
        "analytics_health": {
            "api_tracking_active": len(analytics_state["api_call_patterns"]) > 0,
            "websocket_connections": len(analytics_state["websocket_connections"]),
            "performance_tracking": len(analytics_state["performance_history"]) > 0,
            "redis_connectivity": {},
        },
        "service_connectivity": {},
        "resource_alerts": [],
    }

    # Issue #370: Check Redis connectivity for all databases in parallel
    redis_results = await asyncio.gather(
        *[_check_redis_db(db) for db in RedisDatabase],
        return_exceptions=True
    )
    for result in redis_results:
        if isinstance(result, Exception):
            continue
        db_name, status = result
        detailed_health["analytics_health"]["redis_connectivity"][db_name] = status

    # Issue #370: Check service connectivity in parallel
    services = {
        "ollama": get_service_address("ollama", NetworkConstants.OLLAMA_PORT),
        "frontend": get_service_address("frontend", NetworkConstants.FRONTEND_PORT),
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        service_results = await asyncio.gather(
            *[_check_service(client, name, url) for name, url in services.items()],
            return_exceptions=True
        )
        for result in service_results:
            if isinstance(result, Exception):
                continue
            service_name, status = result
            detailed_health["service_connectivity"][service_name] = status
        detailed_health["service_connectivity"]["redis"] = "checked_via_redis"

    # Resource alerts using helper (Issue #430: await async)
    system_resources = await hardware_monitor.get_system_resources()
    detailed_health["resource_alerts"] = _check_resource_alerts(system_resources)

    return detailed_health


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_metrics",
    error_code_prefix="ANALYTICS",
)
@router.get("/performance/metrics")
async def get_performance_metrics():
    """Get comprehensive performance metrics"""
    metrics = await analytics_controller.collect_performance_metrics()

    # Add historical context
    if analytics_state["performance_history"]:
        recent_history = list(analytics_state["performance_history"])[-10:]
        metrics["historical_context"] = {
            "samples_count": len(recent_history),
            "avg_cpu_last_10": (
                sum(h.get("cpu_percent", 0) for h in recent_history)
                / len(recent_history)
            ),
            "avg_memory_last_10": (
                sum(h.get("memory_percent", 0) for h in recent_history)
                / len(recent_history)
            ),
        }

    # Store current metrics in history
    current_snapshot = {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": metrics.get("system_performance", {}).get("cpu_percent", 0),
        "memory_percent": (
            metrics.get("system_performance", {}).get("memory_percent", 0)
        ),
        "gpu_utilization": (
            metrics.get("hardware_performance", {}).get("gpu_utilization", 0)
        ),
    }
    analytics_state["performance_history"].append(current_snapshot)

    return metrics


# ============================================================================
# COMMUNICATION PATTERN ANALYSIS ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_communication_patterns",
    error_code_prefix="ANALYTICS",
)
@router.get("/communication/patterns")
async def get_communication_patterns():
    """Get detailed communication pattern analysis"""
    patterns = await analytics_controller.analyze_communication_patterns()

    # Add additional analysis
    patterns["analysis_timestamp"] = datetime.now().isoformat()
    patterns["pattern_insights"] = []

    # Analyze for insights
    if patterns["api_patterns"]:
        # Find high-frequency, high-latency endpoints
        high_latency_endpoints = [
            p
            for p in patterns["api_patterns"]
            if p["avg_response_time"] > 1.0 and p["frequency"] > 10
        ]

        if high_latency_endpoints:
            patterns["pattern_insights"].append(
                {
                    "type": "performance_concern",
                    "message": (
                        f"Found {len(high_latency_endpoints)} high-frequency endpoints with high latency"
                    ),
                    "details": high_latency_endpoints[:3],  # Show top 3
                }
            )

        # Find endpoints with high error rates
        high_error_endpoints = [
            p for p in patterns["api_patterns"] if p["error_rate"] > 5.0
        ]

        if high_error_endpoints:
            patterns["pattern_insights"].append(
                {
                    "type": "reliability_concern",
                    "message": (
                        f"Found {len(high_error_endpoints)} endpoints with high error rates"
                    ),
                    "details": high_error_endpoints[:3],
                }
            )

    return patterns


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_usage_statistics",
    error_code_prefix="ANALYTICS",
)
@router.get("/usage/statistics")
async def get_usage_statistics():
    """Get comprehensive usage statistics"""
    stats = await analytics_controller.get_usage_statistics()

    # Add time-based analysis
    stats["analysis_period"] = {
        "start_time": analytics_state.get("session_start", datetime.now().isoformat()),
        "current_time": datetime.now().isoformat(),
        "data_points": len(analytics_state["api_call_patterns"]),
    }

    return stats


# ============================================================================
# IMPORT SUB-ROUTERS FROM SPLIT MODULES
# ============================================================================

# Import code analysis router (split to maintain <20 functions)
# NOTE: analytics_monitoring.py removed in Issue #532 - monitoring endpoints consolidated in monitoring.py
from backend.api import analytics_code

# Import new analytics modules (Issue #59 - Advanced Analytics & BI)
from backend.api import analytics_cost, analytics_agents, analytics_export, analytics_behavior

# Include sub-routers
router.include_router(analytics_code.router)

# Include Issue #59 sub-routers (Advanced Analytics & BI)
router.include_router(analytics_cost.router)
router.include_router(analytics_agents.router)
router.include_router(analytics_export.router)
router.include_router(analytics_behavior.router)

# Set dependencies for sub-modules
analytics_code.set_analytics_dependencies(analytics_controller, analytics_state)

# ============================================================================
# CODE ANALYSIS INTEGRATION ENDPOINTS (MOVED TO analytics_code.py)
# ============================================================================

# The following functions have been moved to analytics_code.py:
# - index_codebase
# - get_code_analysis_status
# - get_code_quality_assessment
# - get_code_quality_metrics
# - get_communication_chains
# - analyze_communication_chains_detailed
# - get_code_quality_score


# Code analysis endpoints have been moved to analytics_code.py


# ============================================================================
# REAL-TIME ANALYTICS ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_realtime_metrics",
    error_code_prefix="ANALYTICS",
)
@router.get("/realtime/metrics")
async def get_realtime_metrics():
    """Get current real-time metrics snapshot"""
    # Issue #619: Parallelize independent metrics collection
    current_metrics, system_resources = await asyncio.gather(
        analytics_controller.metrics_collector.collect_all_metrics(),
        hardware_monitor.get_system_resources(),
    )

    realtime_data = {
        "timestamp": datetime.now().isoformat(),
        "system_metrics": {
            name: {
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
                "metadata": metric.metadata,
            }
            for name, metric in current_metrics.items()
        },
        "system_resources": system_resources,
        "active_connections": len(analytics_state["websocket_connections"]),
        "recent_api_calls": len(
            [
                call
                for call in analytics_state["api_call_patterns"]
                if datetime.fromisoformat(call["timestamp"])
                > datetime.now() - timedelta(minutes=1)
            ]
        ),
        # Issue #596: Fixed key names to match hardware_monitor.get_system_resources() output
        "performance_snapshot": {
            "cpu_percent": system_resources.get("cpu", {}).get("usage_percent", 0),
            "memory_percent": system_resources.get("memory", {}).get("usage_percent", 0),
            "disk_percent": system_resources.get("disk", {}).get("usage_percent", 0),
        },
    }

    return realtime_data


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="track_analytics_event",
    error_code_prefix="ANALYTICS",
)
@router.post("/events/track")
async def track_analytics_event(event: RealTimeEvent):
    """Track a real-time analytics event"""
    # Store event in analytics state
    event_data = event.dict()
    event_data["processed_at"] = datetime.now().isoformat()

    # Store in Redis for persistence
    redis_conn = await analytics_controller.get_redis_connection(RedisDatabase.METRICS)
    if redis_conn:
        await redis_conn.lpush("analytics:events", json.dumps(event_data))
        await redis_conn.ltrim("analytics:events", 0, 9999)  # Keep last 10k events

    # Update tracking based on event type
    if event.event_type == "api_call":
        endpoint = event.data.get("endpoint", "unknown")
        response_time = event.data.get("response_time", 0)
        status_code = event.data.get("status_code", 200)
        await analytics_controller.track_api_call(endpoint, response_time, status_code)

    elif event.event_type == "websocket_activity":
        activity_type = event.data.get("activity_type", "unknown")
        analytics_controller.websocket_activity[activity_type] += 1

    # Broadcast to connected WebSocket clients
    if analytics_state["websocket_connections"]:
        broadcast_data = {"type": "analytics_event", "event": event_data}
        disconnected = set()

        for websocket in analytics_state["websocket_connections"]:
            try:
                await websocket.send_json(broadcast_data)
            except Exception as e:
                logger.debug("WebSocket send failed: %s", e)
                disconnected.add(websocket)

        # Clean up disconnected WebSockets
        analytics_state["websocket_connections"] -= disconnected

    return {
        "status": "tracked",
        "event_id": f"{event.event_type}_{event.timestamp}",
        "broadcast_count": len(analytics_state["websocket_connections"]),
    }


def _parse_historical_calls(api_calls: list, cutoff_time: datetime) -> list:
    """Parse and filter historical API calls. (Issue #315 - extracted)

    Args:
        api_calls: Raw API call JSON strings from Redis
        cutoff_time: Only include calls after this time

    Returns:
        List of parsed call data within time window
    """
    historical_calls = []
    for call_json in api_calls:
        try:
            call_data = json.loads(call_json)
            call_time = datetime.fromisoformat(call_data["timestamp"])
            if call_time > cutoff_time:
                historical_calls.append(call_data)
        except Exception as e:
            logger.debug("Failed to parse historical call data: %s", e)
            continue
    return historical_calls


def _compute_hourly_stats(historical_calls: list) -> dict:
    """Compute hourly statistics from historical calls. (Issue #315 - extracted)

    Args:
        historical_calls: List of call data dictionaries

    Returns:
        Dictionary of hourly statistics with averages computed
    """
    hourly_stats = defaultdict(
        lambda: {"calls": 0, "avg_response_time": 0, "errors": 0}
    )

    for call in historical_calls:
        hour_key = call["timestamp"][:13]  # YYYY-MM-DDTHH
        hourly_stats[hour_key]["calls"] += 1
        hourly_stats[hour_key]["avg_response_time"] += call["response_time"]
        if call["status_code"] >= 400:
            hourly_stats[hour_key]["errors"] += 1

    # Calculate averages
    for hour_data in hourly_stats.values():
        if hour_data["calls"] > 0:
            hour_data["avg_response_time"] /= hour_data["calls"]
            hour_data["error_rate"] = (
                hour_data["errors"] / hour_data["calls"] * 100
            )

    return dict(hourly_stats)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_historical_trends",
    error_code_prefix="ANALYTICS",
)
@router.get("/trends/historical")
async def get_historical_trends(
    hours: int = Query(24, description="Number of hours to analyze", ge=1, le=168)
):
    """Get historical trend analysis"""
    trends = await analytics_controller.detect_trends()

    # Enhance with Redis historical data
    redis_conn = await analytics_controller.get_redis_connection(RedisDatabase.METRICS)
    historical_data = {"trends": trends}

    if not redis_conn:
        return historical_data

    try:
        # Get historical API calls (Issue #315 - refactored to reduce nesting)
        cutoff_time = datetime.now() - timedelta(hours=hours)
        api_calls = await redis_conn.lrange("analytics:api_calls", 0, -1)

        historical_calls = _parse_historical_calls(api_calls, cutoff_time)

        # Analyze historical patterns
        if historical_calls:
            hourly_patterns = _compute_hourly_stats(historical_calls)
            historical_data["hourly_patterns"] = hourly_patterns
            historical_data["analysis_period_hours"] = hours
            historical_data["total_historical_calls"] = len(historical_calls)

    except Exception as e:
        historical_data["redis_error"] = str(e)

    return historical_data


# ============================================================================
# WEBSOCKET REAL-TIME ANALYTICS STREAMING
# ============================================================================


async def _send_periodic_update_or_break(websocket: WebSocket) -> bool:
    """Send periodic update to WebSocket client. (Issue #315 - extracted)

    Returns:
        True to continue loop, False to break
    """
    try:
        current_data = await get_realtime_metrics()
        await websocket.send_json(_build_periodic_update(current_data))
        return True
    except Exception as e:
        logger.error("Failed to send periodic update: %s", e)
        return False


async def _handle_websocket_message_or_timeout(websocket: WebSocket) -> bool:
    """Handle WebSocket message or timeout with periodic update. (Issue #315 - extracted)

    Returns:
        True to continue loop, False to break
    """
    try:
        message = await asyncio.wait_for(
            websocket.receive_text(), timeout=10.0
        )
        await _handle_realtime_client_command(websocket, message)
        return True
    except asyncio.TimeoutError:
        return await _send_periodic_update_or_break(websocket)


async def _realtime_loop_iteration(websocket: WebSocket) -> tuple[bool, bool]:
    """Execute one iteration of the realtime analytics loop. (Issue #315 - extracted)

    Returns:
        Tuple of (should_continue, had_disconnect)
    """
    try:
        should_continue = await _handle_websocket_message_or_timeout(websocket)
        return should_continue, False
    except WebSocketDisconnect:
        logger.info("Analytics WebSocket client disconnected")
        return False, True
    except Exception as e:
        logger.error("Error in analytics WebSocket: %s", e)
        send_ok = await _send_error_safely(websocket, e)
        return send_ok, False


@router.websocket("/ws/realtime")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_realtime_analytics",
    error_code_prefix="ANALYTICS",
)
async def websocket_realtime_analytics(websocket: WebSocket):
    """WebSocket endpoint for real-time analytics streaming"""
    await websocket.accept()
    analytics_state["websocket_connections"].add(websocket)

    try:
        logger.info("Analytics WebSocket connected")

        # Send initial connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "message": "Real-time analytics streaming connected",
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Start streaming loop (Issue #315 - refactored with helper to reduce nesting)
        while True:
            should_continue, _ = await _realtime_loop_iteration(websocket)
            if not should_continue:
                break

    except Exception as e:
        logger.error("Analytics WebSocket error: %s", e)
    finally:
        analytics_state["websocket_connections"].discard(websocket)
        logger.info("Analytics WebSocket disconnected and cleaned up")


# ============================================================================
# UTILITY AND MANAGEMENT ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_analytics_collection",
    error_code_prefix="ANALYTICS",
)
@router.post("/collection/start")
async def start_analytics_collection():
    """Start continuous analytics collection"""
    # Initialize session tracking
    analytics_state["session_start"] = datetime.now().isoformat()

    # Start metrics collection
    collector = analytics_controller.metrics_collector
    if not collector._is_collecting:
        asyncio.create_task(collector.start_collection())
        # Brief delay for service startup
        await asyncio.sleep(TimingConstants.SHORT_DELAY)

    return {
        "status": "started",
        "message": "Analytics collection started successfully",
        "session_id": analytics_state["session_start"],
        "metrics_collection": collector._is_collecting,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_analytics_collection",
    error_code_prefix="ANALYTICS",
)
@router.post("/collection/stop")
async def stop_analytics_collection():
    """Stop continuous analytics collection"""
    # Stop metrics collection
    collector = analytics_controller.metrics_collector
    if collector._is_collecting:
        await collector.stop_collection()

    return {
        "status": "stopped",
        "message": "Analytics collection stopped successfully",
        "session_duration": analytics_state.get("session_start", "unknown"),
    }


def _build_analytics_status_base(collector) -> Dict[str, Any]:
    """Build base analytics status dict (Issue #398: extracted)."""
    return {
        "analytics_system": "operational",
        "timestamp": datetime.now().isoformat(),
        "collection_status": {
            "is_collecting": collector._is_collecting,
            "buffer_size": len(collector._metrics_buffer),
            "retention_hours": collector._retention_hours,
        },
        "websocket_status": {
            "active_connections": len(analytics_state["websocket_connections"]),
            "total_events_tracked": len(analytics_state["api_call_patterns"]),
        },
        "data_status": {
            "api_patterns_tracked": len(analytics_state["api_call_patterns"]),
            "performance_history_points": len(analytics_state["performance_history"]),
            "communication_chains": len(analytics_controller.communication_chains),
            "cached_code_analysis": bool(analytics_state.get("code_analysis_cache")),
        },
        "integration_status": {"redis_connectivity": {}, "code_analysis_tools": {}},
    }


async def _check_analytics_redis_connectivity() -> Dict[str, str]:
    """Check Redis connectivity for analytics databases (Issue #398: extracted)."""
    connectivity = {}
    for db in ANALYTICS_REDIS_DATABASES:
        try:
            redis_conn = await analytics_controller.get_redis_connection(db)
            if redis_conn:
                await redis_conn.ping()
                connectivity[db.name] = "connected"
            else:
                connectivity[db.name] = "failed"
        except Exception as e:
            connectivity[db.name] = f"error: {str(e)}"
    return connectivity


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_analytics_status",
    error_code_prefix="ANALYTICS",
)
@router.get("/status")
async def get_analytics_status():
    """Get comprehensive analytics system status (Issue #398: refactored)."""
    status = _build_analytics_status_base(analytics_controller.metrics_collector)
    # Issue #664: Parallelize independent async operations
    code_analysis_exists, code_index_exists, redis_connectivity = await asyncio.gather(
        asyncio.to_thread(analytics_controller.code_analysis_path.exists),
        asyncio.to_thread(analytics_controller.code_index_path.exists),
        _check_analytics_redis_connectivity(),
    )
    status["integration_status"]["code_analysis_tools"] = {
        "code_analysis_suite": code_analysis_exists,
        "code_index_mcp": code_index_exists,
    }
    status["integration_status"]["redis_connectivity"] = redis_connectivity
    return status


# ============================================================================
# PERFORMANCE MONITORING DASHBOARD ENDPOINTS (MOVED TO analytics_monitoring.py)
# ============================================================================

# The following functions have been moved to analytics_monitoring.py:
# - get_monitoring_status
# - get_dashboard_data
# - get_monitoring_alerts
# - get_analytics_optimization_recommendations
# - start_monitoring
# - stop_monitoring
# - query_metrics

# Performance monitoring endpoints have been moved to analytics_monitoring.py


# ============================================================================
# ENHANCED CODE ANALYSIS INTEGRATION (MOVED TO analytics_code.py)
# ============================================================================

# Enhanced code analysis functions moved to analytics_code.py


# ============================================================================
# ENHANCED REAL-TIME ANALYTICS
# ============================================================================


# =============================================================================
# WebSocket Message Builders (Issue #298 - Reduce Deep Nesting)
# =============================================================================


def _build_performance_message(performance_data: dict) -> dict:
    """Build performance update WebSocket message."""
    sys_perf = performance_data.get("system_performance", {})
    hw_perf = performance_data.get("hardware_performance", {})

    return {
        "type": "performance_update",
        "data": {
            "cpu_percent": sys_perf.get("cpu_percent", 0),
            "memory_percent": sys_perf.get("memory_percent", 0),
            "gpu_utilization": hw_perf.get("gpu_utilization", 0),
            "active_connections": len(analytics_state["websocket_connections"]),
        },
        "timestamp": datetime.now().isoformat(),
    }


def _build_api_activity_message(recent_calls: list) -> dict:
    """Build API activity WebSocket message."""
    return {
        "type": "api_activity",
        "data": {
            "recent_calls_count": len(recent_calls),
            "recent_calls": recent_calls[-5:],
            "total_api_calls": sum(analytics_controller.api_frequencies.values()),
        },
        "timestamp": datetime.now().isoformat(),
    }


def _build_health_message(alerts: list, critical_alerts: list) -> dict:
    """Build system health WebSocket message."""
    return {
        "type": "system_health",
        "data": {
            "alerts_count": len(alerts),
            "critical_alerts_count": len(critical_alerts),
            "critical_alerts": critical_alerts,
        },
        "timestamp": datetime.now().isoformat(),
    }


def _build_error_message(error: Exception) -> dict:
    """Build error WebSocket message."""
    return {
        "type": "error",
        "message": str(error),
        "timestamp": datetime.now().isoformat(),
    }


async def _send_error_safely(websocket: WebSocket, error: Exception) -> bool:
    """Send error message to WebSocket, return False if send failed (Issue #315)."""
    try:
        await websocket.send_json(_build_error_message(error))
        return True
    except Exception:
        return False


def _build_snapshot_response(snapshot_data: dict) -> dict:
    """Build snapshot response WebSocket message."""
    return {
        "type": "snapshot_response",
        "data": snapshot_data,
        "timestamp": datetime.now().isoformat(),
    }


def _get_recent_api_calls(cutoff_seconds: int = 10) -> list:
    """Get recent API calls within cutoff period."""
    cutoff = datetime.now() - timedelta(seconds=cutoff_seconds)
    return [
        call
        for call in analytics_state["api_call_patterns"]
        if datetime.fromisoformat(call["timestamp"]) > cutoff
    ]


async def _handle_websocket_command(websocket: WebSocket, message: str) -> None:
    """Handle incoming WebSocket command messages."""
    try:
        command = json.loads(message)
        if command.get("type") != "request_snapshot":
            return

        snapshot_data = await get_realtime_metrics()
        await websocket.send_json(_build_snapshot_response(snapshot_data))

    except json.JSONDecodeError as e:
        logger.debug("Invalid JSON in WebSocket message: %s", e)


async def _handle_realtime_client_command(websocket: WebSocket, message: str) -> None:
    """Handle client commands for realtime analytics WebSocket."""
    try:
        command = json.loads(message)
        cmd_type = command.get("type")

        if cmd_type == "subscribe":
            await websocket.send_json({
                "type": "subscription_confirmed",
                "subscribed_to": command.get("metrics", "all"),
                "timestamp": datetime.now().isoformat(),
            })
        elif cmd_type == "get_current":
            current_data = await get_realtime_metrics()
            await websocket.send_json({
                "type": "current_snapshot",
                "data": current_data,
                "timestamp": datetime.now().isoformat(),
            })

    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid JSON in client message",
            "timestamp": datetime.now().isoformat(),
        })


def _build_periodic_update(current_data: dict) -> dict:
    """Build periodic update message for realtime analytics."""
    return {
        "type": "periodic_update",
        "data": {
            "performance_snapshot": current_data.get("performance_snapshot", {}),
            "active_connections": current_data.get("active_connections", 0),
            "recent_api_calls": current_data.get("recent_api_calls", []),
        },
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# End of WebSocket Message Builders
# =============================================================================


async def _send_performance_update_if_due(
    websocket: WebSocket, current_time: float, last_update: float
) -> float:
    """Send performance update if due (every 5 seconds). (Issue #315 - extracted)

    Returns:
        Updated last_update timestamp
    """
    if current_time - last_update > 5:
        try:
            perf_data = await analytics_controller.collect_performance_metrics()
            await websocket.send_json(_build_performance_message(perf_data))
            return current_time
        except Exception as e:
            logger.error("Performance update error: %s", e)
    return last_update


async def _send_api_activity_update_if_due(
    websocket: WebSocket, current_time: float, last_update: float
) -> float:
    """Send API activity update if due (every 2 seconds). (Issue #315 - extracted)

    Returns:
        Updated last_update timestamp
    """
    if current_time - last_update > 2:
        try:
            recent_calls = _get_recent_api_calls(cutoff_seconds=10)
            await websocket.send_json(_build_api_activity_message(recent_calls))
            return current_time
        except Exception as e:
            logger.error("API activity update error: %s", e)
    return last_update


async def _send_health_update_if_due(
    websocket: WebSocket, current_time: float, last_update: float
) -> float:
    """Send system health update if due (every 10 seconds). (Issue #315 - extracted)

    Issue #69: Legacy analytics_monitoring removed. Real-time alerts now delivered
    via Prometheus AlertManager webhook (alertmanager_webhook.py -> WebSocket broadcast).

    Returns:
        Updated last_update timestamp
    """
    if current_time - last_update > 10:
        try:
            # Issue #69: Alerts now delivered via AlertManager webhook, not polled here
            alerts: list = []
            critical: list = []
            await websocket.send_json(_build_health_message(alerts, critical))
            return current_time
        except Exception as e:
            logger.error("System health update error: %s", e)
    return last_update


async def _handle_client_message_with_timeout(websocket: WebSocket) -> None:
    """Handle client message with timeout, silently continuing on timeout. (Issue #315 - extracted)"""
    try:
        message = await asyncio.wait_for(
            websocket.receive_text(), timeout=1.0
        )
        await _handle_websocket_command(websocket, message)
    except asyncio.TimeoutError:
        pass  # Continue with periodic updates


async def _live_analytics_loop_iteration(
    websocket: WebSocket,
    last_performance_update: float,
    last_api_update: float,
    last_health_update: float,
) -> tuple[bool, float, float, float]:
    """Execute one iteration of the live analytics loop. (Issue #315 - extracted)

    Returns:
        Tuple of (should_continue, last_perf_update, last_api_update, last_health_update)
    """
    try:
        current_time = time.time()

        # Send periodic updates
        last_performance_update = await _send_performance_update_if_due(
            websocket, current_time, last_performance_update
        )
        last_api_update = await _send_api_activity_update_if_due(
            websocket, current_time, last_api_update
        )
        last_health_update = await _send_health_update_if_due(
            websocket, current_time, last_health_update
        )

        # Handle client messages
        await _handle_client_message_with_timeout(websocket)

        return True, last_performance_update, last_api_update, last_health_update

    except WebSocketDisconnect:
        return False, last_performance_update, last_api_update, last_health_update
    except Exception as e:
        logger.error("Error in live analytics WebSocket: %s", e)
        send_ok = await _send_error_safely(websocket, e)
        return send_ok, last_performance_update, last_api_update, last_health_update


@router.websocket("/ws/analytics/live")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_live_analytics",
    error_code_prefix="ANALYTICS",
)
async def websocket_live_analytics(websocket: WebSocket):
    """Enhanced WebSocket endpoint for live analytics with multiple channels"""
    await websocket.accept()
    analytics_state["websocket_connections"].add(websocket)

    try:
        logger.info("Live analytics WebSocket connected")

        # Send initial connection data
        await websocket.send_json(
            {
                "type": "connection_established",
                "channels": ["performance", "api_activity", "system_health", "alerts"],
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Start streaming loop with different update frequencies (Issue #315 - refactored)
        last_performance_update = 0.0
        last_api_update = 0.0
        last_health_update = 0.0

        while True:
            (
                should_continue,
                last_performance_update,
                last_api_update,
                last_health_update,
            ) = await _live_analytics_loop_iteration(
                websocket, last_performance_update, last_api_update, last_health_update
            )
            if not should_continue:
                break

    except Exception as e:
        logger.error("Live analytics WebSocket error: %s", e)
    finally:
        analytics_state["websocket_connections"].discard(websocket)
        logger.info("Live analytics WebSocket disconnected")


# ============================================================================
# INITIALIZATION
# ============================================================================


# Initialize analytics on module load
@router.on_event("startup")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_analytics",
    error_code_prefix="ANALYTICS",
)
async def initialize_analytics():
    """Initialize analytics system on startup"""
    logger.info("Initializing Enhanced Analytics API...")

    # Initialize session
    analytics_state["session_start"] = datetime.now().isoformat()

    # Start metrics collection
    collector = analytics_controller.metrics_collector
    if hasattr(collector, "_is_collecting") and not collector._is_collecting:
        asyncio.create_task(collector.start_collection())

    logger.info("Enhanced Analytics API initialized successfully")
