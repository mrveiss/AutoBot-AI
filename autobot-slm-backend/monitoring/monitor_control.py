#!/usr/bin/env python3
"""
AutoBot Monitor Control
Centralized control system for managing all AutoBot performance monitoring components.
Provides unified interface for monitoring, optimization, benchmarking, and alerting.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from performance_benchmark import PerformanceBenchmark
from performance_monitor import PerformanceMonitor
from performance_optimizer import PerformanceOptimizer

from autobot_shared.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


# Issue #339: Command handler functions extracted from main()
async def _handle_status_command(monitor_control: "MonitorControl", args) -> None:
    """Handle --status command (Issue #339 - extracted handler)."""
    logger.info("Getting AutoBot monitoring status...")
    status = await monitor_control.get_current_status()

    logger.info("\n" + "=" * 60)
    logger.info("AutoBot Monitoring Status")
    logger.info("=" * 60)

    monitoring = status["monitoring"]
    logger.info(f"Monitoring Running: {'Yes' if monitoring['running'] else 'No'}")
    logger.info(
        f"Dashboard: {'Enabled' if monitoring['dashboard_enabled'] else 'Disabled'}"
    )
    if monitoring["dashboard_enabled"]:
        logger.info(f"Dashboard Port: {monitoring['dashboard_port']}")
    logger.info(
        f"Auto-Optimization: {'Enabled' if monitoring['optimization_enabled'] else 'Disabled'}"
    )

    health = status["system_health"]
    logger.info(f"\nSystem Health Score: {health['overall_score']}/100")
    logger.info(
        f"Healthy Services: {health['healthy_services']}/{health['total_services']}"
    )
    logger.info(f"Active Alerts: {health['active_alerts']}")

    perf = status["performance_metrics"]
    logger.info("\nCurrent Performance:")
    logger.info(f"  CPU Usage: {perf['cpu_percent']:.1f}%")
    logger.info(f"  Memory Usage: {perf['memory_percent']:.1f}%")
    logger.info(f"  Disk Usage: {perf['disk_percent']:.1f}%")
    if perf["gpu_utilization"] is not None:
        logger.info(f"  GPU Utilization: {perf['gpu_utilization']:.1f}%")

    recs = status["recommendations"]
    if recs["total_count"] > 0:
        logger.info(f"\nOptimization Opportunities: {recs['total_count']}")
        logger.info(f"  Critical: {recs['critical']}")
        logger.info(f"  High Priority: {recs['high']}")
        logger.info(f"  Auto-Applicable: {recs['auto_applicable']}")


async def _handle_benchmark_command(monitor_control: "MonitorControl", args) -> None:
    """Handle --benchmark command (Issue #339 - extracted handler)."""
    results = await monitor_control.run_single_benchmark(
        test_type=args.benchmark, duration=args.benchmark_duration
    )

    logger.info(f"\n📈 {args.benchmark.title()} Benchmark Complete")

    if args.benchmark == "comprehensive":
        summary = results["summary"]
        logger.info(
            f"Overall Score: {summary['overall_system_score']:.1f}/100 (Grade: {summary['performance_grade']})"
        )
        logger.info(f"Total Tests: {summary['total_tests']}")
    else:
        logger.info("Results saved to logs/benchmarks/")


async def _handle_optimize_once_command(
    monitor_control: "MonitorControl", args
) -> None:
    """Handle --optimize-once command (Issue #339 - extracted handler)."""
    logger.info("Running single optimization cycle...")
    await monitor_control.optimizer.run_optimization_cycle()
    logger.info("Optimization cycle complete")


async def _run_with_interrupt_handler(monitor_control: "MonitorControl", coro) -> None:
    """Run coroutine with KeyboardInterrupt handling (Issue #339 - extracted helper)."""
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await monitor_control.stop_all() if hasattr(coro, "__self__") else await coro


async def _handle_dashboard_only_command(
    monitor_control: "MonitorControl", args
) -> None:
    """Handle --dashboard-only command (Issue #339 - extracted handler)."""
    logger.info("Starting performance dashboard only...")
    await monitor_control.start_dashboard()
    logger.info("Dashboard running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await monitor_control.stop_dashboard()


async def _handle_monitor_only_command(monitor_control: "MonitorControl", args) -> None:
    """Handle --monitor-only command (Issue #339 - extracted handler)."""
    logger.info("Starting monitoring only (no optimization)...")
    monitor_control.config.auto_optimization_enabled = False
    monitor_control.config.dashboard_enabled = False
    await monitor_control.start_all()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await monitor_control.stop_all()


async def _handle_stop_command(monitor_control: "MonitorControl", args) -> None:
    """Handle --stop command (Issue #339 - extracted handler)."""
    await monitor_control.stop_all()


async def _handle_restart_command(monitor_control: "MonitorControl", args) -> None:
    """Handle --restart command (Issue #339 - extracted handler)."""
    await monitor_control.stop_all()
    await asyncio.sleep(2)
    await monitor_control.start_all()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await monitor_control.stop_all()


async def _handle_start_command(monitor_control: "MonitorControl", args) -> None:
    """Handle --start command (Issue #339 - extracted handler)."""
    await monitor_control.start_all()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await monitor_control.stop_all()


@dataclass
class MonitoringConfig:
    """Monitoring system configuration."""

    monitoring_interval: int = 30
    optimization_interval: int = 1800  # 30 minutes
    dashboard_enabled: bool = True
    dashboard_port: int = 9090
    auto_optimization_enabled: bool = True
    benchmark_schedule: str = "daily"  # daily, weekly, manual
    alert_thresholds: Dict[str, float] = None
    log_level: str = "INFO"


class MonitorControl:
    """Centralized control for AutoBot performance monitoring system."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self.load_config(config_path)
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Initialize monitoring components
        self.performance_monitor = PerformanceMonitor(log_level=self.config.log_level)
        self.optimizer = PerformanceOptimizer()
        self.benchmark = PerformanceBenchmark()

        # Control state
        self.running = False
        self.dashboard_process = None
        self.monitoring_task = None
        self.optimization_task = None
        self.benchmark_task = None

    def load_config(self, config_path: Optional[str] = None) -> MonitoringConfig:
        """Load monitoring configuration from file."""
        if config_path is None:
            config_path = Path(__file__).parent / "monitoring_config.yaml"

        default_config = {
            "monitoring_interval": 30,
            "optimization_interval": 1800,
            "dashboard_enabled": True,
            "dashboard_port": 9090,
            "auto_optimization_enabled": True,
            "benchmark_schedule": "daily",
            "alert_thresholds": {
                "cpu_percent": 80.0,
                "memory_percent": 85.0,
                "disk_percent": 90.0,
                "api_response_time": 5.0,
                "db_query_time": 1.0,
            },
            "log_level": "INFO",
        }

        if Path(config_path).exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded_config = yaml.safe_load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                logger.warning(f"Error loading config: {e}, using defaults")
        else:
            # Create default config file
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(default_config, f, default_flow_style=False)

        return MonitoringConfig(**default_config)

    def setup_logging(self):
        """Configure logging for the monitoring system."""
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        log_dir = Path(_base) / "logs"
        log_dir.mkdir(exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_dir / "monitoring_control.log"),
                logging.handlers.RotatingFileHandler(
                    log_dir / "monitoring_control_detailed.log",
                    maxBytes=10 * 1024 * 1024,  # 10MB
                    backupCount=5,
                ),
            ],
        )

    async def start_dashboard(self):
        """Start the performance dashboard web interface."""
        if not self.config.dashboard_enabled:
            self.logger.info("Dashboard disabled in configuration")
            return

        try:
            dashboard_script = Path(__file__).parent / "performance_dashboard.py"

            self.dashboard_process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(dashboard_script),
                "--port",
                str(self.config.dashboard_port),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait a moment to see if it starts successfully
            await asyncio.sleep(2)

            if self.dashboard_process.returncode is None:
                self.logger.info(
                    f"📊 Performance dashboard started on port {self.config.dashboard_port}"
                )
                self.logger.info(
                    f"   Access at: http://localhost:{self.config.dashboard_port}"
                )
            else:
                self.logger.error("Dashboard failed to start")

        except Exception as e:
            self.logger.error(f"Error starting dashboard: {e}")

    async def stop_dashboard(self):
        """Stop the performance dashboard."""
        if self.dashboard_process:
            try:
                self.dashboard_process.terminate()
                await asyncio.wait_for(self.dashboard_process.wait(), timeout=5)
                self.logger.info("📊 Performance dashboard stopped")
            except asyncio.TimeoutError:
                self.dashboard_process.kill()
                await self.dashboard_process.wait()
                self.logger.warning("Dashboard forcefully killed")
            except Exception as e:
                self.logger.error(f"Error stopping dashboard: {e}")
            finally:
                self.dashboard_process = None

    async def start_monitoring(self):
        """Start continuous performance monitoring."""
        self.logger.info("🔍 Starting continuous performance monitoring")

        while self.running:
            try:
                # Generate performance report
                metrics = await self.performance_monitor.generate_performance_report()

                # Log basic system status
                if "system" in metrics:
                    sys_metrics = metrics["system"]
                    self.logger.info(
                        f"System: CPU={sys_metrics.cpu_percent:.1f}% "
                        f"MEM={sys_metrics.memory_percent:.1f}% "
                        f"DISK={sys_metrics.disk_percent:.1f}%"
                    )

                # Check for alerts
                alerts = metrics.get("alerts", [])
                if alerts:
                    for alert in alerts:
                        self.logger.warning(f"🚨 ALERT: {alert}")

                # Log service health
                services = metrics.get("services", [])
                healthy_services = sum(1 for s in services if s.is_healthy)
                total_services = len(services)

                if total_services > 0:
                    health_percentage = (healthy_services / total_services) * 100
                    if health_percentage < 100:
                        self.logger.warning(
                            f"Services: {healthy_services}/{total_services} healthy ({health_percentage:.1f}%)"
                        )
                    else:
                        self.logger.info(
                            f"Services: {healthy_services}/{total_services} healthy"
                        )

            except Exception as e:
                self.logger.error(f"Error in monitoring cycle: {e}")

            # Wait for next monitoring cycle
            await asyncio.sleep(self.config.monitoring_interval)

    async def start_optimization(self):
        """Start automatic performance optimization."""
        if not self.config.auto_optimization_enabled:
            self.logger.info("Auto-optimization disabled in configuration")
            return

        self.logger.info("🔧 Starting automatic performance optimization")

        while self.running:
            try:
                await self.optimizer.run_optimization_cycle()
            except Exception as e:
                self.logger.error(f"Error in optimization cycle: {e}")

            # Wait for next optimization cycle
            await asyncio.sleep(self.config.optimization_interval)

    async def start_benchmark_scheduler(self):
        """Start scheduled benchmarking."""
        if self.config.benchmark_schedule == "manual":
            self.logger.info("Benchmarking set to manual mode")
            return

        self.logger.info(
            f"📈 Starting benchmark scheduler (schedule: {self.config.benchmark_schedule})"
        )

        # Calculate interval based on schedule
        if self.config.benchmark_schedule == "daily":
            interval = 24 * 60 * 60  # 24 hours
        elif self.config.benchmark_schedule == "weekly":
            interval = 7 * 24 * 60 * 60  # 7 days
        else:
            self.logger.error(
                f"Unknown benchmark schedule: {self.config.benchmark_schedule}"
            )
            return

        while self.running:
            try:
                self.logger.info("🚀 Starting scheduled benchmark")
                await self.benchmark.run_comprehensive_benchmark()
                self.logger.info("✅ Scheduled benchmark completed")
            except Exception as e:
                self.logger.error(f"Error in scheduled benchmark: {e}")

            # Wait for next benchmark
            await asyncio.sleep(interval)

    async def run_single_benchmark(
        self, test_type: str = "comprehensive", duration: int = 60
    ) -> Dict[str, Any]:
        """Run a single benchmark test."""
        self.logger.info(f"🚀 Running {test_type} benchmark")

        try:
            if test_type == "comprehensive":
                return await self.benchmark.run_comprehensive_benchmark()
            elif test_type == "api":
                results = await self.benchmark.run_api_benchmark(
                    duration_seconds=duration
                )
                return {"api_results": [result.__dict__ for result in results]}
            elif test_type == "database":
                results = await self.benchmark.run_database_benchmark(
                    duration_seconds=duration
                )
                return {"database_results": [result.__dict__ for result in results]}
            elif test_type == "network":
                results = await self.benchmark.run_network_benchmark(
                    duration_seconds=duration
                )
                return {"network_results": [result.__dict__ for result in results]}
            elif test_type == "system":
                result = await self.benchmark.run_system_benchmark()
                return {"system_benchmark": result.__dict__}
            else:
                raise ValueError(f"Unknown benchmark type: {test_type}")
        except Exception as e:
            self.logger.error(f"Benchmark failed: {e}")
            raise

    async def get_current_status(self) -> Dict[str, Any]:
        """Get current system status and monitoring state."""
        try:
            # Get current performance metrics
            metrics = await self.performance_monitor.generate_performance_report()

            # Get optimization recommendations
            recommendations = await self.optimizer.analyze_performance_metrics(metrics)

            status = {
                "timestamp": datetime.now().isoformat(),
                "monitoring": {
                    "running": self.running,
                    "monitoring_interval": self.config.monitoring_interval,
                    "optimization_enabled": self.config.auto_optimization_enabled,
                    "optimization_interval": self.config.optimization_interval,
                    "dashboard_enabled": self.config.dashboard_enabled,
                    "dashboard_port": (
                        self.config.dashboard_port
                        if self.config.dashboard_enabled
                        else None
                    ),
                },
                "system_health": {
                    "overall_score": self._calculate_health_score(metrics),
                    "active_alerts": len(metrics.get("alerts", [])),
                    "healthy_services": sum(
                        1 for s in metrics.get("services", []) if s.is_healthy
                    ),
                    "total_services": len(metrics.get("services", [])),
                },
                "performance_metrics": {
                    "cpu_percent": metrics.get("system", {}).get("cpu_percent", 0),
                    "memory_percent": metrics.get("system", {}).get(
                        "memory_percent", 0
                    ),
                    "disk_percent": metrics.get("system", {}).get("disk_percent", 0),
                    "gpu_utilization": metrics.get("system", {}).get("gpu_utilization"),
                    "npu_utilization": metrics.get("system", {}).get("npu_utilization"),
                },
                "recommendations": {
                    "total_count": len(recommendations),
                    "critical": len(
                        [r for r in recommendations if r.severity == "critical"]
                    ),
                    "high": len([r for r in recommendations if r.severity == "high"]),
                    "auto_applicable": len(
                        [r for r in recommendations if r.auto_applicable]
                    ),
                },
            }

            return status

        except Exception as e:
            self.logger.error(f"Error getting current status: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "monitoring": {"running": self.running},
            }

    def _calculate_health_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate overall system health score (0-100)."""
        try:
            score = 100.0

            # Get thresholds from loaded config
            thresholds = self.config.alert_thresholds or {}
            cpu_threshold = thresholds.get("cpu_percent", 80.0)
            memory_threshold = thresholds.get("memory_percent", 85.0)
            disk_threshold = thresholds.get("disk_percent", 90.0)

            # Deduct points for system resource issues
            if "system" in metrics:
                sys_metrics = metrics["system"]

                # CPU usage penalty
                if sys_metrics.cpu_percent > cpu_threshold:
                    score -= min(20, (sys_metrics.cpu_percent - cpu_threshold) / 2)

                # Memory usage penalty
                if sys_metrics.memory_percent > memory_threshold:
                    score -= min(
                        20, (sys_metrics.memory_percent - memory_threshold) / 1.5
                    )

                # Disk usage penalty
                if sys_metrics.disk_percent > disk_threshold:
                    score -= min(15, (sys_metrics.disk_percent - disk_threshold) / 1)

            # Deduct points for unhealthy services
            services = metrics.get("services", [])
            if services:
                unhealthy_services = sum(1 for s in services if not s.is_healthy)
                service_penalty = (unhealthy_services / len(services)) * 30
                score -= service_penalty

            # Deduct points for alerts
            alerts = metrics.get("alerts", [])
            critical_alerts = sum(
                1 for alert in alerts if "DOWN" in alert or "ERROR" in alert
            )
            warning_alerts = len(alerts) - critical_alerts

            score -= critical_alerts * 15  # 15 points per critical alert
            score -= warning_alerts * 5  # 5 points per warning alert

            return max(0.0, round(score, 1))

        except Exception as e:
            self.logger.error(f"Error calculating health score: {e}")
            return 50.0  # Default middle score on error

    async def start_all(self):
        """Start all monitoring components."""
        self.logger.info("🚀 Starting AutoBot Performance Monitoring System")
        self.running = True

        # Start dashboard first
        await self.start_dashboard()

        # Start monitoring tasks
        self.monitoring_task = asyncio.create_task(self.start_monitoring())
        self.optimization_task = asyncio.create_task(self.start_optimization())
        self.benchmark_task = asyncio.create_task(self.start_benchmark_scheduler())

        self.logger.info("✅ All monitoring components started")

        # Print status summary
        await self._print_startup_summary()

    async def stop_all(self):
        """Stop all monitoring components."""
        self.logger.info("🛑 Stopping AutoBot Performance Monitoring System")
        self.running = False

        # Cancel monitoring tasks
        tasks = [self.monitoring_task, self.optimization_task, self.benchmark_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop dashboard
        await self.stop_dashboard()

        self.logger.info("✅ All monitoring components stopped")

    def _log_monitored_vms(self):
        """Log monitored VM addresses and paths. Helper for _print_startup_summary."""
        logger.info("\n🎯 Monitoring AutoBot distributed system:")
        logger.info(
            f"   • Main (WSL): {NetworkConstants.MAIN_MACHINE_IP} - Backend API"
        )
        logger.info(
            f"   • Frontend VM: {NetworkConstants.FRONTEND_VM_IP} - Web Interface"
        )
        logger.info(
            f"   • NPU Worker VM: {NetworkConstants.NPU_WORKER_VM_IP} - AI Acceleration"
        )
        logger.info(f"   • Redis VM: {NetworkConstants.REDIS_VM_IP} - Data Layer")
        logger.info(
            f"   • AI Stack VM: {NetworkConstants.AI_STACK_VM_IP} - AI Processing"
        )
        logger.info(
            f"   • Browser VM: {NetworkConstants.BROWSER_VM_IP} - Web Automation"
        )
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        logger.info("\n💾 Logs: %s/logs/", _base)
        logger.info("📊 Results: %s/logs/benchmarks/", _base)

    def _log_startup_config(self) -> None:
        """Helper for _print_startup_summary. Ref: #1088."""
        logger.info(
            f"📊 Dashboard: {'Enabled' if self.config.dashboard_enabled else 'Disabled'}"
        )
        if self.config.dashboard_enabled:
            logger.info(f"   URL: http://localhost:{self.config.dashboard_port}")
        logger.info(f"🔍 Monitoring: Every {self.config.monitoring_interval}s")
        logger.info(
            f"🔧 Optimization: {'Enabled' if self.config.auto_optimization_enabled else 'Disabled'}"
        )
        if self.config.auto_optimization_enabled:
            logger.info(
                f"   Cycle: Every {self.config.optimization_interval//60} minutes"
            )
        logger.info(f"📈 Benchmarks: {self.config.benchmark_schedule}")

    def _log_startup_health(self, status: Dict[str, Any]) -> None:
        """Helper for _print_startup_summary. Ref: #1088."""
        health_score = status["system_health"]["overall_score"]
        logger.info(f"\n📋 Current System Health: {health_score}/100")

        perf = status["performance_metrics"]
        logger.info(f"   CPU: {perf['cpu_percent']:.1f}%")
        logger.info(f"   Memory: {perf['memory_percent']:.1f}%")
        logger.info(f"   Disk: {perf['disk_percent']:.1f}%")
        if perf["gpu_utilization"] is not None:
            logger.info(f"   GPU: {perf['gpu_utilization']:.1f}%")

        services = status["system_health"]
        logger.info(
            f"   Services: {services['healthy_services']}/{services['total_services']} healthy"
        )
        if status["system_health"]["active_alerts"] > 0:
            logger.info(
                f"   🚨 Active Alerts: {status['system_health']['active_alerts']}"
            )

        recs = status["recommendations"]
        if recs["total_count"] > 0:
            logger.info(
                "   📋 Optimization Opportunities: %s (Critical: %s, High: %s)",
                recs["total_count"],
                recs["critical"],
                recs["high"],
            )

    async def _print_startup_summary(self):
        """Print startup summary information."""
        logger.info("\n" + "=" * 80)
        logger.info("🤖 AutoBot Performance Monitoring System - ACTIVE")
        logger.info("=" * 80)

        self._log_startup_config()

        status = await self.get_current_status()
        self._log_startup_health(status)

        self._log_monitored_vms()

        logger.info("\n🔧 Control Commands:")
        logger.info("   • Press Ctrl+C to stop monitoring")
        logger.info("   • Use --status to check current state")
        logger.info("   • Use --benchmark to run performance tests")

        logger.info("=" * 80)


def _create_argument_parser():
    """Create and configure argument parser. Helper for main."""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Monitor Control System")

    parser.add_argument(
        "--start", action="store_true", help="Start all monitoring components"
    )
    parser.add_argument(
        "--stop", action="store_true", help="Stop all monitoring components"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show current monitoring status"
    )
    parser.add_argument(
        "--restart", action="store_true", help="Restart all monitoring components"
    )
    parser.add_argument(
        "--dashboard-only", action="store_true", help="Start only the dashboard"
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Start only monitoring (no optimization)",
    )
    parser.add_argument(
        "--optimize-once", action="store_true", help="Run single optimization cycle"
    )
    parser.add_argument(
        "--benchmark",
        choices=["comprehensive", "api", "database", "network", "system"],
        help="Run performance benchmark",
    )
    parser.add_argument(
        "--benchmark-duration",
        type=int,
        default=60,
        help="Benchmark duration in seconds",
    )
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    return parser


async def _dispatch_command(monitor_control, args, parser):
    """Dispatch to appropriate command handler. Helper for main."""
    if args.status:
        await _handle_status_command(monitor_control, args)
    elif args.benchmark:
        await _handle_benchmark_command(monitor_control, args)
    elif args.optimize_once:
        await _handle_optimize_once_command(monitor_control, args)
    elif args.dashboard_only:
        await _handle_dashboard_only_command(monitor_control, args)
    elif args.monitor_only:
        await _handle_monitor_only_command(monitor_control, args)
    elif args.stop:
        await _handle_stop_command(monitor_control, args)
    elif args.restart:
        await _handle_restart_command(monitor_control, args)
    elif args.start or len(sys.argv) == 1:
        await _handle_start_command(monitor_control, args)
    else:
        parser.print_help()


async def main():
    """Main function for monitor control."""
    parser = _create_argument_parser()
    args = parser.parse_args()
    monitor_control = MonitorControl(config_path=args.config)

    try:
        await _dispatch_command(monitor_control, args, parser)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        await monitor_control.stop_all()
    except Exception as e:
        logger.error(f"Error: {e}")
        await monitor_control.stop_all()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
