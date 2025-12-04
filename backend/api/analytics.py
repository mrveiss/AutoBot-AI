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

import httpx
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

# Import models from dedicated module (Issue #185 - split oversized files)
from backend.api.analytics_models import (
    AnalyticsOverview,
    RealTimeEvent,
)
from src.constants.network_constants import NetworkConstants
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


# ============================================================================
# DASHBOARD OVERVIEW ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_overview",
    error_code_prefix="ANALYTICS",
)
@router.get("/dashboard/overview", response_model=AnalyticsOverview)
async def get_dashboard_overview():
    """Get comprehensive dashboard overview combining all analytics data"""
    timestamp = datetime.now().isoformat()

    # Collect all analytics data in parallel
    system_health_task = hardware_monitor.get_system_health()
    performance_task = analytics_controller.collect_performance_metrics()
    communication_task = analytics_controller.analyze_communication_patterns()
    usage_task = analytics_controller.get_usage_statistics()
    trends_task = analytics_controller.detect_trends()

    # Wait for all tasks to complete
    (
        system_health,
        performance_metrics,
        communication_patterns,
        usage_statistics,
        trends,
    ) = await asyncio.gather(
        system_health_task,
        performance_task,
        communication_task,
        usage_task,
        trends_task,
        return_exceptions=True,
    )

    # Handle any exceptions
    if isinstance(system_health, Exception):
        system_health = {"error": str(system_health)}
    if isinstance(performance_metrics, Exception):
        performance_metrics = {"error": str(performance_metrics)}
    if isinstance(communication_patterns, Exception):
        communication_patterns = {"error": str(communication_patterns)}
    if isinstance(usage_statistics, Exception):
        usage_statistics = {"error": str(usage_statistics)}
    if isinstance(trends, Exception):
        trends = {"error": str(trends)}

    # Get real-time metrics from existing monitoring
    realtime_metrics = {}
    try:
        current_metrics = (
            await analytics_controller.metrics_collector.collect_all_metrics()
        )
        realtime_metrics = {
            name: {
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
            }
            for name, metric in current_metrics.items()
        }
    except Exception as e:
        realtime_metrics = {"error": str(e)}

    # Code analysis status
    code_analysis_status = {
        "last_analysis": analytics_state.get("last_analysis_time"),
        "cache_available": bool(analytics_state.get("code_analysis_cache")),
        "tools_available": {
            "code_analysis_suite": analytics_controller.code_analysis_path.exists(),
            "code_index_mcp": analytics_controller.code_index_path.exists(),
        },
    }

    overview = AnalyticsOverview(
        timestamp=timestamp,
        system_health=system_health,
        performance_metrics=performance_metrics,
        communication_patterns=communication_patterns,
        code_analysis_status=code_analysis_status,
        usage_statistics=usage_statistics,
        realtime_metrics=realtime_metrics,
        trends=trends,
    )

    return overview


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_system_health",
    error_code_prefix="ANALYTICS",
)
@router.get("/system/health-detailed")
async def get_detailed_system_health():
    """Get detailed system health with enhanced analytics"""
    # Get base system health from existing monitor
    base_health = await hardware_monitor.get_system_health()

    # Add analytics-specific health checks
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

    # Check Redis connectivity for all databases
    for db in RedisDatabase:
        try:
            redis_conn = await analytics_controller.get_redis_connection(db)
            if redis_conn:
                await redis_conn.ping()
                detailed_health["analytics_health"]["redis_connectivity"][
                    db.name
                ] = "connected"
            else:
                detailed_health["analytics_health"]["redis_connectivity"][
                    db.name
                ] = "failed"
        except Exception as e:
            detailed_health["analytics_health"]["redis_connectivity"][
                db.name
            ] = f"error: {str(e)}"

    # Check service connectivity
    services = {
        "ollama": get_service_address("ollama", NetworkConstants.OLLAMA_PORT),
        "frontend": get_service_address("frontend", NetworkConstants.FRONTEND_PORT),
        "redis": get_service_address("redis", NetworkConstants.REDIS_PORT),
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        for service_name, service_url in services.items():
            try:
                if service_name == "redis":
                    # Redis check is already done above
                    detailed_health["service_connectivity"][
                        service_name
                    ] = "checked_via_redis"
                else:
                    start_time = time.time()
                    response = await client.get(f"{service_url}/health")
                    response_time = time.time() - start_time
                    detailed_health["service_connectivity"][service_name] = {
                        "status": (
                            "healthy" if response.status_code == 200 else "unhealthy"
                        ),
                        "response_time": response_time,
                        "status_code": response.status_code,
                    }
            except Exception as e:
                detailed_health["service_connectivity"][service_name] = {
                    "status": "unreachable",
                    "error": str(e),
                }

    # Resource alerts
    system_resources = hardware_monitor.get_system_resources()
    if "cpu" in system_resources and system_resources["cpu"]["percent_overall"] > 90:
        detailed_health["resource_alerts"].append(
            {
                "type": "cpu_high",
                "message": (
                    f"CPU usage at {system_resources['cpu']['percent_overall']:.1f}%"
                ),
                "severity": "warning",
            }
        )

    if "memory" in system_resources and system_resources["memory"]["percent"] > 90:
        detailed_health["resource_alerts"].append(
            {
                "type": "memory_high",
                "message": (
                    f"Memory usage at {system_resources['memory']['percent']:.1f}%"
                ),
                "severity": "warning",
            }
        )

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

# Import monitoring and code analysis routers (split to maintain <20 functions)
from backend.api import analytics_monitoring, analytics_code

# Import new analytics modules (Issue #59 - Advanced Analytics & BI)
from backend.api import analytics_cost, analytics_agents, analytics_export, analytics_behavior

# Include sub-routers
router.include_router(analytics_monitoring.router)
router.include_router(analytics_code.router)

# Include Issue #59 sub-routers (Advanced Analytics & BI)
router.include_router(analytics_cost.router)
router.include_router(analytics_agents.router)
router.include_router(analytics_export.router)
router.include_router(analytics_behavior.router)

# Set dependencies for sub-modules
analytics_monitoring.set_analytics_dependencies(
    analytics_controller, analytics_state, hardware_monitor
)
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
    # Get current system metrics
    current_metrics = await analytics_controller.metrics_collector.collect_all_metrics()
    system_resources = hardware_monitor.get_system_resources()

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
        "performance_snapshot": {
            "cpu_percent": system_resources.get("cpu", {}).get("percent_overall", 0),
            "memory_percent": system_resources.get("memory", {}).get("percent", 0),
            "disk_percent": system_resources.get("disk", {}).get("percent", 0),
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

    if redis_conn:
        try:
            # Get historical API calls
            cutoff_time = datetime.now() - timedelta(hours=hours)
            api_calls = await redis_conn.lrange("analytics:api_calls", 0, -1)

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

            # Analyze historical patterns
            if historical_calls:
                # Group by hour
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

                historical_data["hourly_patterns"] = dict(hourly_stats)
                historical_data["analysis_period_hours"] = hours
                historical_data["total_historical_calls"] = len(historical_calls)

        except Exception as e:
            historical_data["redis_error"] = str(e)

    return historical_data


# ============================================================================
# WEBSOCKET REAL-TIME ANALYTICS STREAMING
# ============================================================================


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

        # Start streaming loop
        while True:
            try:
                # Wait for client message or timeout for periodic updates
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(), timeout=10.0
                    )
                    await _handle_realtime_client_command(websocket, message)

                except asyncio.TimeoutError:
                    # Periodic update - send current metrics
                    try:
                        current_data = await get_realtime_metrics()
                        await websocket.send_json(_build_periodic_update(current_data))
                    except Exception as e:
                        logger.error(f"Failed to send periodic update: {e}")
                        break

            except WebSocketDisconnect:
                logger.info("Analytics WebSocket client disconnected")
                break
            except Exception as e:
                logger.error(f"Error in analytics WebSocket: {e}")
                try:
                    await websocket.send_json(_build_error_message(e))
                except Exception:
                    break

    except Exception as e:
        logger.error(f"Analytics WebSocket error: {e}")
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
        await asyncio.sleep(0.5)  # Give it time to start

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_analytics_status",
    error_code_prefix="ANALYTICS",
)
@router.get("/status")
async def get_analytics_status():
    """Get comprehensive analytics system status"""
    collector = analytics_controller.metrics_collector

    status = {
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
        "integration_status": {
            "redis_connectivity": {},
            "code_analysis_tools": {
                "code_analysis_suite": analytics_controller.code_analysis_path.exists(),
                "code_index_mcp": analytics_controller.code_index_path.exists(),
            },
        },
    }

    # Check Redis connectivity
    for db in [RedisDatabase.METRICS, RedisDatabase.KNOWLEDGE, RedisDatabase.MAIN]:
        try:
            redis_conn = await analytics_controller.get_redis_connection(db)
            if redis_conn:
                await redis_conn.ping()
                status["integration_status"]["redis_connectivity"][
                    db.name
                ] = "connected"
            else:
                status["integration_status"]["redis_connectivity"][db.name] = "failed"
        except Exception as e:
            status["integration_status"]["redis_connectivity"][
                db.name
            ] = f"error: {str(e)}"

    return status


