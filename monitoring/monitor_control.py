#!/usr/bin/env python3
"""
AutoBot Monitor Control
Centralized control system for managing all AutoBot performance monitoring components.
Provides unified interface for monitoring, optimization, benchmarking, and alerting.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import yaml
from src.constants.network_constants import NetworkConstants

from performance_monitor import PerformanceMonitor
from performance_optimizer import PerformanceOptimizer
from performance_benchmark import PerformanceBenchmark

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
                "db_query_time": 1.0
            },
            "log_level": "INFO"
        }

        if Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    loaded_config = yaml.safe_load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
        else:
            # Create default config file
            with open(config_path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)

        return MonitoringConfig(**default_config)

    def setup_logging(self):
        """Configure logging for the monitoring system."""
        log_dir = Path("/home/kali/Desktop/AutoBot/logs")
        log_dir.mkdir(exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_dir / "monitoring_control.log"),
                logging.handlers.RotatingFileHandler(
                    log_dir / "monitoring_control_detailed.log",
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                )
            ]
        )

    async def start_dashboard(self):
        """Start the performance dashboard web interface."""
        if not self.config.dashboard_enabled:
            self.logger.info("Dashboard disabled in configuration")
            return

        try:
            dashboard_script = Path(__file__).parent / "performance_dashboard.py"

            self.dashboard_process = await asyncio.create_subprocess_exec(
                sys.executable, str(dashboard_script),
                "--port", str(self.config.dashboard_port),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait a moment to see if it starts successfully
            await asyncio.sleep(2)

            if self.dashboard_process.returncode is None:
                self.logger.info(f"📊 Performance dashboard started on port {self.config.dashboard_port}")
                self.logger.info(f"   Access at: http://localhost:{self.config.dashboard_port}")
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
                if 'system' in metrics:
                    sys_metrics = metrics['system']
                    self.logger.info(
                        f"System: CPU={sys_metrics.cpu_percent:.1f}% "
                        f"MEM={sys_metrics.memory_percent:.1f}% "
                        f"DISK={sys_metrics.disk_percent:.1f}%"
                    )

                # Check for alerts
                alerts = metrics.get('alerts', [])
                if alerts:
                    for alert in alerts:
                        self.logger.warning(f"🚨 ALERT: {alert}")

                # Log service health
                services = metrics.get('services', [])
                healthy_services = sum(1 for s in services if s.is_healthy)
                total_services = len(services)

                if total_services > 0:
                    health_percentage = (healthy_services / total_services) * 100
                    if health_percentage < 100:
                        self.logger.warning(f"Services: {healthy_services}/{total_services} healthy ({health_percentage:.1f}%)")
                    else:
                        self.logger.info(f"Services: {healthy_services}/{total_services} healthy")

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

        self.logger.info(f"📈 Starting benchmark scheduler (schedule: {self.config.benchmark_schedule})")

        # Calculate interval based on schedule
        if self.config.benchmark_schedule == "daily":
            interval = 24 * 60 * 60  # 24 hours
        elif self.config.benchmark_schedule == "weekly":
            interval = 7 * 24 * 60 * 60  # 7 days
        else:
            self.logger.error(f"Unknown benchmark schedule: {self.config.benchmark_schedule}")
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

    async def run_single_benchmark(self, test_type: str = "comprehensive", duration: int = 60) -> Dict[str, Any]:
        """Run a single benchmark test."""
        self.logger.info(f"🚀 Running {test_type} benchmark")

        try:
            if test_type == "comprehensive":
                return await self.benchmark.run_comprehensive_benchmark()
            elif test_type == "api":
                results = await self.benchmark.run_api_benchmark(duration_seconds=duration)
                return {"api_results": [result.__dict__ for result in results]}
            elif test_type == "database":
                results = await self.benchmark.run_database_benchmark(duration_seconds=duration)
                return {"database_results": [result.__dict__ for result in results]}
            elif test_type == "network":
                results = await self.benchmark.run_network_benchmark(duration_seconds=duration)
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
                    "dashboard_port": self.config.dashboard_port if self.config.dashboard_enabled else None
                },
                "system_health": {
                    "overall_score": self._calculate_health_score(metrics),
                    "active_alerts": len(metrics.get('alerts', [])),
                    "healthy_services": sum(1 for s in metrics.get('services', []) if s.is_healthy),
                    "total_services": len(metrics.get('services', []))
                },
                "performance_metrics": {
                    "cpu_percent": metrics.get('system', {}).get('cpu_percent', 0),
                    "memory_percent": metrics.get('system', {}).get('memory_percent', 0),
                    "disk_percent": metrics.get('system', {}).get('disk_percent', 0),
                    "gpu_utilization": metrics.get('system', {}).get('gpu_utilization'),
                    "npu_utilization": metrics.get('system', {}).get('npu_utilization')
                },
                "recommendations": {
                    "total_count": len(recommendations),
                    "critical": len([r for r in recommendations if r.severity == "critical"]),
                    "high": len([r for r in recommendations if r.severity == "high"]),
                    "auto_applicable": len([r for r in recommendations if r.auto_applicable])
                }
            }

            return status

        except Exception as e:
            self.logger.error(f"Error getting current status: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "monitoring": {"running": self.running}
            }

    def _calculate_health_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate overall system health score (0-100)."""
        try:
            score = 100.0

            # Get thresholds from loaded config
            thresholds = self.config.alert_thresholds or {}
            cpu_threshold = thresholds.get('cpu_percent', 80.0)
            memory_threshold = thresholds.get('memory_percent', 85.0)
            disk_threshold = thresholds.get('disk_percent', 90.0)

            # Deduct points for system resource issues
            if 'system' in metrics:
                sys_metrics = metrics['system']

                # CPU usage penalty
                if sys_metrics.cpu_percent > cpu_threshold:
                    score -= min(20, (sys_metrics.cpu_percent - cpu_threshold) / 2)

                # Memory usage penalty
                if sys_metrics.memory_percent > memory_threshold:
                    score -= min(20, (sys_metrics.memory_percent - memory_threshold) / 1.5)

                # Disk usage penalty
                if sys_metrics.disk_percent > disk_threshold:
                    score -= min(15, (sys_metrics.disk_percent - disk_threshold) / 1)

            # Deduct points for unhealthy services
            services = metrics.get('services', [])
            if services:
                unhealthy_services = sum(1 for s in services if not s.is_healthy)
                service_penalty = (unhealthy_services / len(services)) * 30
                score -= service_penalty

            # Deduct points for alerts
            alerts = metrics.get('alerts', [])
            critical_alerts = sum(1 for alert in alerts if 'DOWN' in alert or 'ERROR' in alert)
            warning_alerts = len(alerts) - critical_alerts

            score -= critical_alerts * 15  # 15 points per critical alert
            score -= warning_alerts * 5    # 5 points per warning alert

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

    async def _print_startup_summary(self):
        """Print startup summary information."""
        print("\n" + "="*80)
        print("🤖 AutoBot Performance Monitoring System - ACTIVE")
        print("="*80)

        print(f"📊 Dashboard: {'Enabled' if self.config.dashboard_enabled else 'Disabled'}")
        if self.config.dashboard_enabled:
            print(f"   URL: http://localhost:{self.config.dashboard_port}")

        print(f"🔍 Monitoring: Every {self.config.monitoring_interval}s")
        print(f"🔧 Optimization: {'Enabled' if self.config.auto_optimization_enabled else 'Disabled'}")
        if self.config.auto_optimization_enabled:
            print(f"   Cycle: Every {self.config.optimization_interval//60} minutes")

        print(f"📈 Benchmarks: {self.config.benchmark_schedule}")

        # Get and display current system status
        status = await self.get_current_status()
        health_score = status['system_health']['overall_score']

        print(f"\n📋 Current System Health: {health_score}/100")

        perf = status['performance_metrics']
        print(f"   CPU: {perf['cpu_percent']:.1f}%")
        print(f"   Memory: {perf['memory_percent']:.1f}%")
        print(f"   Disk: {perf['disk_percent']:.1f}%")
        if perf['gpu_utilization'] is not None:
            print(f"   GPU: {perf['gpu_utilization']:.1f}%")

        services = status['system_health']
        print(f"   Services: {services['healthy_services']}/{services['total_services']} healthy")

        if status['system_health']['active_alerts'] > 0:
            print(f"   🚨 Active Alerts: {status['system_health']['active_alerts']}")

        recs = status['recommendations']
        if recs['total_count'] > 0:
            print(f"   📋 Optimization Opportunities: {recs['total_count']} (Critical: {recs['critical']}, High: {recs['high']})")

        print("\n🎯 Monitoring AutoBot distributed system:")
        print(f"   • Main (WSL): {NetworkConstants.MAIN_MACHINE_IP} - Backend API")
        print(f"   • Frontend VM: {NetworkConstants.FRONTEND_VM_IP} - Web Interface")
        print(f"   • NPU Worker VM: {NetworkConstants.NPU_WORKER_VM_IP} - AI Acceleration")
        print(f"   • Redis VM: {NetworkConstants.REDIS_VM_IP} - Data Layer")
        print(f"   • AI Stack VM: {NetworkConstants.AI_STACK_VM_IP} - AI Processing")
        print(f"   • Browser VM: {NetworkConstants.BROWSER_VM_IP} - Web Automation")

        print(f"\n💾 Logs: /home/kali/Desktop/AutoBot/logs/")
        print(f"📊 Results: /home/kali/Desktop/AutoBot/logs/benchmarks/")

        print("\n🔧 Control Commands:")
        print("   • Press Ctrl+C to stop monitoring")
        print("   • Use --status to check current state")
        print("   • Use --benchmark to run performance tests")

        print("="*80)

