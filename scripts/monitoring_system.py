#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Monitoring and Alerting System for AutoBot
Provides comprehensive system monitoring, performance tracking, and alerting capabilities
"""

import asyncio
import json
import logging
import os
import sys

# Import configuration from centralized source
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import psutil

from src.constants import ServiceURLs

from src.constants.threshold_constants import TimingConstants
from src.config import API_BASE_URL

try:
    import aiohttp
    import aiofiles
except ImportError:
    # Use logging instead of print for package installation messages
    logging.warning("Installing required packages (aiohttp, aiofiles)...")
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "pip", "install", "aiohttp", "aiofiles"])
    import aiohttp
    import aiofiles

# Import centralized Redis client
from src.utils.redis_client import get_redis_client

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class SystemMonitor:
    """Comprehensive system monitoring with metrics collection"""

    def __init__(self, project_root: Path = None):
        """Initialize system monitor with project root and metrics database."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.reports_dir = self.project_root / "reports" / "monitoring"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Initialize metrics database
        self.metrics_db = self.reports_dir / "metrics.db"
        self._init_metrics_db()

        # Monitoring configuration
        self.config = {
            "collection_interval": 60,  # seconds
            "retention_days": 30,
            "alert_thresholds": {
                "cpu_usage": 80,
                "memory_usage": 85,
                "disk_usage": 90,
                "response_time": 5000,  # milliseconds
                "error_rate": 5,  # percentage
            },
        }

        self.alerts_triggered = []

    def _init_metrics_db(self):
        """Initialize metrics database"""
        with sqlite3.connect(self.metrics_db) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL,
                    memory_percent REAL,
                    memory_used_mb REAL,
                    disk_percent REAL,
                    disk_used_gb REAL,
                    network_sent_mb REAL,
                    network_recv_mb REAL,
                    process_count INTEGER,
                    load_average REAL
                );

                CREATE TABLE IF NOT EXISTS application_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    service_name TEXT,
                    response_time_ms REAL,
                    error_count INTEGER,
                    success_count INTEGER,
                    active_connections INTEGER,
                    memory_usage_mb REAL,
                    cpu_usage_percent REAL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    alert_type TEXT,
                    severity TEXT,
                    message TEXT,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_at DATETIME
                );

                CREATE TABLE IF NOT EXISTS health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    service_name TEXT,
                    endpoint TEXT,
                    status_code INTEGER,
                    response_time_ms REAL,
                    status TEXT,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON system_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_application_metrics_timestamp ON application_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
                CREATE INDEX IF NOT EXISTS idx_health_checks_timestamp ON health_checks(timestamp);
            """
            )

    def _collect_resource_metrics(self) -> Dict[str, Any]:
        """
        Collect CPU, memory, disk, and network metrics.

        Issue #665: Extracted from collect_system_metrics to reduce function length.
        """
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)

        # Memory metrics
        memory = psutil.virtual_memory()

        # Disk metrics
        disk = psutil.disk_usage("/")

        # Network metrics
        network = psutil.net_io_counters()

        # Load average (Unix-like systems)
        try:
            load_average = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
        except (AttributeError, OSError):
            load_average = 0.0

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_mb": memory.used / (1024**2),
            "disk_percent": (disk.used / disk.total) * 100,
            "disk_used_gb": disk.used / (1024**3),
            "network_sent_mb": network.bytes_sent / (1024**2),
            "network_recv_mb": network.bytes_recv / (1024**2),
            "process_count": len(psutil.pids()),
            "load_average": load_average,
        }

    def collect_system_metrics(self) -> Dict[str, Any]:
        """
        Collect comprehensive system metrics.

        Issue #665: Refactored to extract _collect_resource_metrics() helper,
        reducing function from 54 to ~20 lines.
        """
        try:
            # Issue #665: Use extracted helper for resource collection
            metrics = self._collect_resource_metrics()
            metrics["timestamp"] = datetime.now().isoformat()

            # Store in database
            self._store_system_metrics(metrics)

            # Check for alerts
            self._check_system_alerts(metrics)

            return metrics

        except Exception as e:
            logger.error("Failed to collect system metrics: %s", e)
            return {}

    def _store_system_metrics(self, metrics: Dict[str, Any]):
        """Store system metrics in database"""
        try:
            with sqlite3.connect(self.metrics_db) as conn:
                conn.execute(
                    """
                    INSERT INTO system_metrics (
                        cpu_percent, memory_percent, memory_used_mb, disk_percent,
                        disk_used_gb, network_sent_mb, network_recv_mb, process_count,
                        load_average
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        metrics["cpu_percent"],
                        metrics["memory_percent"],
                        metrics["memory_used_mb"],
                        metrics["disk_percent"],
                        metrics["disk_used_gb"],
                        metrics["network_sent_mb"],
                        metrics["network_recv_mb"],
                        metrics["process_count"],
                        metrics["load_average"],
                    ),
                )
        except Exception as e:
            logger.error("Failed to store system metrics: %s", e)

    def _check_system_alerts(self, metrics: Dict[str, Any]):
        """Check system metrics against alert thresholds"""
        alerts = []

        # CPU usage alert
        if metrics["cpu_percent"] > self.config["alert_thresholds"]["cpu_usage"]:
            alerts.append(
                {
                    "type": "high_cpu_usage",
                    "severity": "warning",
                    "message": f"CPU usage is {metrics['cpu_percent']:.1f}% (threshold: {self.config['alert_thresholds']['cpu_usage']}%)",
                }
            )

        # Memory usage alert
        if metrics["memory_percent"] > self.config["alert_thresholds"]["memory_usage"]:
            alerts.append(
                {
                    "type": "high_memory_usage",
                    "severity": "warning",
                    "message": f"Memory usage is {metrics['memory_percent']:.1f}% (threshold: {self.config['alert_thresholds']['memory_usage']}%)",
                }
            )

        # Disk usage alert
        if metrics["disk_percent"] > self.config["alert_thresholds"]["disk_usage"]:
            alerts.append(
                {
                    "type": "high_disk_usage",
                    "severity": "critical",
                    "message": f"Disk usage is {metrics['disk_percent']:.1f}% (threshold: {self.config['alert_thresholds']['disk_usage']}%)",
                }
            )

        # Store alerts
        for alert in alerts:
            self._store_alert(alert)
            self.alerts_triggered.append(alert)

    def _store_alert(self, alert: Dict[str, Any]):
        """Store alert in database"""
        try:
            with sqlite3.connect(self.metrics_db) as conn:
                conn.execute(
                    """
                    INSERT INTO alerts (alert_type, severity, message)
                    VALUES (?, ?, ?)
                """,
                    (alert["type"], alert["severity"], alert["message"]),
                )
        except Exception as e:
            logger.error("Failed to store alert: %s", e)

    async def collect_application_metrics(self) -> Dict[str, Any]:
        """Collect application-specific metrics"""
        metrics = {"timestamp": datetime.now().isoformat(), "services": {}}

        # Monitor AutoBot services
        services_to_monitor = [
            {
                "name": "backend",
                "url": f"{API_BASE_URL}/api/system/health",
                "port": 8001,
            },
            {"name": "frontend", "url": ServiceURLs.FRONTEND_VM, "port": 5173},  # FIXED: Frontend on VM1 (172.16.168.21)
            {"name": "redis", "url": None, "port": 6379},
        ]

        for service in services_to_monitor:
            service_metrics = await self._collect_service_metrics(service)
            metrics["services"][service["name"]] = service_metrics

        return metrics

    async def _check_http_service_health(
        self, url: str, service_name: str, service_metrics: Dict[str, Any]
    ) -> None:
        """
        Check HTTP service health and update metrics.

        Issue #665: Extracted from _collect_service_metrics to reduce function length.
        """
        start_time = time.time()
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.get(url) as response:
                    response_time = (time.time() - start_time) * 1000
                    service_metrics["response_time_ms"] = response_time

                    if response.status == 200:
                        service_metrics["status"] = "healthy"
                        service_metrics["success_count"] = 1
                    else:
                        service_metrics["status"] = "unhealthy"
                        service_metrics["error_count"] = 1

        except asyncio.TimeoutError:
            service_metrics["status"] = "timeout"
            service_metrics["error_count"] = 1
        except Exception as e:
            service_metrics["status"] = "error"
            service_metrics["error_count"] = 1
            logger.debug("Service %s health check failed: %s", service_name, e)

    async def _check_redis_health(self, service_metrics: Dict[str, Any]) -> None:
        """
        Check Redis service health and update metrics.

        Issue #665: Extracted from _collect_service_metrics to reduce function length.
        Issue #666: Fixed blocking I/O - use async Redis client in async context.
        """
        try:
            # Issue #666: Use async_client=True to avoid blocking the event loop
            r = await get_redis_client(async_client=True, database="main")
            if r:
                await r.ping()
                service_metrics["status"] = "healthy"
                service_metrics["success_count"] = 1
            else:
                service_metrics["status"] = "unhealthy"
                service_metrics["error_count"] = 1
        except Exception:
            service_metrics["status"] = "unhealthy"
            service_metrics["error_count"] = 1

    async def _collect_service_metrics(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect metrics for a specific service.

        Issue #665: Refactored to extract _check_http_service_health() and
        _check_redis_health() helpers, reducing function from 74 to ~30 lines.
        """
        service_name = service["name"]
        service_metrics = {
            "status": "unknown",
            "response_time_ms": 0,
            "error_count": 0,
            "success_count": 0,
            "memory_usage_mb": 0,
            "cpu_usage_percent": 0,
        }

        try:
            # Check if service is running on expected port
            if not self._check_port(service["port"]):
                service_metrics["status"] = "down"
                return service_metrics

            # Issue #665: Use extracted helper methods for specific service types
            if service["url"]:
                await self._check_http_service_health(
                    service["url"], service_name, service_metrics
                )
            elif service_name == "redis":
                # Issue #666: Now properly awaited since _check_redis_health is async
                await self._check_redis_health(service_metrics)

            # Try to get process-specific metrics
            service_metrics.update(self._get_process_metrics(service_name))

        except Exception as e:
            logger.error("Failed to collect metrics for %s: %s", service_name, e)
            service_metrics["status"] = "error"
            service_metrics["error_count"] = 1

        # Store application metrics
        self._store_application_metrics(service_name, service_metrics)

        return service_metrics

    def _check_port(self, port: int) -> bool:
        """Check if a port is open/listening"""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.status == "LISTEN":
                    return True
            return False
        except Exception:
            return False

    def _get_process_metrics(self, service_name: str) -> Dict[str, float]:
        """Get process-specific metrics"""
        metrics = {"memory_usage_mb": 0, "cpu_usage_percent": 0}

        try:
            # Find processes related to the service
            for process in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    proc_info = process.info
                    cmdline = (
                        " ".join(proc_info["cmdline"]) if proc_info["cmdline"] else ""
                    )

                    # Check if process is related to the service
                    if (
                        service_name.lower() in proc_info["name"].lower()
                        or service_name.lower() in cmdline.lower()
                        or (
                            service_name == "backend"
                            and ("uvicorn" in cmdline or "main.py" in cmdline)
                        )
                        or (
                            service_name == "frontend"
                            and ("vite" in cmdline or "dev" in cmdline)
                        )
                        or (
                            service_name == "redis"
                            and "redis-server" in proc_info["name"].lower()
                        )
                    ):
                        proc = psutil.Process(proc_info["pid"])
                        memory_info = proc.memory_info()
                        metrics["memory_usage_mb"] += memory_info.rss / (1024**2)
                        metrics["cpu_usage_percent"] += proc.cpu_percent()

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            logger.debug("Failed to get process metrics for %s: %s", service_name, e)

        return metrics

    def _store_application_metrics(self, service_name: str, metrics: Dict[str, Any]):
        """Store application metrics in database"""
        try:
            with sqlite3.connect(self.metrics_db) as conn:
                conn.execute(
                    """
                    INSERT INTO application_metrics (
                        service_name, response_time_ms, error_count, success_count,
                        memory_usage_mb, cpu_usage_percent
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        service_name,
                        metrics["response_time_ms"],
                        metrics["error_count"],
                        metrics["success_count"],
                        metrics["memory_usage_mb"],
                        metrics["cpu_usage_percent"],
                    ),
                )
        except Exception as e:
            logger.error("Failed to store application metrics: %s", e)

    def _get_health_check_endpoints(self) -> list:
        """
        Get list of health check endpoint definitions.

        Issue #665: Extracted from perform_health_checks to reduce function length.
        """
        return [
            {
                "service": "backend",
                "endpoint": "/api/system/health",
                "url": "ServiceURLs.BACKEND_LOCAL/api/system/health",
            },
            {
                "service": "backend",
                "endpoint": "/api/system/status",
                "url": "ServiceURLs.BACKEND_LOCAL/api/system/status",
            },
            {
                "service": "backend",
                "endpoint": "/api/chat_knowledge/health",
                "url": "ServiceURLs.BACKEND_LOCAL/api/chat_knowledge/health",
            },
            {"service": "redis", "endpoint": "ping", "url": None},
        ]

    def _process_health_check_result(
        self,
        check: Dict[str, Any],
        result: Dict[str, Any],
        health_results: Dict[str, Any],
    ) -> None:
        """
        Process a single health check result and update aggregated results.

        Issue #665: Extracted from perform_health_checks to reduce function length.
        """
        service_name = check["service"]
        if service_name not in health_results["services"]:
            health_results["services"][service_name] = {
                "status": "healthy",
                "checks": [],
                "issues": [],
            }

        health_results["services"][service_name]["checks"].append(result)

        if result["status"] != "healthy":
            health_results["services"][service_name]["status"] = "unhealthy"
            health_results["overall_status"] = "unhealthy"

            issue = f"{service_name} {check['endpoint']}: {result.get('error_message', 'Unknown error')}"
            health_results["services"][service_name]["issues"].append(issue)
            health_results["issues"].append(issue)

    async def perform_health_checks(self) -> Dict[str, Any]:
        """
        Perform comprehensive health checks.

        Issue #665: Refactored to extract _get_health_check_endpoints() and
        _process_health_check_result() helpers, reducing function from 56 to ~20 lines.
        """
        logger.info("🏥 Performing health checks...")

        health_results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "services": {},
            "issues": [],
        }

        # Issue #665: Use extracted helper for endpoint definitions
        for check in self._get_health_check_endpoints():
            result = await self._perform_single_health_check(check)
            self._process_health_check_result(check, result, health_results)

        # Store health check results
        self._store_health_check_results(health_results)

        return health_results

    async def _perform_single_health_check(
        self, check: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform a single health check"""
        result = {
            "service": check["service"],
            "endpoint": check["endpoint"],
            "status": "healthy",
            "response_time_ms": 0,
            "error_message": None,
        }

        try:
            start_time = time.time()

            if check["url"]:
                # HTTP health check
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as session:
                    async with session.get(check["url"]) as response:
                        result["response_time_ms"] = (time.time() - start_time) * 1000

                        if response.status == 200:
                            result["status"] = "healthy"
                        else:
                            result["status"] = "unhealthy"
                            result["error_message"] = f"HTTP {response.status}"

            elif check["service"] == "redis" and check["endpoint"] == "ping":
                # Issue #666: Fixed blocking I/O - use async Redis client
                r = await get_redis_client(async_client=True, database="main")
                if r:
                    await r.ping()
                    result["response_time_ms"] = (time.time() - start_time) * 1000
                    result["status"] = "healthy"
                else:
                    result["status"] = "unhealthy"
                    result["error_message"] = "Failed to get Redis client"

        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["error_message"] = "Request timeout"
        except Exception as e:
            result["status"] = "error"
            result["error_message"] = str(e)

        return result

    def _store_health_check_results(self, health_results: Dict[str, Any]):
        """Store health check results in database.

        Issue #663: Uses executemany for batch insert to eliminate N+1 pattern.
        """
        try:
            # Issue #663: Collect all checks into a list for batch insert
            check_rows = []
            for service_name, service_data in health_results["services"].items():
                for check in service_data["checks"]:
                    check_rows.append((
                        check["service"],
                        check["endpoint"],
                        200 if check["status"] == "healthy" else 500,
                        check["response_time_ms"],
                        check["status"],
                        check["error_message"],
                    ))

            # Issue #663: Single executemany call instead of N individual inserts
            if check_rows:
                with sqlite3.connect(self.metrics_db) as conn:
                    conn.executemany(
                        """
                        INSERT INTO health_checks (
                            service_name, endpoint, status_code, response_time_ms, status, error_message
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        check_rows,
                    )
        except Exception as e:
            logger.error("Failed to store health check results: %s", e)

    def _query_system_overview(self, conn) -> dict:
        """
        Query system overview metrics for last 24 hours.

        Issue #281: Extracted from generate_monitoring_dashboard to reduce function length.
        """
        cursor = conn.execute(
            """
            SELECT
                AVG(cpu_percent) as avg_cpu,
                AVG(memory_percent) as avg_memory,
                AVG(disk_percent) as avg_disk,
                MAX(cpu_percent) as max_cpu,
                MAX(memory_percent) as max_memory,
                COUNT(*) as data_points
            FROM system_metrics
            WHERE timestamp > datetime('now', '-24 hours')
        """
        )
        row = cursor.fetchone()
        if row:
            return {
                "avg_cpu_percent": round(row[0] or 0, 2),
                "avg_memory_percent": round(row[1] or 0, 2),
                "avg_disk_percent": round(row[2] or 0, 2),
                "max_cpu_percent": round(row[3] or 0, 2),
                "max_memory_percent": round(row[4] or 0, 2),
                "data_points": row[5] or 0,
            }
        return {}

    def _query_service_status(self, conn) -> dict:
        """
        Query service status metrics for last hour.

        Issue #281: Extracted from generate_monitoring_dashboard to reduce function length.
        """
        cursor = conn.execute(
            """
            SELECT
                service_name,
                AVG(response_time_ms) as avg_response_time,
                SUM(error_count) as total_errors,
                SUM(success_count) as total_successes,
                AVG(memory_usage_mb) as avg_memory
            FROM application_metrics
            WHERE timestamp > datetime('now', '-1 hour')
            GROUP BY service_name
        """
        )
        status = {}
        for row in cursor.fetchall():
            service_name = row[0]
            status[service_name] = {
                "avg_response_time_ms": round(row[1] or 0, 2),
                "total_errors": row[2] or 0,
                "total_successes": row[3] or 0,
                "avg_memory_mb": round(row[4] or 0, 2),
                "error_rate": round(
                    (row[2] or 0) / max((row[2] or 0) + (row[3] or 0), 1) * 100, 2
                ),
            }
        return status

    def _query_recent_alerts(self, conn) -> list:
        """
        Query recent alerts from last 24 hours.

        Issue #281: Extracted from generate_monitoring_dashboard to reduce function length.
        """
        cursor = conn.execute(
            """
            SELECT alert_type, severity, message, timestamp
            FROM alerts
            WHERE timestamp > datetime('now', '-24 hours')
            ORDER BY timestamp DESC
            LIMIT 10
        """
        )
        return [
            {
                "type": row[0],
                "severity": row[1],
                "message": row[2],
                "timestamp": row[3],
            }
            for row in cursor.fetchall()
        ]

    def _query_performance_trends(self, conn) -> list:
        """
        Query performance trends for last 7 days.

        Issue #281: Extracted from generate_monitoring_dashboard to reduce function length.
        """
        cursor = conn.execute(
            """
            SELECT
                strftime('%Y-%m-%d %H:00:00', sm.timestamp) as hour,
                AVG(sm.cpu_percent) as avg_cpu,
                AVG(sm.memory_percent) as avg_memory,
                AVG(am.response_time_ms) as avg_response_time
            FROM system_metrics sm
            LEFT JOIN (
                SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hour_group,
                       AVG(response_time_ms) as response_time_ms
                FROM application_metrics
                WHERE timestamp > datetime('now', '-7 days')
                GROUP BY strftime('%Y-%m-%d %H:00:00', timestamp)
            ) am ON strftime('%Y-%m-%d %H:00:00', sm.timestamp) = am.hour_group
            WHERE sm.timestamp > datetime('now', '-7 days')
            GROUP BY strftime('%Y-%m-%d %H:00:00', sm.timestamp)
            ORDER BY hour
        """
        )
        trends = []
        for row in cursor.fetchall():
            trends.append({
                "hour": row[0],
                "cpu_percent": round(row[1] or 0, 2),
                "memory_percent": round(row[2] or 0, 2),
                "response_time_ms": round(row[3] or 0, 2),
            })
        return trends[-24:]  # Last 24 hours

    def generate_monitoring_dashboard(self) -> Dict[str, Any]:
        """
        Generate monitoring dashboard data.

        Issue #281: Extracted queries to _query_system_overview(), _query_service_status(),
        _query_recent_alerts(), and _query_performance_trends() to reduce function length
        from 129 to ~25 lines.
        """
        logger.info("📊 Generating monitoring dashboard...")

        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "system_overview": {},
            "service_status": {},
            "recent_alerts": [],
            "performance_trends": {},
            "health_summary": {},
        }

        try:
            with sqlite3.connect(self.metrics_db) as conn:
                # Issue #281: Use extracted query helpers
                dashboard["system_overview"] = self._query_system_overview(conn)
                dashboard["service_status"] = self._query_service_status(conn)
                dashboard["recent_alerts"] = self._query_recent_alerts(conn)
                dashboard["performance_trends"] = self._query_performance_trends(conn)

        except Exception as e:
            logger.error("Failed to generate dashboard data: %s", e)

        return dashboard

    def _delete_old_records(
        self, conn, table_name: str, retention_date: datetime
    ) -> int:
        """
        Delete old records from a specific table.

        Issue #665: Extracted from cleanup_old_metrics to reduce duplication.
        """
        result = conn.execute(
            f"DELETE FROM {table_name} WHERE timestamp < ?",
            (retention_date.isoformat(),),
        )
        return result.rowcount

    def cleanup_old_metrics(self):
        """
        Clean up old metrics data.

        Issue #665: Refactored to extract _delete_old_records() helper,
        reducing function from 59 to ~25 lines.
        """
        logger.info("🧹 Cleaning up old metrics...")

        retention_date = datetime.now() - timedelta(days=self.config["retention_days"])
        alert_retention_date = datetime.now() - timedelta(days=90)

        try:
            with sqlite3.connect(self.metrics_db) as conn:
                # Issue #665: Use extracted helper for consistent cleanup
                deleted_system = self._delete_old_records(
                    conn, "system_metrics", retention_date
                )
                deleted_app = self._delete_old_records(
                    conn, "application_metrics", retention_date
                )
                deleted_health = self._delete_old_records(
                    conn, "health_checks", retention_date
                )
                # Alerts have longer retention (90 days)
                deleted_alerts = self._delete_old_records(
                    conn, "alerts", alert_retention_date
                )

                logger.info(
                    f"Cleaned up {deleted_system} system metrics, {deleted_app} app metrics, "
                    f"{deleted_health} health checks, {deleted_alerts} alerts"
                )

        except Exception as e:
            logger.error("Failed to cleanup old metrics: %s", e)

    async def run_monitoring_cycle(self):
        """Run a complete monitoring cycle"""
        logger.info("🚀 Running monitoring cycle...")

        try:
            # Collect system metrics
            system_metrics = self.collect_system_metrics()
            logger.info(
                f"📊 System: CPU {system_metrics.get('cpu_percent', 0):.1f}%, Memory {system_metrics.get('memory_percent', 0):.1f}%"
            )

            # Collect application metrics
            app_metrics = await self.collect_application_metrics()
            logger.info("🔧 Services: %s", len(app_metrics.get('services', {})))

            # Perform health checks
            health_results = await self.perform_health_checks()
            logger.info("🏥 Health: %s", health_results.get('overall_status', 'unknown'))

            # Generate dashboard
            dashboard = self.generate_monitoring_dashboard()

            # Save dashboard data
            # Issue #666: Fixed blocking I/O - use aiofiles for async file write
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dashboard_file = self.reports_dir / f"dashboard_{timestamp}.json"
            async with aiofiles.open(dashboard_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(dashboard, indent=2, ensure_ascii=False))

            # Check for alerts
            if self.alerts_triggered:
                logger.warning(
                    f"⚠️  {len(self.alerts_triggered)} alerts triggered this cycle"
                )
                for alert in self.alerts_triggered:
                    logger.warning(
                        f"  • {alert['severity'].upper()}: {alert['message']}"
                    )
                self.alerts_triggered.clear()

            return {
                "system_metrics": system_metrics,
                "application_metrics": app_metrics,
                "health_results": health_results,
                "dashboard": dashboard,
            }

        except Exception as e:
            logger.error("Monitoring cycle failed: %s", e)
            return {}

    async def start_monitoring(self, continuous: bool = False):
        """Start monitoring system"""
        logger.info("🎯 Starting AutoBot monitoring system...")

        if continuous:
            logger.info(
                f"📡 Continuous monitoring every {self.config['collection_interval']} seconds"
            )

            while True:
                try:
                    await self.run_monitoring_cycle()
                    await asyncio.sleep(self.config["collection_interval"])

                    # Cleanup old data periodically (every 24 hours)
                    if datetime.now().hour == 2 and datetime.now().minute < 5:  # 2 AM
                        self.cleanup_old_metrics()

                except KeyboardInterrupt:
                    logger.info("🛑 Monitoring stopped by user")
                    break
                except Exception as e:
                    logger.error("Monitoring error: %s", e)
                    await asyncio.sleep(TimingConstants.ERROR_RECOVERY_LONG_DELAY)  # Wait before retrying
        else:
            # Single monitoring cycle
            results = await self.run_monitoring_cycle()
            return results


