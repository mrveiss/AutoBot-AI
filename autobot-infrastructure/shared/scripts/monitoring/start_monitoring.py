#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Performance Monitoring Startup Script
Comprehensive performance monitoring system initialization and management.

One launcher for both monitoring backends (#17906). ``--backend performance`` (the default) drives
``utils.performance_monitor``; ``--backend hardware`` drives ``utils.hardware_metrics`` and keeps the
retired ``start_hardware_monitoring.py``'s log file and benchmark location.

A backend tool (#18288): it drives backend monitors, so it puts the backend on its own path. Run it
from anywhere as ``python3 autobot-infrastructure/shared/scripts/monitoring/start_monitoring.py
[--backend hardware] <command>``; no PYTHONPATH is needed.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Two roots, kept apart on purpose (#15643). `backend_root` is the IMPORT root for the backend's
# `constants.*` and `utils.*`; `project_root` is the repository root, which is both the import root
# for `autobot_shared` (#18288: the script used to need it on the caller's PYTHONPATH) and the DATA
# root for `logs/` and `reports/`. `Path(__file__).parent.parent.parent` once landed on
# autobot-infrastructure/shared/ and the script could not start at all (#15643, #14129).
project_root = Path(__file__).resolve().parents[4]
backend_root = Path(__file__).resolve().parents[4] / "autobot-backend"
monitoring_dir = Path(__file__).resolve().parent
# Own dir first so it ends up LAST of the three: nothing beside the launcher may shadow the backend.
sys.path.insert(0, str(monitoring_dir))  # the sibling monitoring_backends module
sys.path.insert(0, str(backend_root))
sys.path.insert(0, str(project_root))

from autobot_shared.async_compat import fire_and_forget  # noqa: E402
from constants.threshold_constants import CategoryDefaults, TimingConstants
from utils.gpu_acceleration_optimizer import (
    benchmark_gpu,
    get_gpu_capabilities,
    gpu_optimizer,
    monitor_gpu_efficiency,
    optimize_gpu_for_multimodal,
)
from monitoring_backends import (  # noqa: E402
    BACKEND_PERFORMANCE,
    BACKENDS,
    MonitoringBackend,
    load_backend,
)

logger = logging.getLogger(__name__)


def configure_logging(backend: MonitoringBackend) -> None:
    """Send logs to the console and to the backend's log file."""
    backend.log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(backend.log_file)],
    )


class PerformanceMonitoringManager:
    """
    Manager for comprehensive performance monitoring system.
    Coordinates GPU optimization, NPU acceleration, and system monitoring.
    """

    def __init__(self, backend: Optional[MonitoringBackend] = None):
        """Initialize performance monitoring manager with default configuration."""
        self.backend = backend or load_backend(BACKEND_PERFORMANCE)
        self.monitoring_active = False
        self.optimization_active = False
        self.alerts_enabled = True
        self.start_time = None

        # Performance tracking
        self.metrics_collected = 0
        self.optimizations_applied = 0
        self.alerts_triggered = 0

        # Configuration
        self.config = {
            "monitoring_interval": 5.0,
            "optimization_interval": 300.0,  # 5 minutes
            "alert_threshold_critical": 90.0,
            "alert_threshold_warning": 80.0,
            "gpu_optimization_enabled": True,
            "npu_monitoring_enabled": True,
            "multimodal_tracking_enabled": True,
            "realtime_dashboard_enabled": True,
        }

    async def initialize(self):
        """Initialize the performance monitoring system"""
        try:
            logger.info("Initializing Performance Monitoring System...")

            # Check hardware availability
            gpu_capabilities = get_gpu_capabilities()
            logger.info("GPU Available: %s", gpu_capabilities["gpu_available"])
            logger.info("NPU Available: %s", self.backend.monitor.npu_available)

            # Setup alert callbacks
            if self.alerts_enabled:
                await self.backend.add_alert_callback(self._handle_performance_alert)
                logger.info("Performance alert callbacks configured")

            # Initialize baseline metrics
            logger.info("Collecting baseline performance metrics...")
            baseline_metrics = await self.backend.collect()
            if baseline_metrics.get("collection_successful", False):
                logger.info("Baseline metrics collected successfully")
            else:
                logger.warning("Failed to collect baseline metrics")

            # Run initial GPU optimization if enabled
            if self.config["gpu_optimization_enabled"] and gpu_capabilities["gpu_available"]:
                logger.info("Running initial GPU optimization...")
                optimization_result = await optimize_gpu_for_multimodal()
                if optimization_result.success:
                    logger.info(
                        "GPU optimization completed: %.1f%% improvement",
                        optimization_result.performance_improvement,
                    )
                    self.optimizations_applied += len(optimization_result.applied_optimizations)
                else:
                    logger.warning("GPU optimization failed")

            logger.info("Performance monitoring system initialized successfully")
            return True

        except Exception as e:
            logger.error("Failed to initialize performance monitoring: %s", e)
            return False

    async def start_monitoring(self):
        """Start comprehensive performance monitoring"""
        try:
            if self.monitoring_active:
                logger.warning("Monitoring already active")
                return False

            logger.info("Starting comprehensive performance monitoring...")

            # Start core monitoring
            await self.backend.start()

            prefix = self.backend.task_prefix

            # Start periodic optimization if enabled
            if self.config["gpu_optimization_enabled"]:
                fire_and_forget(self._periodic_optimization_loop(), name=f"{prefix}-optimization-loop")

            # Start monitoring dashboard updates
            if self.config["realtime_dashboard_enabled"]:
                fire_and_forget(self._dashboard_update_loop(), name=f"{prefix}-dashboard-loop")

            self.monitoring_active = True
            self.start_time = time.time()

            logger.info("Performance monitoring started successfully")
            return True

        except Exception as e:
            logger.error("Failed to start monitoring: %s", e)
            return False

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        try:
            if not self.monitoring_active:
                logger.warning("Monitoring not active")
                return False

            logger.info("Stopping performance monitoring...")

            # Stop core monitoring
            await self.backend.stop()

            self.monitoring_active = False

            # Generate final report
            uptime = time.time() - self.start_time if self.start_time else 0
            logger.info(
                "Monitoring stopped. Uptime: %.1fs, Metrics collected: %s",
                uptime,
                self.metrics_collected,
            )

            return True

        except Exception as e:
            logger.error("Failed to stop monitoring: %s", e)
            return False

    async def _periodic_optimization_loop(self):
        """Periodic GPU optimization loop"""
        logger.info("Starting periodic optimization loop...")

        while self.monitoring_active:
            try:
                await asyncio.sleep(self.config["optimization_interval"])

                if not self.monitoring_active:
                    break

                logger.info("Running periodic GPU optimization...")

                # Check if optimization is needed
                efficiency = await monitor_gpu_efficiency()
                overall_efficiency = efficiency.get("overall_efficiency", 0)

                if overall_efficiency < 80:  # Trigger optimization if efficiency is low
                    optimization_result = await optimize_gpu_for_multimodal()
                    if optimization_result.success:
                        logger.info(
                            "Periodic optimization completed: %.1f%% improvement",
                            optimization_result.performance_improvement,
                        )
                        self.optimizations_applied += len(optimization_result.applied_optimizations)
                    else:
                        logger.warning("Periodic optimization failed")
                else:
                    logger.info(
                        "GPU efficiency is good (%.1f%%), skipping optimization",
                        overall_efficiency,
                    )

            except Exception as e:
                logger.error("Error in periodic optimization loop: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_TIMEOUT)  # Wait before retrying

    async def _dashboard_update_loop(self):
        """Dashboard update loop for real-time monitoring"""
        logger.info("Starting dashboard update loop...")

        while self.monitoring_active:
            try:
                await asyncio.sleep(TimingConstants.LONG_DELAY)  # Update every 10 seconds

                if not self.monitoring_active:
                    break

                # Collect current metrics
                dashboard_data = await self.backend.dashboard()

                if dashboard_data.get("monitoring_active", False):
                    self.metrics_collected += 1

                    # Log key metrics periodically
                    if self.metrics_collected % 6 == 0:  # Every minute
                        self._log_dashboard_summary(dashboard_data)

            except Exception as e:
                logger.error("Error in dashboard update loop: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_LONG_DELAY)  # Wait before retrying

    def _log_dashboard_summary(self, dashboard_data):
        """Log dashboard summary information"""
        try:
            summary_parts = []

            # GPU summary
            if dashboard_data.get("gpu"):
                gpu = dashboard_data["gpu"]
                summary_parts.append(f"GPU: {gpu.get('utilization_percent', 0):.0f}%")

            # NPU summary
            if dashboard_data.get("npu"):
                npu = dashboard_data["npu"]
                summary_parts.append(f"NPU: {npu.get('acceleration_ratio', 0):.1f}x")

            # System summary
            if dashboard_data.get("system"):
                system = dashboard_data["system"]
                summary_parts.append(f"CPU: {system.get('cpu_usage_percent', 0):.0f}%")
                summary_parts.append(f"MEM: {system.get('memory_usage_percent', 0):.0f}%")

            # Alert summary
            recent_alerts = dashboard_data.get("recent_alerts", [])
            if recent_alerts:
                critical_alerts = sum(1 for alert in recent_alerts if alert.get("severity") == "critical")
                if critical_alerts > 0:
                    summary_parts.append(f"⚠️ {critical_alerts} critical alerts")

            logger.info(
                "DASHBOARD: %s | Collected: %s",
                " | ".join(summary_parts),
                self.metrics_collected,
            )

        except Exception as e:
            logger.error("Error logging dashboard summary: %s", e)

    async def _handle_performance_alert(self, alerts):
        """Handle performance alerts"""
        try:
            for alert in alerts:
                self.alerts_triggered += 1
                severity = alert.get("severity", "unknown")
                category = alert.get("category", CategoryDefaults.UNKNOWN)
                message = alert.get("message", "No message")

                log_level = logging.CRITICAL if severity == "critical" else logging.WARNING
                logger.log(
                    log_level,
                    f"PERFORMANCE ALERT [{severity.upper()}] {category}: {message}",
                )

                # Take automated action for critical alerts
                if severity == "critical":
                    await self._handle_critical_alert(alert)

        except Exception as e:
            logger.error("Error handling performance alert: %s", e)

    async def _handle_critical_alert(self, alert):
        """Handle critical performance alerts with automated responses"""
        try:
            category = alert.get("category", "")

            if category == "gpu" and "thermal throttling" in alert.get("message", "").lower():
                logger.critical("GPU thermal throttling detected - reducing GPU load")
                # Could implement automated GPU load reduction here

            elif category == "memory" and alert.get("message", "").find("90") != -1:
                logger.critical("High memory usage detected - triggering cleanup")
                # Could implement automated memory cleanup here

            elif category == "service" and "critical" in alert.get("message", "").lower():
                logger.critical("Critical service issue detected")
                # Could implement service restart or fallback here

        except Exception as e:
            logger.error("Error handling critical alert: %s", e)

    async def run_benchmark_suite(self):
        """Run comprehensive benchmark suite"""
        try:
            logger.info("Starting comprehensive benchmark suite...")

            results = {
                "timestamp": datetime.now().isoformat(),
                "system_info": {},
                "gpu_benchmark": {},
                "performance_metrics": {},
                "optimization_results": {},
            }

            # System information
            results["system_info"] = get_gpu_capabilities()

            # GPU benchmark
            if results["system_info"]["gpu_available"]:
                logger.info("Running GPU benchmark...")
                results["gpu_benchmark"] = await benchmark_gpu()

            # Current performance metrics
            logger.info("Collecting performance metrics...")
            results["performance_metrics"] = await self.backend.collect()

            # GPU optimization test
            if self.config["gpu_optimization_enabled"]:
                logger.info("Testing GPU optimization...")
                results["optimization_results"] = await optimize_gpu_for_multimodal()

            # Save results to proper directory
            reports_dir = self.backend.report_dir
            reports_dir.mkdir(parents=True, exist_ok=True)

            benchmark_file = reports_dir / f"{self.backend.report_prefix}_{int(time.time())}.json"
            with open(benchmark_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)

            logger.info("Benchmark suite completed. Results saved to: %s", benchmark_file)
            return results

        except Exception as e:
            logger.error("Benchmark suite failed: %s", e)
            return {"error": str(e)}

    def get_status_report(self):
        """Get current status report"""
        uptime = time.time() - self.start_time if self.start_time else 0

        return {
            "monitoring_active": self.monitoring_active,
            "optimization_active": self.optimization_active,
            "uptime_seconds": uptime,
            "metrics_collected": self.metrics_collected,
            "optimizations_applied": self.optimizations_applied,
            "alerts_triggered": self.alerts_triggered,
            "configuration": self.config,
            "hardware_status": {
                "gpu_available": gpu_optimizer.gpu_available,
                "npu_available": self.backend.monitor.npu_available,
            },
        }


async def _run_daemon_loop(manager: PerformanceMonitoringManager) -> None:
    """Run monitoring daemon loop (Issue #315: extracted helper)."""
    logger.info("Running in daemon mode...")
    try:
        while True:
            await asyncio.sleep(TimingConstants.STANDARD_TIMEOUT)
            status = manager.get_status_report()
            if not status["monitoring_active"]:
                break
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await manager.stop_monitoring()


async def _handle_start_command(manager: PerformanceMonitoringManager, daemon: bool) -> None:
    """Handle start command (Issue #315: extracted helper)."""
    if not await manager.initialize():
        logger.error("Failed to initialize monitoring")
        sys.exit(1)

    if not await manager.start_monitoring():
        logger.error("Failed to start monitoring")
        sys.exit(1)

    logger.info("Performance monitoring started successfully")

    if daemon:
        await _run_daemon_loop(manager)
    else:
        logger.info("Monitoring started. Use 'stop' command to stop monitoring.")


async def _handle_test_command(manager: PerformanceMonitoringManager) -> None:
    """Handle test command (Issue #315: extracted helper)."""
    logger.info("Running quick test of monitoring components...")
    await manager.initialize()

    metrics = await manager.backend.collect()
    logger.info(
        "Metrics collection test: %s",
        "✓" if metrics.get("collection_successful") else "✗",
    )

    capabilities = get_gpu_capabilities()
    logger.info("GPU capabilities test: %s", "✓" if capabilities["gpu_available"] else "✗")

    efficiency = await monitor_gpu_efficiency()
    logger.info(
        "Efficiency monitoring test: %s",
        "✓" if "overall_efficiency" in efficiency else "✗",
    )

    logger.info("Component tests completed")


def _build_parser(default_backend: str) -> argparse.ArgumentParser:
    """Command-line interface: the command, the backend to drive, and run options."""
    parser = argparse.ArgumentParser(description="AutoBot Performance Monitoring")
    parser.add_argument(
        "--backend",
        choices=BACKENDS,
        default=default_backend,
        help="Monitor to drive: performance (default) or hardware (GPU/NPU metrics)",
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "benchmark", "test"],
        help="Command to execute",
    )
    parser.add_argument("--config", type=str, help="Configuration file path")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser


def _load_config_file(manager: PerformanceMonitoringManager, config_path: Optional[str]) -> None:
    """Merge a JSON configuration file into the manager's config, if one was given and exists."""
    if not (config_path and os.path.exists(config_path)):
        return
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            manager.config.update(json.load(f))
            logger.info("Configuration loaded from %s", config_path)
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)


async def _handle_stop_command(manager: PerformanceMonitoringManager) -> None:
    """Handle stop command."""
    if not await manager.stop_monitoring():
        logger.error("Failed to stop monitoring")
        sys.exit(1)
    logger.info("Monitoring stopped successfully")


async def _handle_benchmark_command(manager: PerformanceMonitoringManager) -> None:
    """Handle benchmark command."""
    await manager.initialize()
    logger.info(json.dumps(await manager.run_benchmark_suite(), indent=2, default=str))


async def _dispatch(manager: PerformanceMonitoringManager, args: argparse.Namespace) -> None:
    """Run the parsed command against the manager."""
    if args.command == "start":
        await _handle_start_command(manager, args.daemon)
    elif args.command == "stop":
        await _handle_stop_command(manager)
    elif args.command == "status":
        logger.info(json.dumps(manager.get_status_report(), indent=2))
    elif args.command == "benchmark":
        await _handle_benchmark_command(manager)
    elif args.command == "test":
        await _handle_test_command(manager)


async def main(default_backend: str = BACKEND_PERFORMANCE):
    """Main function for performance monitoring management (Issue #315: refactored)."""
    args = _build_parser(default_backend).parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    backend = load_backend(args.backend)
    configure_logging(backend)
    manager = PerformanceMonitoringManager(backend)
    _load_config_file(manager, args.config)

    try:
        await _dispatch(manager, args)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        if manager.monitoring_active:
            await manager.stop_monitoring()
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