async def main():
    """Main function for monitor control."""
    import argparse

    parser = argparse.ArgumentParser(description='AutoBot Monitor Control System')

    # Main actions
    parser.add_argument('--start', action='store_true', help='Start all monitoring components')
    parser.add_argument('--stop', action='store_true', help='Stop all monitoring components')
    parser.add_argument('--status', action='store_true', help='Show current monitoring status')
    parser.add_argument('--restart', action='store_true', help='Restart all monitoring components')

    # Specific component controls
    parser.add_argument('--dashboard-only', action='store_true', help='Start only the dashboard')
    parser.add_argument('--monitor-only', action='store_true', help='Start only monitoring (no optimization)')
    parser.add_argument('--optimize-once', action='store_true', help='Run single optimization cycle')

    # Benchmark controls
    parser.add_argument('--benchmark', choices=['comprehensive', 'api', 'database', 'network', 'system'],
                       help='Run performance benchmark')
    parser.add_argument('--benchmark-duration', type=int, default=60, help='Benchmark duration in seconds')

    # Configuration
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    # Initialize monitor control
    monitor_control = MonitorControl(config_path=args.config)

    try:
        if args.status:
            # Show current status
            print("🔍 Getting AutoBot monitoring status...")
            status = await monitor_control.get_current_status()

            print("\n" + "="*60)
            print("AutoBot Monitoring Status")
            print("="*60)

            monitoring = status['monitoring']
            print(f"Monitoring Running: {'Yes' if monitoring['running'] else 'No'}")
            print(f"Dashboard: {'Enabled' if monitoring['dashboard_enabled'] else 'Disabled'}")
            if monitoring['dashboard_enabled']:
                print(f"Dashboard Port: {monitoring['dashboard_port']}")
            print(f"Auto-Optimization: {'Enabled' if monitoring['optimization_enabled'] else 'Disabled'}")

            health = status['system_health']
            print(f"\nSystem Health Score: {health['overall_score']}/100")
            print(f"Healthy Services: {health['healthy_services']}/{health['total_services']}")
            print(f"Active Alerts: {health['active_alerts']}")

            perf = status['performance_metrics']
            print(f"\nCurrent Performance:")
            print(f"  CPU Usage: {perf['cpu_percent']:.1f}%")
            print(f"  Memory Usage: {perf['memory_percent']:.1f}%")
            print(f"  Disk Usage: {perf['disk_percent']:.1f}%")
            if perf['gpu_utilization'] is not None:
                print(f"  GPU Utilization: {perf['gpu_utilization']:.1f}%")

            recs = status['recommendations']
            if recs['total_count'] > 0:
                print(f"\nOptimization Opportunities: {recs['total_count']}")
                print(f"  Critical: {recs['critical']}")
                print(f"  High Priority: {recs['high']}")
                print(f"  Auto-Applicable: {recs['auto_applicable']}")

        elif args.benchmark:
            # Run benchmark
            results = await monitor_control.run_single_benchmark(
                test_type=args.benchmark,
                duration=args.benchmark_duration
            )

            print(f"\n📈 {args.benchmark.title()} Benchmark Complete")

            if args.benchmark == "comprehensive":
                summary = results['summary']
                print(f"Overall Score: {summary['overall_system_score']:.1f}/100 (Grade: {summary['performance_grade']})")
                print(f"Total Tests: {summary['total_tests']}")
            else:
                print(f"Results saved to logs/benchmarks/")

        elif args.optimize_once:
            # Run single optimization cycle
            print("🔧 Running single optimization cycle...")
            await monitor_control.optimizer.run_optimization_cycle()
            print("✅ Optimization cycle complete")

        elif args.dashboard_only:
            # Start only dashboard
            print("📊 Starting performance dashboard only...")
            await monitor_control.start_dashboard()
            print("Dashboard running. Press Ctrl+C to stop.")

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                await monitor_control.stop_dashboard()

        elif args.monitor_only:
            # Start only monitoring
            print("🔍 Starting monitoring only (no optimization)...")
            monitor_control.config.auto_optimization_enabled = False
            monitor_control.config.dashboard_enabled = False
            await monitor_control.start_all()

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                await monitor_control.stop_all()

        elif args.stop:
            # Stop all components
            await monitor_control.stop_all()

        elif args.restart:
            # Restart all components
            await monitor_control.stop_all()
            await asyncio.sleep(2)
            await monitor_control.start_all()

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                await monitor_control.stop_all()

        elif args.start or len(sys.argv) == 1:
            # Start all monitoring (default action)
            await monitor_control.start_all()

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                await monitor_control.stop_all()

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
        await monitor_control.stop_all()
    except Exception as e:
        print(f"❌ Error: {e}")
        await monitor_control.stop_all()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
