# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Phase 9 Monitoring Analytics API Module
Provides Phase 9 monitoring endpoints for the dashboard
Extracted from analytics.py to maintain <20 functions per file
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta

import psutil
from fastapi import APIRouter

from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import shared analytics controller from analytics module
# This will be set after analytics.py is updated
analytics_controller = None
analytics_state = None
hardware_monitor = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics", "monitoring"])


def set_analytics_dependencies(controller, state, hw_monitor):
    """Set dependencies from main analytics module"""
    global analytics_controller, analytics_state, hardware_monitor
    analytics_controller = controller
    analytics_state = state
    hardware_monitor = hw_monitor


# ============================================================================
# PHASE 9 MONITORING DASHBOARD ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_monitoring_status",
    error_code_prefix="ANALYTICS",
)
@router.get("/monitoring/phase9/status")
async def get_monitoring_status():
    """Get Phase 9 monitoring status for dashboard"""
    collector = analytics_controller.metrics_collector

    status = {
        "active": (
            collector._is_collecting if hasattr(collector, "_is_collecting") else True
        ),
        "timestamp": datetime.now().isoformat(),
        "components": {
            "gpu_monitoring": True,
            "npu_monitoring": True,
            "analytics_collection": True,
            "websocket_streaming": len(analytics_state["websocket_connections"]) > 0,
        },
        "version": "Phase9",
        "uptime_seconds": time.time() - psutil.boot_time(),
    }

    return status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase9_dashboard_data",
    error_code_prefix="ANALYTICS",
)
@router.get("/monitoring/phase9/dashboard")
async def get_phase9_dashboard_data():
    """Get comprehensive Phase 9 dashboard data"""
    # Get performance metrics
    performance_data = await analytics_controller.collect_performance_metrics()

    # Get system health
    system_health = await hardware_monitor.get_system_health()

    # Calculate overall health score
    cpu_health = 100 - performance_data.get("system_performance", {}).get(
        "cpu_percent", 0
    )
    memory_health = 100 - performance_data.get("system_performance", {}).get(
        "memory_percent", 0
    )
    gpu_health = 100 - performance_data.get("hardware_performance", {}).get(
        "gpu_utilization", 0
    )

    overall_score = (cpu_health + memory_health + gpu_health) / 3

    dashboard_data = {
        "timestamp": datetime.now().isoformat(),
        "overall_health": {
            "score": round(overall_score, 1),
            "status": (
                "excellent"
                if overall_score > 80
                else (
                    "good"
                    if overall_score > 60
                    else "warning" if overall_score > 40 else "critical"
                )
            ),
            "text": (
                "Excellent"
                if overall_score > 80
                else (
                    "Good"
                    if overall_score > 60
                    else "Warning" if overall_score > 40 else "Critical"
                )
            ),
        },
        "gpu_metrics": performance_data.get("hardware_performance", {}).get("gpu", {}),
        "npu_metrics": performance_data.get("hardware_performance", {}).get("npu", {}),
        "system_metrics": {
            "cpu": performance_data.get("system_performance", {}),
            "memory": performance_data.get("system_performance", {}),
            "network": performance_data.get("network_io", {}),
        },
        "api_performance": performance_data.get("api_performance", {}),
        "active_connections": len(analytics_state["websocket_connections"]),
        "recent_api_calls": len(
            [
                call
                for call in analytics_state["api_call_patterns"]
                if datetime.fromisoformat(call["timestamp"])
                > datetime.now() - timedelta(minutes=5)
            ]
        ),
        "system_health": system_health,
    }

    return dashboard_data


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase9_alerts",
    error_code_prefix="ANALYTICS",
)
@router.get("/monitoring/phase9/alerts")
async def get_phase9_alerts():
    """Get Phase 9 monitoring alerts"""
    alerts = []

    # Get current metrics for alert generation
    performance_data = await analytics_controller.collect_performance_metrics()

    # CPU alerts
    cpu_percent = performance_data.get("system_performance", {}).get("cpu_percent", 0)
    if cpu_percent > 90:
        alerts.append(
            {
                "id": f"cpu_high_{int(time.time())}",
                "type": "cpu",
                "severity": "critical",
                "title": "High CPU Usage",
                "message": f"CPU usage is at {cpu_percent:.1f}%",
                "timestamp": datetime.now().isoformat(),
                "value": cpu_percent,
                "threshold": 90,
            }
        )
    elif cpu_percent > 75:
        alerts.append(
            {
                "id": f"cpu_warn_{int(time.time())}",
                "type": "cpu",
                "severity": "warning",
                "title": "Elevated CPU Usage",
                "message": f"CPU usage is at {cpu_percent:.1f}%",
                "timestamp": datetime.now().isoformat(),
                "value": cpu_percent,
                "threshold": 75,
            }
        )

    # Memory alerts
    memory_percent = performance_data.get("system_performance", {}).get(
        "memory_percent", 0
    )
    if memory_percent > 90:
        alerts.append(
            {
                "id": f"memory_high_{int(time.time())}",
                "type": "memory",
                "severity": "critical",
                "title": "High Memory Usage",
                "message": f"Memory usage is at {memory_percent:.1f}%",
                "timestamp": datetime.now().isoformat(),
                "value": memory_percent,
                "threshold": 90,
            }
        )

    # GPU alerts
    gpu_util = performance_data.get("hardware_performance", {}).get(
        "gpu_utilization", 0
    )
    if gpu_util > 95:
        alerts.append(
            {
                "id": f"gpu_high_{int(time.time())}",
                "type": "gpu",
                "severity": "warning",
                "title": "High GPU Utilization",
                "message": f"GPU utilization is at {gpu_util:.1f}%",
                "timestamp": datetime.now().isoformat(),
                "value": gpu_util,
                "threshold": 95,
            }
        )

    # API performance alerts
    api_performance = performance_data.get("api_performance", {})
    slow_endpoints = [
        endpoint
        for endpoint, data in api_performance.items()
        if data.get("avg_response_time", 0) > 5.0
    ]

    if slow_endpoints:
        alerts.append(
            {
                "id": f"api_slow_{int(time.time())}",
                "type": "api_performance",
                "severity": "warning",
                "title": "Slow API Endpoints",
                "message": f"{len(slow_endpoints)} endpoints have high response times",
                "timestamp": datetime.now().isoformat(),
                "details": slow_endpoints[:3],
            }
        )

    return alerts


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase9_optimization_recommendations",
    error_code_prefix="ANALYTICS",
)
@router.get("/monitoring/phase9/optimization/recommendations")
async def get_phase9_optimization_recommendations():
    """Get Phase 9 optimization recommendations"""
    recommendations = []

    # Get current performance data
    performance_data = await analytics_controller.collect_performance_metrics()
    communication_patterns = await analytics_controller.analyze_communication_patterns()

    # CPU optimization recommendations
    cpu_percent = performance_data.get("system_performance", {}).get("cpu_percent", 0)
    if cpu_percent > 80:
        recommendations.append(
            {
                "type": "cpu_optimization",
                "priority": "high",
                "title": "Optimize CPU Usage",
                "description": (
                    "CPU usage is consistently high. Consider optimizing background processes."
                ),
                "impact": "High",
                "estimated_improvement": "15-25% performance boost",
                "actions": [
                    "Review running processes and terminate unnecessary ones",
                    "Optimize async operations to reduce CPU blocking",
                    "Consider scaling horizontally with additional VMs",
                ],
            }
        )

    # Memory optimization recommendations
    memory_percent = performance_data.get("system_performance", {}).get(
        "memory_percent", 0
    )
    if memory_percent > 80:
        recommendations.append(
            {
                "type": "memory_optimization",
                "priority": "medium",
                "title": "Optimize Memory Usage",
                "description": (
                    "Memory usage is high. Consider memory optimization strategies."
                ),
                "impact": "Medium",
                "estimated_improvement": "10-20% memory reduction",
                "actions": [
                    "Clear Redis caches for unused data",
                    "Optimize knowledge base vector storage",
                    "Implement memory pooling for frequent operations",
                ],
            }
        )

    # API optimization recommendations
    if communication_patterns.get("avg_response_time", 0) > 2.0:
        recommendations.append(
            {
                "type": "api_optimization",
                "priority": "high",
                "title": "Optimize API Response Times",
                "description": (
                    f"Average API response time is {communication_patterns.get('avg_response_time', 0):.2f}s"
                ),
                "impact": "High",
                "estimated_improvement": "50-70% faster responses",
                "actions": [
                    "Implement response caching for frequently requested data",
                    "Optimize database queries and indexing",
                    "Add connection pooling for external services",
                ],
            }
        )

    # Code analysis recommendations
    cached_analysis = analytics_state.get("code_analysis_cache")
    if cached_analysis and "code_analysis" in cached_analysis:
        complexity = cached_analysis["code_analysis"].get("complexity", 0)
        if complexity > 7:
            recommendations.append(
                {
                    "type": "code_quality",
                    "priority": "medium",
                    "title": "Reduce Code Complexity",
                    "description": f"Code complexity score is {complexity}/10",
                    "impact": "Medium",
                    "estimated_improvement": "Better maintainability and performance",
                    "actions": [
                        "Refactor complex functions into smaller components",
                        "Extract common patterns into utility functions",
                        "Implement proper error handling patterns",
                    ],
                }
            )

    return recommendations


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_monitoring",
    error_code_prefix="ANALYTICS",
)
@router.post("/monitoring/phase9/start")
async def start_monitoring():
    """Start Phase 9 monitoring"""
    # Start metrics collection
    collector = analytics_controller.metrics_collector
    if hasattr(collector, "_is_collecting") and not collector._is_collecting:
        asyncio.create_task(collector.start_collection())

    # Initialize session tracking
    analytics_state["session_start"] = datetime.now().isoformat()

    return {
        "status": "started",
        "message": "Phase 9 monitoring started successfully",
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_monitoring",
    error_code_prefix="ANALYTICS",
)
@router.post("/monitoring/phase9/stop")
async def stop_monitoring():
    """Stop Phase 9 monitoring"""
    # Stop metrics collection
    collector = analytics_controller.metrics_collector
    if hasattr(collector, "_is_collecting") and collector._is_collecting:
        await collector.stop_collection()

    return {
        "status": "stopped",
        "message": "Phase 9 monitoring stopped successfully",
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_phase9_metrics",
    error_code_prefix="ANALYTICS",
)
@router.post("/monitoring/phase9/metrics/query")
async def query_phase9_metrics(query_request: dict):
    """Query Phase 9 metrics with filtering"""
    metric_name = query_request.get("metric", "all")
    time_range = query_request.get("time_range", 3600)  # 1 hour default

    # Get current metrics
    current_metrics = await analytics_controller.metrics_collector.collect_all_metrics()

    # Filter by metric name if specified
    if metric_name != "all" and metric_name in current_metrics:
        filtered_metrics = {metric_name: current_metrics[metric_name]}
    else:
        filtered_metrics = current_metrics

    # Add historical context from performance history
    historical_data = []
    cutoff_time = datetime.now() - timedelta(seconds=time_range)

    for perf_point in analytics_state["performance_history"]:
        point_time = datetime.fromisoformat(perf_point["timestamp"])
        if point_time > cutoff_time:
            historical_data.append(perf_point)

    return {
        "current_metrics": {
            name: {
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
                "timestamp": metric.timestamp,
            }
            for name, metric in filtered_metrics.items()
        },
        "historical_data": historical_data,
        "query_info": {
            "metric": metric_name,
            "time_range_seconds": time_range,
            "results_count": len(filtered_metrics),
            "historical_points": len(historical_data),
        },
    }
