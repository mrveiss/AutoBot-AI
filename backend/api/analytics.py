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
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import psutil
import redis
import requests
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from backend.type_defs.common import Metadata
from src.constants import PATH

# Import models from dedicated module (Issue #185 - split oversized files)
from backend.api.analytics_models import (
    AnalyticsOverview,
    CodeAnalysisRequest,
    CommunicationPattern,
    RealTimeEvent,
)
from src.constants.network_constants import NetworkConstants
from src.unified_config_manager import UnifiedConfigManager
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import RedisDatabase, RedisDatabaseManager
from src.utils.system_metrics import get_metrics_collector

# Import existing monitoring infrastructure
from .monitoring import hardware_monitor

# Create singleton config instance
config = UnifiedConfigManager()


# Simple service address function using configuration
def get_service_address(service_name: str, port: int, protocol: str = "http") -> str:
    """Get standardized service address from config helper"""
    # Get host from configuration system
    try:
        host = config.get_host(service_name)
    except Exception:
        # Fallback to localhost if config lookup fails
        host = "localhost"
    return f"{protocol}://{host}:{port}"


logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

# Global analytics state management
analytics_state = {
    "websocket_connections": set(),
    "api_call_patterns": deque(maxlen=1000),
    "performance_history": deque(maxlen=500),
    "communication_chains": defaultdict(list),
    "code_analysis_cache": {},
    "last_analysis_time": None,
}


# ============================================================================
# ANALYTICS CORE CLASS
# ============================================================================


