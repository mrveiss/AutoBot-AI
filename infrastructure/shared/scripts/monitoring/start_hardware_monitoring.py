#!/usr/bin/env python3
"""
AutoBot Phase 9 Monitoring Startup Script
Comprehensive performance monitoring system initialization and management.
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

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.gpu_acceleration_optimizer import (
    benchmark_gpu,
    get_gpu_capabilities,
    gpu_optimizer,
    monitor_gpu_efficiency,
    optimize_gpu_for_multimodal,
)

# Import Phase 9 monitoring components
from src.utils.hardware_metrics import (
    add_phase9_alert_callback,
    collect_phase9_metrics,
    get_phase9_performance_dashboard,
    phase9_monitor,
    start_phase9_monitoring,
    stop_phase9_monitoring,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/phase9_monitoring.log"),
    ],
)
logger = logging.getLogger(__name__)


class Phase9MonitoringManager:
    """
    Manager for Phase 9 comprehensive performance monitoring system.
    Coordinates GPU optimization, NPU acceleration, and system monitoring.
    """

    def __init__(self):
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
        """Initialize the Phase 9 monitoring system"""
        try:
            logger.info("Initializing Phase 9 Performance Monitoring System...")

            # Check hardware availability
            gpu_capabilities = get_gpu_capabilities()
            logger.info(f"GPU Available: {gpu_capabilities['gpu_available']}")
            logger.info(f"NPU Available: {phase9_monitor.npu_available}")

            # Setup alert callbacks
            if self.alerts_enabled:
                add_phase9_alert_callback(self._handle_performance_alert)
                logger.info("Performance alert callbacks configured")

            # Initialize baseline metrics
            logger.info("Collecting baseline performance metrics...")
            baseline_metrics = await collect_phase9_metrics()
            if baseline_metrics.get("collection_successful", False):
                logger.info("Baseline metrics collected successfully")
            else:
                logger.warning("Failed to collect baseline metrics")

            # Run initial GPU optimization if enabled
            if (
                self.config["gpu_optimization_enabled"]
                and gpu_capabilities["gpu_available"]
            ):
                logger.info("Running initial GPU optimization...")
                optimization_result = await optimize_gpu_for_multimodal()
                if optimization_result.success:
                    logger.info(
                        f"GPU optimization completed: {optimization_result.performance_improvement:.1f}% improvement"
                    )
                    self.optimizations_applied += len(
                        optimization_result.applied_optimizations
                    )
                else:
                    logger.warning("GPU optimization failed")

            logger.info("Phase 9 monitoring system initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Phase 9 monitoring: {e}")
            return False

    async def start_monitoring(self):
        """Start comprehensive performance monitoring"""
        try:
            if self.monitoring_active:
                logger.warning("Monitoring already active")
                return False

            logger.info("Starting Phase 9 comprehensive performance monitoring...")

            # Start core monitoring
            await start_phase9_monitoring()

            # Start periodic optimization if enabled
            if self.config["gpu_optimization_enabled"]:
                asyncio.create_task(self._periodic_optimization_loop())

            # Start monitoring dashboard updates
            if self.config["realtime_dashboard_enabled"]:
                asyncio.create_task(self._dashboard_update_loop())

            self.monitoring_active = True
            self.start_time = time.time()

            logger.info("Phase 9 monitoring started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
            return False

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        try:
            if not self.monitoring_active:
                logger.warning("Monitoring not active")
                return False

            logger.info("Stopping Phase 9 performance monitoring...")

            # Stop core monitoring
            await stop_phase9_monitoring()

            self.monitoring_active = False

            # Generate final report
            uptime = time.time() - self.start_time if self.start_time else 0
            logger.info(
                f"Monitoring stopped. Uptime: {uptime:.1f}s, Metrics collected: {self.metrics_collected}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to stop monitoring: {e}")
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
                            f"Periodic optimization completed: {optimization_result.performance_improvement:.1f}% improvement"
                        )
                        self.optimizations_applied += len(
                            optimization_result.applied_optimizations
                        )
                    else:
                        logger.warning("Periodic optimization failed")
                else:
                    logger.info(
                        f"GPU efficiency is good ({overall_efficiency:.1f}%), skipping optimization"
                    )

            except Exception as e:
                logger.error(f"Error in periodic optimization loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _dashboard_update_loop(self):
        """Dashboard update loop for real-time monitoring"""
        logger.info("Starting dashboard update loop...")

        while self.monitoring_active:
            try:
                await asyncio.sleep(10)  # Update every 10 seconds

                if not self.monitoring_active:
                    break

                # Collect current metrics
                dashboard_data = get_phase9_performance_dashboard()

                if dashboard_data.get("monitoring_active", False):
                    self.metrics_collected += 1

                    # Log key metrics periodically
                    if self.metrics_collected % 6 == 0:  # Every minute
                        self._log_dashboard_summary(dashboard_data)

            except Exception as e:
                logger.error(f"Error in dashboard update loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying

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
                summary_parts.append(
                    f"MEM: {system.get('memory_usage_percent', 0):.0f}%"
                )

            # Alert summary
            recent_alerts = dashboard_data.get("recent_alerts", [])
            if recent_alerts:
                critical_alerts = sum(
                    1 for alert in recent_alerts if alert.get("severity") == "critical"
                )
                if critical_alerts > 0:
                    summary_parts.append(f"⚠️ {critical_alerts} critical alerts")

            logger.info(
                f"DASHBOARD: {' | '.join(summary_parts)} | Collected: {self.metrics_collected}"
            )

        except Exception as e:
            logger.error(f"Error logging dashboard summary: {e}")

    async def _handle_performance_alert(self, alerts):
        """Handle performance alerts"""
        try:
            for alert in alerts:
                self.alerts_triggered += 1
                severity = alert.get("severity", "unknown")
                category = alert.get("category", "unknown")
                message = alert.get("message", "No message")

                log_level = (
                    logging.CRITICAL if severity == "critical" else logging.WARNING
                )
                logger.log(
                    log_level,
                    f"PERFORMANCE ALERT [{severity.upper()}] {category}: {message}",
                )

                # Take automated action for critical alerts
                if severity == "critical":
                    await self._handle_critical_alert(alert)

        except Exception as e:
            logger.error(f"Error handling performance alert: {e}")

    async def _handle_critical_alert(self, alert):
        """Handle critical performance alerts with automated responses"""
        try:
            category = alert.get("category", "")

            if (
                category == "gpu"
                and "thermal throttling" in alert.get("message", "").lower()
            ):
                logger.critical("GPU thermal throttling detected - reducing GPU load")
                # Could implement automated GPU load reduction here

            elif category == "memory" and alert.get("message", "").find("90") != -1:
                logger.critical("High memory usage detected - triggering cleanup")
                # Could implement automated memory cleanup here

            elif (
                category == "service" and "critical" in alert.get("message", "").lower()
            ):
                logger.critical("Critical service issue detected")
                # Could implement service restart or fallback here

        except Exception as e:
            logger.error(f"Error handling critical alert: {e}")

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
            results["performance_metrics"] = await collect_phase9_metrics()

            # GPU optimization test
            if self.config["gpu_optimization_enabled"]:
                logger.info("Testing GPU optimization...")
                results["optimization_results"] = await optimize_gpu_for_multimodal()

            # Save results
            benchmark_file = f"/tmp/phase9_benchmark_{int(time.time())}.json"
            with open(benchmark_file, "w") as f:
                json.dump(results, f, indent=2, default=str)

            logger.info(
                f"Benchmark suite completed. Results saved to: {benchmark_file}"
            )
            return results

        except Exception as e:
            logger.error(f"Benchmark suite failed: {e}")
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
                "npu_available": phase9_monitor.npu_available,
            },
        }


async def main():
    """Main function for Phase 9 monitoring management"""
    parser = argparse.ArgumentParser(
        description="AutoBot Phase 9 Performance Monitoring"
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "benchmark", "test"],
        help="Command to execute",
    )
    parser.add_argument("--config", type=str, help="Configuration file path")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize monitoring manager
    manager = Phase9MonitoringManager()

    # Load configuration if provided
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, "r") as f:
                config_updates = json.load(f)
                manager.config.update(config_updates)
                logger.info(f"Configuration loaded from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")

    try:
        if args.command == "start":
            # Initialize and start monitoring
            if await manager.initialize():
                if await manager.start_monitoring():
                    logger.info("Phase 9 monitoring started successfully")

                    if args.daemon:
                        logger.info("Running in daemon mode...")
                        try:
                            while True:
                                await asyncio.sleep(60)
                                status = manager.get_status_report()
                                if not status["monitoring_active"]:
                                    break
                        except KeyboardInterrupt:
                            logger.info("Received interrupt signal")
                        finally:
                            await manager.stop_monitoring()
                    else:
                        logger.info(
                            "Monitoring started. Use 'stop' command to stop monitoring."
                        )
                else:
                    logger.error("Failed to start monitoring")
                    sys.exit(1)
            else:
                logger.error("Failed to initialize monitoring")
                sys.exit(1)

        elif args.command == "stop":
            if await manager.stop_monitoring():
                logger.info("Monitoring stopped successfully")
            else:
                logger.error("Failed to stop monitoring")
                sys.exit(1)

        elif args.command == "status":
            status = manager.get_status_report()
            print(json.dumps(status, indent=2))

        elif args.command == "benchmark":
            await manager.initialize()
            results = await manager.run_benchmark_suite()
            print(json.dumps(results, indent=2, default=str))

        elif args.command == "test":
            # Quick test of monitoring components
            logger.info("Running quick test of monitoring components...")

            await manager.initialize()

            # Test metrics collection
            metrics = await collect_phase9_metrics()
            logger.info(
                f"Metrics collection test: {'✓' if metrics.get('collection_successful') else '✗'}"
            )

            # Test GPU capabilities
            capabilities = get_gpu_capabilities()
            logger.info(
                f"GPU capabilities test: {'✓' if capabilities['gpu_available'] else '✗'}"
            )

            # Test efficiency monitoring
            efficiency = await monitor_gpu_efficiency()
            logger.info(
                f"Efficiency monitoring test: {'✓' if 'overall_efficiency' in efficiency else '✗'}"
            )

            logger.info("Component tests completed")

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        if manager.monitoring_active:
            await manager.stop_monitoring()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