# ============================================================================
# PHASE 9 MONITORING DASHBOARD ENDPOINTS (MOVED TO analytics_monitoring.py)
# ============================================================================

# The following functions have been moved to analytics_monitoring.py:
# - get_monitoring_status
# - get_phase9_dashboard_data
# - get_phase9_alerts
# - get_phase9_optimization_recommendations
# - start_monitoring
# - stop_monitoring
# - query_phase9_metrics

# Phase 9 monitoring endpoints have been moved to analytics_monitoring.py


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

        # Start streaming loop with different update frequencies
        last_performance_update = 0
        last_api_update = 0
        last_health_update = 0

        while True:
            try:
                current_time = time.time()

                # Performance updates (every 5 seconds)
                if current_time - last_performance_update > 5:
                    try:
                        perf_data = await analytics_controller.collect_performance_metrics()
                        await websocket.send_json(_build_performance_message(perf_data))
                        last_performance_update = current_time
                    except Exception as e:
                        logger.error(f"Performance update error: {e}")

                # API activity updates (every 2 seconds)
                if current_time - last_api_update > 2:
                    try:
                        recent_calls = _get_recent_api_calls(cutoff_seconds=10)
                        await websocket.send_json(_build_api_activity_message(recent_calls))
                        last_api_update = current_time
                    except Exception as e:
                        logger.error(f"API activity update error: {e}")

                # System health updates (every 10 seconds)
                if current_time - last_health_update > 10:
                    try:
                        alerts = await analytics_monitoring.get_phase9_alerts()
                        critical = [a for a in alerts if a.get("severity") == "critical"]
                        await websocket.send_json(_build_health_message(alerts, critical))
                        last_health_update = current_time
                    except Exception as e:
                        logger.error(f"System health update error: {e}")

                # Wait for client message or timeout
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(), timeout=1.0
                    )
                    await _handle_websocket_command(websocket, message)
                except asyncio.TimeoutError:
                    pass  # Continue with periodic updates

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in live analytics WebSocket: {e}")
                try:
                    await websocket.send_json(_build_error_message(e))
                except Exception:
                    break

    except Exception as e:
        logger.error(f"Live analytics WebSocket error: {e}")
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
