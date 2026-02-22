#!/usr/bin/env python3
"""
AutoBot Comprehensive Monitoring Controller
Central controller for all monitoring systems - integrates performance monitoring,
AI analytics, business intelligence, and APM systems.
"""

import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from advanced_apm_system import AdvancedAPMSystem
from ai_performance_analytics import AIPerformanceAnalytics
from business_intelligence_dashboard import BusinessIntelligenceDashboard

# Import monitoring components
from performance_monitor import ALERT_THRESHOLDS, PerformanceMonitor

logger = logging.getLogger(__name__)


class ComprehensiveMonitoringController:
    """Central controller for AutoBot's comprehensive monitoring system."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.setup_logging()

        # Initialize monitoring components
        self.performance_monitor = PerformanceMonitor()
        self.ai_analytics = AIPerformanceAnalytics()
        self.bi_dashboard = BusinessIntelligenceDashboard()
        self.apm_system = AdvancedAPMSystem()

        # Control flags
        self.monitoring_active = False
        self.shutdown_requested = False

        # Monitoring intervals (seconds)
        self.intervals = {
            "performance": 30,  # Basic system monitoring
            "ai_analytics": 60,  # AI performance analysis
            "bi_dashboard": 300,  # Business intelligence (5 minutes)
            "apm_reporting": 120,  # APM reporting (2 minutes)
        }

        # Results storage
        self.monitoring_results = {}
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.reports_path = Path(_base) / "reports" / "performance"
        self.reports_path.mkdir(parents=True, exist_ok=True)

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def setup_logging(self):
        """Setup comprehensive logging for monitoring controller."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(
                    os.path.join(
                        os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"),
                        "logs/monitoring_controller.log",
                    )
                ),
            ],
        )

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True

    async def initialize_all_systems(self):
        """Initialize all monitoring systems."""
        self.logger.info("🚀 Initializing comprehensive monitoring systems...")

        try:
            # Initialize Redis connections for all systems
            await self.performance_monitor.initialize_redis_connection()
            await self.ai_analytics.initialize_redis_connection()
            await self.bi_dashboard.initialize_redis_connection()
            await self.apm_system.initialize_redis_connection()

            self.logger.info("✅ All monitoring systems initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize monitoring systems: {e}")
            return False

    async def start_comprehensive_monitoring(self):
        """Start all monitoring systems in coordinated fashion."""
        if not await self.initialize_all_systems():
            return

        self.logger.info("🎯 Starting comprehensive monitoring...")
        self.monitoring_active = True

        try:
            # Start monitoring tasks concurrently
            tasks = [
                asyncio.create_task(self._performance_monitoring_loop()),
                asyncio.create_task(self._ai_analytics_loop()),
                asyncio.create_task(self._bi_dashboard_loop()),
                asyncio.create_task(self._apm_monitoring_loop()),
                asyncio.create_task(self._consolidated_reporting_loop()),
            ]

            # Wait for all tasks or shutdown signal
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self.logger.error(f"Error in comprehensive monitoring: {e}")
        finally:
            self.monitoring_active = False
            self.logger.info("🛑 Comprehensive monitoring stopped")

    async def _performance_monitoring_loop(self):
        """Performance monitoring loop."""
        self.logger.info("📊 Starting performance monitoring loop")

        while self.monitoring_active and not self.shutdown_requested:
            try:
                start_time = time.time()

                # Generate performance report
                performance_report = (
                    await self.performance_monitor.generate_performance_report()
                )
                self.monitoring_results["performance"] = performance_report

                # Log summary
                sys_metrics = performance_report.get("system")
                if sys_metrics:
                    self.logger.info(
                        f"📊 Performance: CPU={sys_metrics.cpu_percent:.1f}% "
                        f"MEM={sys_metrics.memory_percent:.1f}% "
                        f"DISK={sys_metrics.disk_percent:.1f}%"
                    )

                # Check for alerts
                alerts = performance_report.get("alerts", [])
                if alerts:
                    for alert in alerts[:3]:  # Show first 3 alerts
                        self.logger.warning(f"🚨 PERF ALERT: {alert}")

                # Calculate sleep time to maintain interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.intervals["performance"] - elapsed)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"Error in performance monitoring loop: {e}")
                await asyncio.sleep(self.intervals["performance"])

    async def _ai_analytics_loop(self):
        """AI analytics monitoring loop."""
        self.logger.info("🤖 Starting AI analytics loop")

        while self.monitoring_active and not self.shutdown_requested:
            try:
                start_time = time.time()

                # Generate AI performance report
                ai_report = await self.ai_analytics.generate_ai_performance_report()
                self.monitoring_results["ai_analytics"] = ai_report

                # Log AI metrics summary
                npu_metrics = ai_report.get("npu_metrics")
                if npu_metrics:
                    self.logger.info(
                        f"🤖 AI Performance: NPU={npu_metrics.utilization_percent:.1f}% "
                        f"Latency={npu_metrics.inference_latency_ms:.1f}ms"
                    )

                hardware_efficiency = ai_report.get("hardware_efficiency", {})
                if hardware_efficiency:
                    self.logger.info(
                        f"🔧 Hardware Efficiency: {hardware_efficiency.get('inference_performance', 'unknown')}"
                    )

                # Calculate sleep time
                elapsed = time.time() - start_time
                sleep_time = max(0, self.intervals["ai_analytics"] - elapsed)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"Error in AI analytics loop: {e}")
                await asyncio.sleep(self.intervals["ai_analytics"])

    async def _bi_dashboard_loop(self):
        """Business intelligence dashboard loop."""
        self.logger.info("💼 Starting BI dashboard loop")

        while self.monitoring_active and not self.shutdown_requested:
            try:
                start_time = time.time()

                # Generate BI dashboard report
                bi_report = (
                    await self.bi_dashboard.generate_comprehensive_dashboard_report()
                )
                self.monitoring_results["bi_dashboard"] = bi_report

                # Log BI summary
                summary = bi_report.get("summary", {})
                if summary:
                    self.logger.info(
                        f"💼 BI Dashboard: Health={summary.get('overall_health_score', 0):.1f}/100 "
                        f"ROI={summary.get('total_roi_percent', 0):.1f}% "
                        f"Cost=${summary.get('monthly_operational_cost', 0):.0f}/month"
                    )

                # Calculate sleep time
                elapsed = time.time() - start_time
                sleep_time = max(0, self.intervals["bi_dashboard"] - elapsed)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"Error in BI dashboard loop: {e}")
                await asyncio.sleep(self.intervals["bi_dashboard"])

    async def _apm_monitoring_loop(self):
        """APM monitoring loop."""
        self.logger.info("🔍 Starting APM monitoring loop")

        while self.monitoring_active and not self.shutdown_requested:
            try:
                start_time = time.time()

                # Generate APM report
                apm_report = await self.apm_system.generate_apm_report()
                self.monitoring_results["apm"] = apm_report

                # Log APM summary
                summary = apm_report.get("summary", {})
                api_perf = summary.get("api_performance", {})
                alerting = summary.get("alerting", {})

                if api_perf:
                    self.logger.info(
                        f"🔍 APM: API_Requests={api_perf.get('total_requests', 0)} "
                        f"Avg_Response={api_perf.get('average_response_time', 0):.1f}ms "
                        f"Error_Rate={api_perf.get('error_rate', 0):.1f}%"
                    )

                if alerting.get("active_alerts", 0) > 0:
                    self.logger.warning(
                        f"🚨 APM ALERTS: {alerting['active_alerts']} active "
                        f"({alerting.get('critical_alerts', 0)} critical)"
                    )

                # Calculate sleep time
                elapsed = time.time() - start_time
                sleep_time = max(0, self.intervals["apm_reporting"] - elapsed)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"Error in APM monitoring loop: {e}")
                await asyncio.sleep(self.intervals["apm_reporting"])

    async def _consolidated_reporting_loop(self):
        """Consolidated reporting loop - generates master reports."""
        self.logger.info("📋 Starting consolidated reporting loop")

        while self.monitoring_active and not self.shutdown_requested:
            try:
                # Generate consolidated report every 10 minutes
                await asyncio.sleep(600)

                if not self.monitoring_active:
                    break

                await self._generate_consolidated_report()

            except Exception as e:
                self.logger.error(f"Error in consolidated reporting loop: {e}")
                await asyncio.sleep(600)

    async def _generate_consolidated_report(self):
        """Generate consolidated monitoring report."""
        try:
            self.logger.info("📋 Generating consolidated monitoring report...")

            timestamp = datetime.now(timezone.utc).isoformat()

            # Compile all monitoring data
            consolidated_report = {
                "timestamp": timestamp,
                "system_overview": await self._generate_system_overview(),
                "performance_summary": self.monitoring_results.get("performance", {}),
                "ai_analytics_summary": self.monitoring_results.get("ai_analytics", {}),
                "business_intelligence": self.monitoring_results.get(
                    "bi_dashboard", {}
                ),
                "apm_summary": self.monitoring_results.get("apm", {}),
                "overall_health_assessment": await self._assess_overall_health(),
                "recommendations": await self._generate_recommendations(),
            }

            # Store consolidated report
            await self._store_consolidated_report(consolidated_report)

            self.logger.info("✅ Consolidated report generated successfully")

        except Exception as e:
            self.logger.error(f"Error generating consolidated report: {e}")

    async def _generate_system_overview(self) -> Dict[str, Any]:
        """Generate high-level system overview."""
        try:
            overview = {
                "monitoring_duration": "ongoing",
                "systems_monitored": {
                    "vm_count": 6,
                    "services_count": len(
                        [
                            "backend",
                            "frontend",
                            "npu-worker",
                            "ai-stack",
                            "browser",
                            "redis",
                            "ollama",
                        ]
                    ),
                    "databases_monitored": 6,  # Redis databases
                    "hardware_components": ["CPU", "GPU", "NPU", "Memory", "Storage"],
                },
                "monitoring_systems": {
                    "performance_monitor": "active",
                    "ai_analytics": "active",
                    "bi_dashboard": "active",
                    "apm_system": "active",
                },
            }

            return overview

        except Exception as e:
            self.logger.error(f"Error generating system overview: {e}")
            return {}

    async def _assess_overall_health(self) -> Dict[str, Any]:
        """Assess overall system health across all monitoring systems."""
        try:
            health_scores = []

            # Get health from BI dashboard
            bi_data = self.monitoring_results.get("bi_dashboard", {})
            bi_health = bi_data.get("system_health", {})
            if bi_health:
                health_scores.append(bi_health.get("overall_score", 0))

            # Get health from performance monitoring
            perf_data = self.monitoring_results.get("performance", {})
            alerts = perf_data.get("alerts", [])
            perf_health = max(0, 100 - len(alerts) * 15)  # Reduce score by 15 per alert
            health_scores.append(perf_health)

            # Get health from APM
            apm_data = self.monitoring_results.get("apm", {})
            apm_summary = apm_data.get("summary", {})
            apm_health = 100 if apm_summary.get("system_health") == "healthy" else 70
            health_scores.append(apm_health)

            # Calculate overall health
            if health_scores:
                overall_health = sum(health_scores) / len(health_scores)
            else:
                overall_health = 0

            # Determine health status
            if overall_health >= 90:
                status = "excellent"
            elif overall_health >= 75:
                status = "good"
            elif overall_health >= 60:
                status = "fair"
            else:
                status = "poor"

            return {
                "overall_score": round(overall_health, 1),
                "status": status,
                "component_scores": {
                    "bi_dashboard": (
                        bi_health.get("overall_score", 0) if bi_health else 0
                    ),
                    "performance": perf_health,
                    "apm": apm_health,
                },
                "critical_issues": len([a for a in alerts if "CRITICAL" in a.upper()]),
                "total_alerts": len(alerts),
            }

        except Exception as e:
            self.logger.error(f"Error assessing overall health: {e}")
            return {"overall_score": 0, "status": "unknown"}

    async def _generate_recommendations(self) -> List[str]:
        """Generate system recommendations based on monitoring data."""
        recommendations = []

        try:
            # Performance-based recommendations - use thresholds from config
            cpu_threshold = ALERT_THRESHOLDS.get("cpu_percent", 80.0)
            memory_threshold = ALERT_THRESHOLDS.get("memory_percent", 85.0)

            perf_data = self.monitoring_results.get("performance", {})
            sys_metrics = perf_data.get("system")
            if sys_metrics:
                if (
                    hasattr(sys_metrics, "cpu_percent")
                    and sys_metrics.cpu_percent > cpu_threshold
                ):
                    recommendations.append(
                        "CPU utilization high - consider workload optimization"
                    )
                if (
                    hasattr(sys_metrics, "memory_percent")
                    and sys_metrics.memory_percent > memory_threshold
                ):
                    recommendations.append(
                        "Memory utilization high - consider memory optimization"
                    )

            # AI analytics recommendations
            ai_data = self.monitoring_results.get("ai_analytics", {})
            trends = ai_data.get("trends", {})
            if "recommendations" in trends:
                recommendations.extend(trends["recommendations"])

            # BI dashboard recommendations
            bi_data = self.monitoring_results.get("bi_dashboard", {})
            bi_health = bi_data.get("system_health", {})
            improvement_areas = bi_health.get("improvement_areas", [])
            for area in improvement_areas:
                recommendations.append(f"Improve {area.lower()}")

            # APM recommendations
            apm_data = self.monitoring_results.get("apm", {})
            if apm_data.get("summary", {}).get("system_health") == "degraded":
                recommendations.append(
                    "APM system shows performance degradation - investigate active alerts"
                )

            # Remove duplicates and limit to top 10
            recommendations = list(set(recommendations))[:10]

            if not recommendations:
                recommendations.append("System performing well - continue monitoring")

            return recommendations

        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")
            return ["Error generating recommendations"]

    async def _store_consolidated_report(self, report: Dict[str, Any]):
        """Store consolidated report to file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = (
                self.reports_path / f"consolidated_monitoring_report_{timestamp}.json"
            )

            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)

            self.logger.info(f"📋 Consolidated report saved: {report_file}")

        except Exception as e:
            self.logger.error(f"Error storing consolidated report: {e}")

    async def get_current_status(self) -> Dict[str, Any]:
        """Get current monitoring system status."""
        return {
            "monitoring_active": self.monitoring_active,
            "systems_initialized": all(
                [
                    self.performance_monitor.redis_client is not None,
                    self.ai_analytics.redis_client is not None,
                    self.bi_dashboard.redis_client is not None,
                    self.apm_system.redis_client is not None,
                ]
            ),
            "last_performance_check": self.monitoring_results.get(
                "performance", {}
            ).get("timestamp"),
            "last_ai_check": self.monitoring_results.get("ai_analytics", {}).get(
                "timestamp"
            ),
            "last_bi_check": self.monitoring_results.get("bi_dashboard", {}).get(
                "timestamp"
            ),
            "last_apm_check": self.monitoring_results.get("apm", {}).get("timestamp"),
            "intervals": self.intervals,
        }

    async def generate_instant_report(self) -> Dict[str, Any]:
        """Generate instant monitoring report across all systems."""
        try:
            self.logger.info("⚡ Generating instant comprehensive report...")

            # Gather data from all systems in parallel
            tasks = [
                self.performance_monitor.generate_performance_report(),
                self.ai_analytics.generate_ai_performance_report(),
                self.bi_dashboard.generate_comprehensive_dashboard_report(),
                self.apm_system.generate_apm_report(),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            instant_report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "report_type": "instant_comprehensive",
                "performance_data": (
                    results[0]
                    if not isinstance(results[0], Exception)
                    else {"error": str(results[0])}
                ),
                "ai_analytics_data": (
                    results[1]
                    if not isinstance(results[1], Exception)
                    else {"error": str(results[1])}
                ),
                "bi_dashboard_data": (
                    results[2]
                    if not isinstance(results[2], Exception)
                    else {"error": str(results[2])}
                ),
                "apm_data": (
                    results[3]
                    if not isinstance(results[3], Exception)
                    else {"error": str(results[3])}
                ),
            }

            # Store instant report
            await self._store_consolidated_report(instant_report)

            self.logger.info("⚡ Instant report generated successfully")
            return instant_report

        except Exception as e:
            self.logger.error(f"Error generating instant report: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def stop_monitoring(self):
        """Stop all monitoring activities."""
        self.logger.info("🛑 Stopping comprehensive monitoring...")
        self.monitoring_active = False
        self.shutdown_requested = True


async def main():
    """Main function for comprehensive monitoring controller."""
    import argparse

    parser = argparse.ArgumentParser(
        description="AutoBot Comprehensive Monitoring Controller"
    )
    parser.add_argument(
        "--start", action="store_true", help="Start comprehensive monitoring"
    )
    parser.add_argument(
        "--instant-report", action="store_true", help="Generate instant report"
    )
    parser.add_argument("--status", action="store_true", help="Show monitoring status")

    args = parser.parse_args()

    controller = ComprehensiveMonitoringController()

    if args.instant_report:
        logger.info("⚡ Generating instant comprehensive report...")
        report = await controller.generate_instant_report()
        logger.info("✅ Instant report generated")
        logger.info("📊 Summary:")
        logger.info(f"  Timestamp: {report.get('timestamp')}")
        logger.info(
            f"  Performance: {'✅' if 'error' not in report.get('performance_data', {}) else '❌'}"
        )
        logger.info(
            f"  AI Analytics: {'✅' if 'error' not in report.get('ai_analytics_data', {}) else '❌'}"
        )
        logger.info(
            f"  BI Dashboard: {'✅' if 'error' not in report.get('bi_dashboard_data', {}) else '❌'}"
        )
        logger.info(
            f"  APM System: {'✅' if 'error' not in report.get('apm_data', {}) else '❌'}"
        )

    elif args.status:
        status = await controller.get_current_status()
        logger.info("📊 Monitoring System Status:")
        logger.info(f"  Active: {status['monitoring_active']}")
        logger.info(f"  Systems Initialized: {status['systems_initialized']}")
        logger.info(f"  Monitoring Intervals: {status['intervals']}")

    elif args.start:
        logger.info("🚀 Starting AutoBot Comprehensive Monitoring System...")
        logger.info("📊 Monitoring intervals:")
        for system, interval in controller.intervals.items():
            logger.info(f"  {system}: {interval}s")
        logger.info("Press Ctrl+C to stop monitoring")

        try:
            await controller.start_comprehensive_monitoring()
        except KeyboardInterrupt:
            logger.info("\n🛑 Monitoring stopped by user")
        finally:
            controller.stop_monitoring()

    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