class AnalyticsController:
    """Core analytics controller with comprehensive monitoring capabilities"""

    def __init__(self):
        self.redis_manager = RedisDatabaseManager()
        self.metrics_collector = get_metrics_collector()
        self.code_analysis_path = PATH.PROJECT_ROOT / "tools" / "code-analysis-suite"
        self.code_index_path = PATH.PROJECT_ROOT / "mcp-tools" / "code-index-mcp"

        # Performance tracking
        self.api_call_tracker = defaultdict(list)
        self.websocket_activity = defaultdict(int)
        self.system_bottlenecks = []

        # Communication pattern analysis
        self.communication_chains = defaultdict(list)
        self.api_frequencies = defaultdict(int)
        self.response_times = defaultdict(list)
        self.error_counts = defaultdict(int)

    async def get_redis_connection(self, database: RedisDatabase) -> redis.Redis:
        """Get Redis connection for specific database"""
        try:
            return await self.redis_manager.get_async_connection(database)
        except Exception as e:
            logger.error(f"Failed to get Redis connection for {database}: {e}")
            return None

    async def track_api_call(
        self, endpoint: str, response_time: float, status_code: int
    ):
        """Track API call for pattern analysis"""
        timestamp = datetime.now().isoformat()

        # Update frequency tracking
        self.api_frequencies[endpoint] += 1

        # Track response times
        self.response_times[endpoint].append(response_time)
        if len(self.response_times[endpoint]) > 100:
            self.response_times[endpoint] = self.response_times[endpoint][-100:]

        # Track errors
        if status_code >= 400:
            self.error_counts[endpoint] += 1

        # Store in analytics state
        analytics_state["api_call_patterns"].append(
            {
                "endpoint": endpoint,
                "response_time": response_time,
                "status_code": status_code,
                "timestamp": timestamp,
            }
        )

        # Store in Redis for persistence
        try:
            redis_conn = await self.get_redis_connection(RedisDatabase.METRICS)
            if redis_conn:
                await redis_conn.lpush(
                    "analytics:api_calls",
                    json.dumps(
                        {
                            "endpoint": endpoint,
                            "response_time": response_time,
                            "status_code": status_code,
                            "timestamp": timestamp,
                        }
                    ),
                )
                await redis_conn.ltrim(
                    "analytics:api_calls", 0, 9999
                )  # Keep last 10k calls
        except Exception as e:
            logger.error(f"Failed to store API call analytics: {e}")

    async def analyze_communication_patterns(self) -> Metadata:
        """Analyze communication patterns across the system"""
        patterns = {}

        # Analyze API call patterns
        api_patterns = []
        for endpoint, frequency in self.api_frequencies.items():
            avg_response_time = (
                sum(self.response_times[endpoint]) / len(self.response_times[endpoint])
                if self.response_times[endpoint]
                else 0
            ),
            error_rate = (
                self.error_counts[endpoint] / frequency * 100 if frequency > 0 else 0
            )

            api_patterns.append(
                CommunicationPattern(
                    endpoint=endpoint,
                    frequency=frequency,
                    avg_response_time=avg_response_time,
                    error_rate=error_rate,
                    last_accessed=datetime.now().isoformat(),
                    pattern_type="API",
                )
            )

        # Sort by frequency
        api_patterns.sort(key=lambda x: x.frequency, reverse=True)

        patterns["api_patterns"] = [p.dict() for p in api_patterns[:20]]  # Top 20
        patterns["websocket_activity"] = dict(self.websocket_activity)
        patterns["total_api_calls"] = sum(self.api_frequencies.values())
        patterns["unique_endpoints"] = len(self.api_frequencies)
        patterns["avg_response_time"] = sum(
            sum(times) for times in self.response_times.values()
        ) / max(sum(len(times) for times in self.response_times.values()), 1)

        return patterns

    async def perform_code_analysis(
        self, request: CodeAnalysisRequest
    ) -> Metadata:
        """Perform code analysis using integrated tools"""
        analysis_results = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "analysis_type": request.analysis_type,
            "target_path": request.target_path,
        }

        try:
            # Check if code analysis tools are available
            if not self.code_analysis_path.exists():
                analysis_results["status"] = "error"
                analysis_results["error"] = "Code analysis suite not found"
                return analysis_results

            # Run code analysis suite
            if request.analysis_type in ["full", "communication_chains"]:
                await self._run_code_analysis_suite(request, analysis_results)

            # Run code indexing if available
            if self.code_index_path.exists() and request.analysis_type in [
                "full",
                "incremental",
            ]:
                await self._run_code_indexing(request, analysis_results)

            # Store results in cache
            analytics_state["code_analysis_cache"] = analysis_results
            analytics_state["last_analysis_time"] = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"Code analysis failed: {e}")
            analysis_results["status"] = "error"
            analysis_results["error"] = str(e)

        return analysis_results

    async def _run_code_analysis_suite(
        self, request: CodeAnalysisRequest, results: Dict
    ):
        """Run the code analysis suite"""
        try:
            cmd = [
                "python3",
                str(self.code_analysis_path / "scripts" / "analyze_project.py"),
                "--target",
                request.target_path,
                "--output-format",
                "json",
            ]

            if request.analysis_type == "communication_chains":
                cmd.extend(["--focus", "communication"])

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.code_analysis_path),
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode == 0:
                analysis_data = json.loads(stdout.decode())
                results["code_analysis"] = analysis_data
                results["communication_chains"] = analysis_data.get(
                    "communication_patterns", {}
                )
            else:
                results["code_analysis_error"] = stderr.decode()

        except asyncio.TimeoutError:
            results["code_analysis_error"] = "Analysis timeout (5 minutes)"
        except Exception as e:
            results["code_analysis_error"] = str(e)

    async def _run_code_indexing(self, request: CodeAnalysisRequest, results: Dict):
        """Run code indexing using code-index-mcp"""
        try:
            cmd = [
                "python3",
                str(self.code_index_path / "run.py"),
                "--index-path",
                request.target_path,
                "--output-format",
                "json",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.code_index_path),
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)

            if process.returncode == 0:
                index_data = json.loads(stdout.decode())
                results["code_index"] = index_data
                results["codebase_metrics"] = {
                    "total_files": index_data.get("file_count", 0),
                    "total_lines": index_data.get("line_count", 0),
                    "languages": index_data.get("languages", {}),
                    "complexity_score": index_data.get("complexity", 0),
                }
            else:
                results["code_index_error"] = stderr.decode()

        except asyncio.TimeoutError:
            results["code_index_error"] = "Indexing timeout (3 minutes)"
        except Exception as e:
            results["code_index_error"] = str(e)

    async def collect_performance_metrics(self) -> Metadata:
        """Collect comprehensive performance metrics"""
        metrics = {}

        try:
            # Get advanced metrics from existing collector
            current_metrics = await self.metrics_collector.collect_all_metrics()
            summary = await self.metrics_collector.get_metric_summary()

            # System performance
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            metrics["system_performance"] = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": (disk.used / disk.total) * 100,
                "load_average": (
                    psutil.getloadavg() if hasattr(psutil, "getloadavg") else [0, 0, 0]
                ),
            }

            # API performance from tracking
            api_performance = {}
            for endpoint, times in self.response_times.items():
                if times:
                    api_performance[endpoint] = {
                        "avg_response_time": sum(times) / len(times),
                        "min_response_time": min(times),
                        "max_response_time": max(times),
                        "total_calls": self.api_frequencies[endpoint],
                        "error_rate": (
                            (
                                self.error_counts[endpoint]
                                / self.api_frequencies[endpoint]
                                * 100
                            )
                            if self.api_frequencies[endpoint] > 0
                            else 0
                        ),
                    }

            metrics["api_performance"] = api_performance
            metrics["advanced_metrics"] = summary
            metrics["detailed_metrics"] = current_metrics

            # Hardware performance from existing monitor
            gpu_status = hardware_monitor.get_gpu_status()
            npu_status = hardware_monitor.get_npu_status()

            metrics["hardware_performance"] = {
                "gpu": gpu_status,
                "npu": npu_status,
                "gpu_utilization": gpu_status.get("utilization_percent", 0),
                "gpu_memory_usage": gpu_status.get("memory_utilization_percent", 0),
            }

            # Network and I/O
            network = psutil.net_io_counters()
            metrics["network_io"] = {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
            }

        except Exception as e:
            logger.error(f"Failed to collect performance metrics: {e}")
            metrics["error"] = str(e)

        return metrics

    async def get_usage_statistics(self) -> Metadata:
        """Get comprehensive usage statistics"""
        stats = {}

        try:
            # API usage statistics
            total_calls = sum(self.api_frequencies.values())
            most_used_endpoints = sorted(
                self.api_frequencies.items(), key=lambda x: x[1], reverse=True
            )[:10]

            stats["api_usage"] = {
                "total_calls": total_calls,
                "unique_endpoints": len(self.api_frequencies),
                "most_used_endpoints": [
                    {"endpoint": endpoint, "calls": calls}
                    for endpoint, calls in most_used_endpoints
                ],
                "total_errors": sum(self.error_counts.values()),
                "overall_error_rate": (
                    (sum(self.error_counts.values()) / total_calls * 100)
                    if total_calls > 0
                    else 0
                ),
            }

            # WebSocket usage
            stats["websocket_usage"] = {
                "active_connections": len(analytics_state["websocket_connections"]),
                "activity_by_type": dict(self.websocket_activity),
            }

            # System uptime and resource usage
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time

            stats["system_usage"] = {
                "uptime_hours": uptime_seconds / 3600,
                "processes_count": len(psutil.pids()),
                "active_users": len(psutil.users()) if hasattr(psutil, "users") else 0,
            }

            # Knowledge base usage (if available)
            try:
                redis_conn = await self.get_redis_connection(RedisDatabase.KNOWLEDGE)
                if redis_conn:
                    kb_info = await redis_conn.info()
                    stats["knowledge_base_usage"] = {
                        "keys_count": kb_info.get("db1", {}).get("keys", 0),
                        "memory_usage_mb": (
                            kb_info.get("used_memory", 0) / (1024 * 1024)
                        ),
                    }
            except Exception:
                stats["knowledge_base_usage"] = {"error": "Unable to retrieve KB stats"}

        except Exception as e:
            logger.error(f"Failed to get usage statistics: {e}")
            stats["error"] = str(e)

        return stats

    async def detect_trends(self) -> Metadata:
        """Detect trends in system performance and usage"""
        trends = {}

        try:
            # Performance trends from history
            if analytics_state["performance_history"]:
                recent_performance = list(analytics_state["performance_history"])[-50:]

                # Calculate trends
                cpu_trend = self._calculate_trend(
                    [p.get("cpu_percent", 0) for p in recent_performance]
                ),
                memory_trend = self._calculate_trend(
                    [p.get("memory_percent", 0) for p in recent_performance]
                )

                trends["performance_trends"] = {
                    "cpu_trend": cpu_trend,
                    "memory_trend": memory_trend,
                    "trend_period_minutes": (
                        len(recent_performance) * 2
                    ),  # Assuming 2-minute intervals
                }

            # API usage trends
            recent_calls = list(analytics_state["api_call_patterns"])[-100:]
            if recent_calls:
                response_times = [call["response_time"] for call in recent_calls]
                response_time_trend = self._calculate_trend(response_times)

                trends["api_trends"] = {
                    "response_time_trend": response_time_trend,
                    "recent_calls_count": len(recent_calls),
                    "avg_response_time": sum(response_times) / len(response_times),
                }

            # Error trends
            error_calls = [call for call in recent_calls if call["status_code"] >= 400]
            trends["error_trends"] = {
                "recent_error_rate": (
                    len(error_calls) / len(recent_calls) * 100 if recent_calls else 0
                ),
                "total_recent_errors": len(error_calls),
            }

        except Exception as e:
            logger.error(f"Failed to detect trends: {e}")
            trends["error"] = str(e)

        return trends

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from list of values"""
        if len(values) < 2:
            return "stable"

        # Simple linear trend calculation
        first_half = values[: len(values) // 2]
        second_half = values[len(values) // 2 :]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        change_percent = (
            ((second_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0
        )

        if abs(change_percent) < 5:
            return "stable"
        elif change_percent > 0:
            return "increasing"
        else:
            return "decreasing"


# Global analytics controller instance
analytics_controller = AnalyticsController()

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
        ),
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

    for service_name, service_url in services.items():
        try:
            if service_name == "redis":
                # Redis check is already done above
                detailed_health["service_connectivity"][
                    service_name
                ] = "checked_via_redis"
            else:
                response = requests.get(f"{service_url}/health", timeout=5)
                detailed_health["service_connectivity"][service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response.elapsed.total_seconds(),
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
# CODE ANALYSIS INTEGRATION ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="ANALYTICS",
)
@router.post("/code/index")
async def index_codebase(request: CodeAnalysisRequest):
    """Trigger codebase indexing and analysis"""
    # Validate request
    if not Path(request.target_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Target path does not exist: {request.target_path}",
        )

    # Perform analysis
    results = await analytics_controller.perform_code_analysis(request)

    return {
        "status": "completed",
        "request": request.dict(),
        "results": results,
        "cached_for_reuse": True,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_analysis_status",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/status")
async def get_code_analysis_status():
    """Get current code analysis status and capabilities"""
    status = {
        "tools_available": {
            "code_analysis_suite": analytics_controller.code_analysis_path.exists(),
            "code_index_mcp": analytics_controller.code_index_path.exists(),
        },
        "last_analysis_time": analytics_state.get("last_analysis_time"),
        "cache_status": {
            "has_cached_results": bool(analytics_state.get("code_analysis_cache")),
            "cache_timestamp": analytics_state.get("last_analysis_time"),
        },
        "supported_analysis_types": ["full", "incremental", "communication_chains"],
    }

    # Add tool details if available
    if analytics_controller.code_analysis_path.exists():
        status["code_analysis_suite"] = {
            "path": str(analytics_controller.code_analysis_path),
            "scripts_available": list(
                analytics_controller.code_analysis_path.glob("scripts/*.py")
            ),
        }

    if analytics_controller.code_index_path.exists():
        status["code_index_mcp"] = {
            "path": str(analytics_controller.code_index_path),
            "config_available": (
                (analytics_controller.code_index_path / "pyproject.toml").exists()
            ),
        }

    return status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_quality_assessment",
    error_code_prefix="ANALYTICS",
)
@router.get("/quality/assessment")
async def get_code_quality_assessment():
    """Get comprehensive code quality assessment for frontend dashboard"""
    # Get cached analysis or trigger new one
    cached_analysis = analytics_state.get("code_analysis_cache")

    # Default quality scores
    quality_assessment = {
        "overall_score": 75,
        "maintainability": 80,
        "testability": 70,
        "documentation": 65,
        "complexity": 85,
        "security": 75,
        "performance": 80,
        "timestamp": datetime.now().isoformat(),
    }

    # If we have cached analysis, use it
    if cached_analysis and "code_analysis" in cached_analysis:
        code_data = cached_analysis["code_analysis"]

        # Calculate quality metrics based on analysis
        complexity = code_data.get("complexity", 5)
        quality_assessment["complexity"] = max(0, (10 - complexity) * 10)

        quality_assessment["testability"] = code_data.get("test_coverage", 70)
        quality_assessment["documentation"] = code_data.get("doc_coverage", 65)

        # Calculate maintainability
        maintainability = code_data.get("maintainability", "good")
        maintainability_scores = {
            "excellent": 95,
            "good": 80,
            "fair": 65,
            "poor": 40,
        }
        quality_assessment["maintainability"] = maintainability_scores.get(
            maintainability, 80
        )

        # Overall score is average of all factors
        quality_assessment["overall_score"] = round(
            (
                quality_assessment["maintainability"]
                + quality_assessment["testability"]
                + quality_assessment["documentation"]
                + quality_assessment["complexity"]
                + quality_assessment["security"]
                + quality_assessment["performance"]
            )
            / 6,
            1,
        )

    return quality_assessment


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_quality_metrics",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/quality-metrics")
async def get_code_quality_metrics():
    """Get code quality metrics from cached analysis"""
    cached_analysis = analytics_state.get("code_analysis_cache")

    if not cached_analysis:
        return {
            "status": "no_analysis_available",
            "message": "No cached code analysis found. Run /code/index first.",
            "suggestion": "POST /api/analytics/code/index with analysis_type='full'",
        }

    # Extract quality metrics
    quality_metrics = {
        "analysis_timestamp": cached_analysis.get("timestamp"),
        "codebase_metrics": cached_analysis.get("codebase_metrics", {}),
        "quality_indicators": {},
        "recommendations": [],
    }

    # Process code analysis results if available
    if "code_analysis" in cached_analysis:
        code_data = cached_analysis["code_analysis"]

        quality_metrics["quality_indicators"] = {
            "complexity_score": code_data.get("complexity", 0),
            "maintainability": code_data.get("maintainability", "unknown"),
            "test_coverage": code_data.get("test_coverage", 0),
            "documentation_coverage": code_data.get("doc_coverage", 0),
        }

        # Generate recommendations
        if code_data.get("complexity", 0) > 7:
            quality_metrics["recommendations"].append(
                {
                    "type": "complexity",
                    "message": (
                        "High complexity detected. Consider refactoring complex functions."
                    ),
                    "priority": "medium",
                }
            )

        if code_data.get("test_coverage", 0) < 70:
            quality_metrics["recommendations"].append(
                {
                    "type": "testing",
                    "message": "Low test coverage. Consider adding more unit tests.",
                    "priority": "high",
                }
            )

    return quality_metrics


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_communication_chains",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/communication-chains")
async def get_communication_chains():
    """Get communication chain analysis from code analysis"""
    cached_analysis = analytics_state.get("code_analysis_cache")

    if not cached_analysis or "communication_chains" not in cached_analysis:
        return {
            "status": "no_analysis_available",
            "message": "No communication chain analysis found.",
            "suggestion": (
                "POST /api/analytics/code/index with analysis_type='communication_chains'"
            ),
        }

    chains = cached_analysis["communication_chains"]

    # Enhance with runtime patterns
    enhanced_chains = {
        "static_analysis": chains,
        "runtime_patterns": dict(analytics_controller.communication_chains),
        "correlation_analysis": {},
        "insights": [],
    }

    # Correlate static and runtime patterns
    static_endpoints = chains.get("api_endpoints", [])
    runtime_patterns = analytics_controller.api_frequencies

    for endpoint in static_endpoints:
        if endpoint in runtime_patterns:
            enhanced_chains["correlation_analysis"][endpoint] = {
                "static_detected": True,
                "runtime_calls": runtime_patterns[endpoint],
                "avg_response_time": (
                    sum(analytics_controller.response_times[endpoint])
                    / len(analytics_controller.response_times[endpoint])
                    if analytics_controller.response_times[endpoint]
                    else 0
                ),
            }

    # Generate insights
    unused_endpoints = [ep for ep in static_endpoints if ep not in runtime_patterns]
    if unused_endpoints:
        enhanced_chains["insights"].append(
            {
                "type": "unused_endpoints",
                "message": (
                    f"Found {len(unused_endpoints)} endpoints that are defined but not used"
                ),
                "details": unused_endpoints[:5],
            }
        )

    runtime_only = [ep for ep in runtime_patterns if ep not in static_endpoints]
    if runtime_only:
        enhanced_chains["insights"].append(
            {
                "type": "undocumented_endpoints",
                "message": (
                    f"Found {len(runtime_only)} endpoints in use but not in static analysis"
                ),
                "details": runtime_only[:5],
            }
        )

    return enhanced_chains


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
            except Exception:
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
                except Exception:
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

                    # Handle client commands
                    try:
                        command = json.loads(message)
                        if command.get("type") == "subscribe":
                            # Client subscribing to specific metrics
                            await websocket.send_json(
                                {
                                    "type": "subscription_confirmed",
                                    "subscribed_to": command.get("metrics", "all"),
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        elif command.get("type") == "get_current":
                            # Client requesting current snapshot
                            current_data = await get_realtime_metrics()
                            await websocket.send_json(
                                {
                                    "type": "current_snapshot",
                                    "data": current_data,
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                    except json.JSONDecodeError:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Invalid JSON in client message",
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

                except asyncio.TimeoutError:
                    # Periodic update - send current metrics
                    try:
                        current_data = await get_realtime_metrics()
                        await websocket.send_json(
                            {
                                "type": "periodic_update",
                                "data": {
                                    "performance_snapshot": current_data[
                                        "performance_snapshot"
                                    ],
                                    "active_connections": current_data[
                                        "active_connections"
                                    ],
                                    "recent_api_calls": current_data[
                                        "recent_api_calls"
                                    ],
                                },
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to send periodic update: {e}")
                        break

            except WebSocketDisconnect:
                logger.info("Analytics WebSocket client disconnected")
                break
            except Exception as e:
                logger.error(f"Error in analytics WebSocket: {e}")
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": str(e),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
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


# ============================================================================
# ENHANCED CODE ANALYSIS INTEGRATION
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_communication_chains_detailed",
    error_code_prefix="ANALYTICS",
)
@router.post("/code/analyze/communication-chains")
async def analyze_communication_chains_detailed():
    """Perform detailed communication chain analysis"""
    # Run communication chain analysis
    analysis_request = CodeAnalysisRequest(
        analysis_type="communication_chains", include_metrics=True
    )

    results = await analytics_controller.perform_code_analysis(analysis_request)

    # Enhance with runtime correlation
    if results.get("status") == "success":
        runtime_patterns = analytics_controller.api_frequencies
        static_patterns = results.get("communication_chains", {})

        # Create correlation matrix
        correlation_data = {}

        for endpoint in static_patterns.get("api_endpoints", []):
            correlation_data[endpoint] = {
                "static_detected": True,
                "runtime_calls": runtime_patterns.get(endpoint, 0),
                "avg_response_time": (
                    sum(analytics_controller.response_times.get(endpoint, []))
                    / max(
                        len(analytics_controller.response_times.get(endpoint, [])),
                        1,
                    )
                ),
                "error_rate": (
                    analytics_controller.error_counts.get(endpoint, 0)
                    / max(runtime_patterns.get(endpoint, 1), 1)
                    * 100
                ),
            }

        results["runtime_correlation"] = correlation_data
        results["insights"] = []

        # Generate insights
        unused_endpoints = [
            ep
            for ep in static_patterns.get("api_endpoints", [])
            if ep not in runtime_patterns
        ]

        if unused_endpoints:
            results["insights"].append(
                {
                    "type": "unused_endpoints",
                    "count": len(unused_endpoints),
                    "endpoints": unused_endpoints[:10],
                    "recommendation": (
                        "Consider removing unused endpoints or adding tests"
                    ),
                }
            )

        high_error_endpoints = [
            ep for ep, data in correlation_data.items() if data["error_rate"] > 5.0
        ]

        if high_error_endpoints:
            results["insights"].append(
                {
                    "type": "high_error_endpoints",
                    "count": len(high_error_endpoints),
                    "endpoints": high_error_endpoints,
                    "recommendation": (
                        "Investigate and fix endpoints with high error rates"
                    ),
                }
            )

    return results


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_quality_score",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/metrics/quality-score")
async def get_code_quality_score():
    """Get comprehensive code quality score"""
    cached_analysis = analytics_state.get("code_analysis_cache")

    if not cached_analysis:
        # Trigger new analysis
        analysis_request = CodeAnalysisRequest(analysis_type="full")
        cached_analysis = await analytics_controller.perform_code_analysis(
            analysis_request
        )

    # Calculate quality score
    quality_factors = {
        "complexity": 0,
        "maintainability": 0,
        "test_coverage": 0,
        "documentation": 0,
        "security": 0,
    }

    if "code_analysis" in cached_analysis:
        code_data = cached_analysis["code_analysis"]

        # Complexity score (inverted - lower complexity is better)
        complexity = code_data.get("complexity", 10)
        quality_factors["complexity"] = max(0, (10 - complexity) * 10)

        # Test coverage
        quality_factors["test_coverage"] = code_data.get("test_coverage", 0)

        # Documentation coverage
        quality_factors["documentation"] = code_data.get("doc_coverage", 0)

        # Maintainability (convert to numeric)
        maintainability = code_data.get("maintainability", "poor")
        maintainability_scores = {
            "excellent": 95,
            "good": 80,
            "fair": 65,
            "poor": 40,
        }
        quality_factors["maintainability"] = maintainability_scores.get(
            maintainability, 40
        )

        # Security score (placeholder - would need security analysis)
        quality_factors["security"] = 75  # Default security score

    # Calculate overall score
    overall_score = sum(quality_factors.values()) / len(quality_factors)

    return {
        "overall_score": round(overall_score, 1),
        "grade": (
            "A"
            if overall_score >= 90
            else (
                "B"
                if overall_score >= 80
                else (
                    "C" if overall_score >= 70 else "D" if overall_score >= 60 else "F"
                )
            )
        ),
        "quality_factors": quality_factors,
        "recommendations": [],
        "last_analysis": cached_analysis.get("timestamp"),
        "codebase_metrics": cached_analysis.get("codebase_metrics", {}),
    }


# ============================================================================
# ENHANCED REAL-TIME ANALYTICS
# ============================================================================


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
                        performance_data = (
                            await analytics_controller.collect_performance_metrics()
                        )
                        await websocket.send_json(
                            {
                                "type": "performance_update",
                                "data": {
                                    "cpu_percent": (
                                        performance_data.get(
                                            "system_performance", {}
                                        ).get("cpu_percent", 0)
                                    ),
                                    "memory_percent": (
                                        performance_data.get(
                                            "system_performance", {}
                                        ).get("memory_percent", 0)
                                    ),
                                    "gpu_utilization": (
                                        performance_data.get(
                                            "hardware_performance", {}
                                        ).get("gpu_utilization", 0)
                                    ),
                                    "active_connections": len(
                                        analytics_state["websocket_connections"]
                                    ),
                                },
                                "timestamp": datetime.now().isoformat(),
                            }
                        ),
                        last_performance_update = current_time
                    except Exception as e:
                        logger.error(f"Performance update error: {e}")

                # API activity updates (every 2 seconds)
                if current_time - last_api_update > 2:
                    try:
                        recent_calls = [
                            call
                            for call in analytics_state["api_call_patterns"]
                            if datetime.fromisoformat(call["timestamp"])
                            > datetime.now() - timedelta(seconds=10)
                        ]

                        await websocket.send_json(
                            {
                                "type": "api_activity",
                                "data": {
                                    "recent_calls_count": len(recent_calls),
                                    "recent_calls": recent_calls[-5:],  # Last 5 calls
                                    "total_api_calls": sum(
                                        analytics_controller.api_frequencies.values()
                                    ),
                                },
                                "timestamp": datetime.now().isoformat(),
                            }
                        ),
                        last_api_update = current_time
                    except Exception as e:
                        logger.error(f"API activity update error: {e}")

                # System health updates (every 10 seconds)
                if current_time - last_health_update > 10:
                    try:
                        alerts = await get_phase9_alerts()
                        critical_alerts = [
                            a for a in alerts if a.get("severity") == "critical"
                        ]

                        await websocket.send_json(
                            {
                                "type": "system_health",
                                "data": {
                                    "alerts_count": len(alerts),
                                    "critical_alerts_count": len(critical_alerts),
                                    "critical_alerts": critical_alerts,
                                },
                                "timestamp": datetime.now().isoformat(),
                            }
                        ),
                        last_health_update = current_time
                    except Exception as e:
                        logger.error(f"System health update error: {e}")

                # Wait for client message or timeout
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(), timeout=1.0
                    )
                    try:
                        command = json.loads(message)
                        if command.get("type") == "request_snapshot":
                            # Send immediate snapshot
                            snapshot_data = await get_realtime_metrics()
                            await websocket.send_json(
                                {
                                    "type": "snapshot_response",
                                    "data": snapshot_data,
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                    except json.JSONDecodeError:
                        pass
                except asyncio.TimeoutError:
                    pass  # Continue with regular updates

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in live analytics WebSocket: {e}")
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": str(e),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
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