async def main():
    """Main entry point"""
    try:
        monitor = SystemMonitor()

        # Run single monitoring cycle for testing
        results = await monitor.start_monitoring(continuous=False)

        if results:
            logger.info("✅ Monitoring cycle completed successfully")

            # Print summary
            system = results.get("system_metrics", {})
            health = results.get("health_results", {})

            print("\n" + "=" * 60)
            print("📊 AUTOBOT MONITORING SUMMARY")
            print("=" * 60)
            print("⚡ System Status:")
            print(f"  • CPU Usage: {system.get('cpu_percent', 0):.1f}%")
            print(f"  • Memory Usage: {system.get('memory_percent', 0):.1f}%")
            print(f"  • Disk Usage: {system.get('disk_percent', 0):.1f}%")

            print(
                f"\n🏥 Health Status: {health.get('overall_status', 'unknown').upper()}"
            )

            services = health.get("services", {})
            for service_name, service_data in services.items():
                status = service_data.get("status", "unknown")
                print(f"  • {service_name}: {status.upper()}")

            if health.get("issues"):
                print("\n⚠️  Issues Detected:")
                for issue in health["issues"]:
                    print(f"  • {issue}")

            print("=" * 60)
        else:
            logger.error("❌ Monitoring cycle failed")
            return 1

        return 0

    except Exception as e:
        logger.error("Monitoring system failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
