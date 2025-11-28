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

from src.unified_config import API_BASE_URL

try:
    import aiohttp
except ImportError:
    print("Installing required packages...")
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "pip", "install", "aiohttp"])
    import aiohttp

# Import centralized Redis client
from src.utils.redis_client import get_redis_client

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class SystemMonitor:
    """Comprehensive system monitoring with metrics collection"""

    def __init__(self, project_root: Path = None):
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

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024**2)

            # Disk metrics
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            disk_used_gb = disk.used / (1024**3)

            # Network metrics
            network = psutil.net_io_counters()
            network_sent_mb = network.bytes_sent / (1024**2)
            network_recv_mb = network.bytes_recv / (1024**2)

            # Process metrics
            process_count = len(psutil.pids())

            # Load average (Unix-like systems)
            try:
                load_average = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
            except (AttributeError, OSError):
                load_average = 0.0

            metrics = {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_used_mb": memory_used_mb,
                "disk_percent": disk_percent,
                "disk_used_gb": disk_used_gb,
                "network_sent_mb": network_sent_mb,
                "network_recv_mb": network_recv_mb,
                "process_count": process_count,
                "load_average": load_average,
            }

            # Store in database
            self._store_system_metrics(metrics)

            # Check for alerts
            self._check_system_alerts(metrics)

            return metrics

        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
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
            logger.error(f"Failed to store system metrics: {e}")

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
            logger.error(f"Failed to store alert: {e}")

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

    async def _collect_service_metrics(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Collect metrics for a specific service"""
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
            port_open = self._check_port(service["port"])

            if not port_open:
                service_metrics["status"] = "down"
                return service_metrics

            # For HTTP services, make health check request
            if service["url"]:
                start_time = time.time()
                try:
                    async with aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as session:
                        async with session.get(service["url"]) as response:
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
                    logger.debug(f"Service {service_name} health check failed: {e}")

            # For Redis, try connection using canonical client
            elif service_name == "redis":
                try:
                    # Use canonical get_redis_client() for production Redis VM
                    r = get_redis_client(async_client=False, database="main")
                    if r:
                        r.ping()
                        service_metrics["status"] = "healthy"
                        service_metrics["success_count"] = 1
                    else:
                        service_metrics["status"] = "unhealthy"
                        service_metrics["error_count"] = 1
                except Exception:
                    service_metrics["status"] = "unhealthy"
                    service_metrics["error_count"] = 1

            # Try to get process-specific metrics
            service_metrics.update(self._get_process_metrics(service_name))

        except Exception as e:
            logger.error(f"Failed to collect metrics for {service_name}: {e}")
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
            logger.debug(f"Failed to get process metrics for {service_name}: {e}")

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
            logger.error(f"Failed to store application metrics: {e}")

    async def perform_health_checks(self) -> Dict[str, Any]:
        """Perform comprehensive health checks"""
        logger.info("🏥 Performing health checks...")

        health_results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "services": {},
            "issues": [],
        }

        # Define health check endpoints
        health_checks = [
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

        for check in health_checks:
            result = await self._perform_single_health_check(check)

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
                # Redis health check - use canonical client for central Redis VM
                r = get_redis_client(async_client=False, database="main")
                if r:
                    r.ping()
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
        """Store health check results in database"""
        try:
            with sqlite3.connect(self.metrics_db) as conn:
                for service_name, service_data in health_results["services"].items():
                    for check in service_data["checks"]:
                        conn.execute(
                            """
                            INSERT INTO health_checks (
                                service_name, endpoint, status_code, response_time_ms, status, error_message
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                            (
                                check["service"],
                                check["endpoint"],
                                200 if check["status"] == "healthy" else 500,
                                check["response_time_ms"],
                                check["status"],
                                check["error_message"],
                            ),
                        )
        except Exception as e:
            logger.error(f"Failed to store health check results: {e}")

    def generate_monitoring_dashboard(self) -> Dict[str, Any]:
        """Generate monitoring dashboard data"""
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
                # System overview (last 24 hours)
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
                    dashboard["system_overview"] = {
                        "avg_cpu_percent": round(row[0] or 0, 2),
                        "avg_memory_percent": round(row[1] or 0, 2),
                        "avg_disk_percent": round(row[2] or 0, 2),
                        "max_cpu_percent": round(row[3] or 0, 2),
                        "max_memory_percent": round(row[4] or 0, 2),
                        "data_points": row[5] or 0,
                    }

                # Service status (last hour)
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

                for row in cursor.fetchall():
                    service_name = row[0]
                    dashboard["service_status"][service_name] = {
                        "avg_response_time_ms": round(row[1] or 0, 2),
                        "total_errors": row[2] or 0,
                        "total_successes": row[3] or 0,
                        "avg_memory_mb": round(row[4] or 0, 2),
                        "error_rate": round(
                            (row[2] or 0) / max((row[2] or 0) + (row[3] or 0), 1) * 100,
                            2,
                        ),
                    }

                # Recent alerts (last 24 hours)
                cursor = conn.execute(
                    """
                    SELECT alert_type, severity, message, timestamp
                    FROM alerts
                    WHERE timestamp > datetime('now', '-24 hours')
                    ORDER BY timestamp DESC
                    LIMIT 10
                """
                )

                dashboard["recent_alerts"] = [
                    {
                        "type": row[0],
                        "severity": row[1],
                        "message": row[2],
                        "timestamp": row[3],
                    }
                    for row in cursor.fetchall()
                ]

                # Performance trends (last 7 days, hourly averages)
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
                    trends.append(
                        {
                            "hour": row[0],
                            "cpu_percent": round(row[1] or 0, 2),
                            "memory_percent": round(row[2] or 0, 2),
                            "response_time_ms": round(row[3] or 0, 2),
                        }
                    )

                dashboard["performance_trends"] = trends[-24:]  # Last 24 hours

        except Exception as e:
            logger.error(f"Failed to generate dashboard data: {e}")

        return dashboard

    def cleanup_old_metrics(self):
        """Clean up old metrics data"""
        logger.info("🧹 Cleaning up old metrics...")

        retention_date = datetime.now() - timedelta(days=self.config["retention_days"])

        try:
            with sqlite3.connect(self.metrics_db) as conn:
                # Clean up old system metrics
                result = conn.execute(
                    """
                    DELETE FROM system_metrics
                    WHERE timestamp < ?
                """,
                    (retention_date.isoformat(),),
                )

                deleted_system = result.rowcount

                # Clean up old application metrics
                result = conn.execute(
                    """
                    DELETE FROM application_metrics
                    WHERE timestamp < ?
                """,
                    (retention_date.isoformat(),),
                )

                deleted_app = result.rowcount

                # Clean up old health checks
                result = conn.execute(
                    """
                    DELETE FROM health_checks
                    WHERE timestamp < ?
                """,
                    (retention_date.isoformat(),),
                )

                deleted_health = result.rowcount

                # Keep alerts for longer (90 days)
                alert_retention_date = datetime.now() - timedelta(days=90)
                result = conn.execute(
                    """
                    DELETE FROM alerts
                    WHERE timestamp < ?
                """,
                    (alert_retention_date.isoformat(),),
                )

                deleted_alerts = result.rowcount

                logger.info(
                    f"Cleaned up {deleted_system} system metrics, {deleted_app} app metrics, {deleted_health} health checks, {deleted_alerts} alerts"
                )

        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")

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
            logger.info(f"🔧 Services: {len(app_metrics.get('services', {}))}")

            # Perform health checks
            health_results = await self.perform_health_checks()
            logger.info(f"🏥 Health: {health_results.get('overall_status', 'unknown')}")

            # Generate dashboard
            dashboard = self.generate_monitoring_dashboard()

            # Save dashboard data
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dashboard_file = self.reports_dir / f"dashboard_{timestamp}.json"
            with open(dashboard_file, "w") as f:
                json.dump(dashboard, f, indent=2)

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
            logger.error(f"Monitoring cycle failed: {e}")
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
                    logger.error(f"Monitoring error: {e}")
                    await asyncio.sleep(30)  # Wait before retrying
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
            print(f"⚡ System Status:")
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
                print(f"\n⚠️  Issues Detected:")
                for issue in health["issues"]:
                    print(f"  • {issue}")

            print("=" * 60)
        else:
            logger.error("❌ Monitoring cycle failed")
            return 1

        return 0

    except Exception as e:
        logger.error(f"Monitoring system failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
