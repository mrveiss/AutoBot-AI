# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Controller - Core analytics class with monitoring capabilities.

This module contains the AnalyticsController class for comprehensive system monitoring.
Extracted from analytics.py for better maintainability (Issue #185, #212).

Classes:
- AnalyticsController: Core analytics with metrics, patterns, and code analysis

Related Issues: #185 (Split), #212 (Analytics split)
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import psutil
import redis

# Import models from dedicated module (Issue #185)
from backend.api.analytics_models import CodeAnalysisRequest, CommunicationPattern
from backend.type_defs.common import Metadata
from config import UnifiedConfigManager
from constants import PATH
from backend.constants.threshold_constants import TimingConstants
from autobot_shared.redis_client import RedisDatabase, get_redis_client
from backend.utils.system_metrics import get_metrics_collector

# Import existing monitoring infrastructure
from .monitoring_hardware import hardware_monitor

logger = logging.getLogger(__name__)

# Create singleton config instance
config = UnifiedConfigManager()

# Lock for thread-safe analytics state access
_analytics_state_lock = asyncio.Lock()

# Performance optimization: O(1) lookup for analysis type routing (Issue #326)
COMMUNICATION_CHAIN_ANALYSIS_TYPES = {"full", "communication_chains"}
CODE_INDEXING_ANALYSIS_TYPES = {"full", "incremental"}


# Simple service address function using configuration
def get_service_address(service_name: str, port: int, protocol: str = "http") -> str:
    """Get standardized service address from config helper"""
    try:
        host = config.get_host(service_name)
    except Exception:
        host = "localhost"
    return f"{protocol}://{host}:{port}"


# Global analytics state management (shared with analytics.py)
analytics_state = {
    "websocket_connections": set(),
    "api_call_patterns": [],
    "performance_history": [],
    "communication_chains": defaultdict(list),
    "code_analysis_cache": {},
    "last_analysis_time": None,
}


class AnalyticsController:
    """Core analytics controller with comprehensive monitoring capabilities"""

    def __init__(self):
        """Initialize analytics controller with Redis, metrics, and tracking."""
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
            db_name = (
                database.name.lower()
                if isinstance(database, RedisDatabase)
                else database
            )
            return await get_redis_client(async_client=True, database=db_name)
        except Exception as e:
            logger.error("Failed to get Redis connection for %s: %s", database, e)
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

        # Store in analytics state (thread-safe)
        async with _analytics_state_lock:
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
                call_data = json.dumps(
                    {
                        "endpoint": endpoint,
                        "response_time": response_time,
                        "status_code": status_code,
                        "timestamp": timestamp,
                    }
                )
                # Issue #483: Parallelize independent Redis operations
                await asyncio.gather(
                    redis_conn.lpush("analytics:api_calls", call_data),
                    redis_conn.ltrim("analytics:api_calls", 0, 9999),  # Keep last 10k
                    return_exceptions=True,
                )
        except Exception as e:
            logger.error("Failed to store API call analytics: %s", e)

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
            )
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

    async def perform_code_analysis(self, request: CodeAnalysisRequest) -> Metadata:
        """Perform code analysis using integrated tools"""
        analysis_results = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "analysis_type": request.analysis_type,
            "target_path": request.target_path,
        }

        try:
            # Check if code analysis tools are available
            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(self.code_analysis_path.exists):
                analysis_results["status"] = "error"
                analysis_results["error"] = "Code analysis suite not found"
                return analysis_results

            # Run code analysis suite
            if request.analysis_type in COMMUNICATION_CHAIN_ANALYSIS_TYPES:
                await self._run_code_analysis_suite(request, analysis_results)

            # Run code indexing if available
            # Issue #358 - avoid blocking
            code_index_exists = await asyncio.to_thread(self.code_index_path.exists)
            if (
                code_index_exists
                and request.analysis_type in CODE_INDEXING_ANALYSIS_TYPES
            ):
                await self._run_code_indexing(request, analysis_results)

            # Store results in cache (thread-safe)
            async with _analytics_state_lock:
                analytics_state["code_analysis_cache"] = analysis_results
                analytics_state["last_analysis_time"] = datetime.now().isoformat()

        except Exception as e:
            logger.error("Code analysis failed: %s", e)
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

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=TimingConstants.VERY_LONG_TIMEOUT
            )

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

            # Hardware performance from existing monitor (Issue #430: await async)
            gpu_status = await hardware_monitor.get_gpu_status()
            npu_status = await hardware_monitor.get_npu_status()

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
            logger.error("Failed to collect performance metrics: %s", e)
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

            # WebSocket usage (thread-safe access)
            async with _analytics_state_lock:
                active_ws_connections = len(analytics_state["websocket_connections"])
            stats["websocket_usage"] = {
                "active_connections": active_ws_connections,
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
            logger.error("Failed to get usage statistics: %s", e)
            stats["error"] = str(e)

        return stats

    async def detect_trends(self) -> Metadata:
        """Detect trends in system performance and usage"""
        trends = {}

        try:
            # Performance trends from history (thread-safe access)
            async with _analytics_state_lock:
                performance_history_copy = list(analytics_state["performance_history"])
                api_patterns_copy = list(analytics_state["api_call_patterns"])

            if performance_history_copy:
                recent_performance = performance_history_copy[-50:]

                # Calculate trends
                cpu_trend = self._calculate_trend(
                    [p.get("cpu_percent", 0) for p in recent_performance]
                )
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
            recent_calls = api_patterns_copy[-100:]
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
            logger.error("Failed to detect trends: %s", e)
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
