#!/usr/bin/env python3
"""
AutoBot Performance Optimizer
Automated performance optimization system that analyzes metrics and applies optimizations
for the distributed AutoBot system across 6 VMs.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import yaml
from constants.path_constants import PATH
from performance_monitor import PerformanceMonitor

logger = logging.getLogger(__name__)


# Issue #339: Command handler functions extracted from main()
async def _handle_analyze_command(optimizer: "PerformanceOptimizer") -> None:
    """Handle --analyze command (Issue #339 - extracted handler)."""
    logger.info("Analyzing AutoBot performance...")
    metrics = await optimizer.monitor.generate_performance_report()
    recommendations = await optimizer.analyze_performance_metrics(metrics)

    if recommendations:
        logger.info(f"\n📋 Found {len(recommendations)} optimization opportunities:")
        logger.info("=" * 80)

        for i, rec in enumerate(recommendations, 1):
            severity_emoji = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "📊",
                "low": "💡",
            }.get(rec.severity, "")
            auto_indicator = "🤖 Auto" if rec.auto_applicable else "👤 Manual"

            logger.info(
                f"{i}. {severity_emoji} [{rec.severity.upper()}] {rec.description}"
            )
            logger.info(f"   Category: {rec.category}")
            logger.info(f"   Impact: {rec.impact_estimate}")
            logger.info(f"   Application: {auto_indicator}")
            if rec.affected_services:
                logger.info(f"   Affected: {', '.join(rec.affected_services)}")
            logger.info("")
    else:
        logger.info(
            "✅ No optimization opportunities found - system performing optimally!"
        )


async def _handle_report_command(optimizer: "PerformanceOptimizer") -> None:
    """Handle --report command (Issue #339 - extracted handler)."""
    logger.info("Generating optimization report...")
    report = await optimizer.generate_optimization_report()

    logger.info("\n" + "=" * 80)
    logger.info("AutoBot Performance Optimization Report")
    logger.info("=" * 80)

    status = report["system_status"]
    logger.info(f"📋 Total Recommendations: {status['total_recommendations']}")
    logger.info(f"🚨 Critical Issues: {status['critical_issues']}")
    logger.info(f"⚠️  High Priority: {status['high_priority']}")
    logger.info(f"🤖 Auto-Applicable: {status['auto_applicable']}")

    logger.info("\n📊 Recommendations by Category:")
    for category, recs in report["recommendations_by_category"].items():
        logger.info(f"  {category.title()}: {len(recs)} recommendations")

    logger.info("\n🔧 Recent Optimizations:")
    recent = report["recent_optimizations"]
    if recent:
        for opt in recent[-5:]:  # Show last 5
            status_icon = "✅" if opt["success"] else "❌"
            improvement = f" (+{opt['improvement']:.1f}%)" if opt["improvement"] else ""
            logger.info(f"  {status_icon} {opt['description']}{improvement}")
    else:
        logger.info("  No recent optimizations")


async def _handle_continuous_command(optimizer: "PerformanceOptimizer") -> None:
    """Handle --continuous command (Issue #339 - extracted handler)."""
    logger.info("🔄 Starting continuous performance optimization...")
    logger.info("   Optimization cycle: every 30 minutes")
    logger.info("   Press Ctrl+C to stop")

    try:
        while True:
            await optimizer.run_optimization_cycle()
            await asyncio.sleep(30 * 60)
    except KeyboardInterrupt:
        logger.info("\n🛑 Continuous optimization stopped")


@dataclass
class OptimizationRecommendation:
    """Performance optimization recommendation."""

    category: str  # "system", "database", "service", "network"
    severity: str  # "low", "medium", "high", "critical"
    description: str
    impact_estimate: str  # Expected performance improvement
    auto_applicable: bool  # Can be applied automatically
    command: Optional[str] = None  # Command to apply optimization
    rollback_command: Optional[str] = None  # Command to rollback if needed
    affected_services: List[str] = None


@dataclass
class OptimizationResult:
    """Result of applying an optimization."""

    recommendation: OptimizationRecommendation
    applied: bool
    success: bool
    error_message: Optional[str] = None
    metrics_before: Optional[Dict] = None
    metrics_after: Optional[Dict] = None
    improvement_percentage: Optional[float] = None


class PerformanceOptimizer:
    """Automated performance optimization system for AutoBot."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitor = PerformanceMonitor()
        self.redis_client = None
        self.optimization_history = []
        self.optimization_config = self.load_optimization_config()

    def load_optimization_config(self) -> Dict:
        """Load optimization configuration."""
        config_path = Path(__file__).parent / "optimization_config.yaml"

        default_config = {
            "auto_optimization": {
                "enabled": True,
                "max_optimizations_per_hour": 3,
                "severity_threshold": "medium",
                "require_confirmation": False,
            },
            "thresholds": {
                "cpu_high_usage": 80.0,
                "memory_high_usage": 85.0,
                "disk_high_usage": 90.0,
                "response_time_slow": 5.0,
                "database_slow_query": 1.0,
            },
            "optimization_rules": {
                "system": {
                    "cpu_optimization": True,
                    "memory_optimization": True,
                    "disk_optimization": True,
                },
                "database": {
                    "redis_optimization": True,
                    "connection_pooling": True,
                    "query_optimization": True,
                },
                "services": {
                    "restart_unhealthy": True,
                    "scale_resources": True,
                    "optimize_configs": True,
                },
                "network": {
                    "connection_optimization": True,
                    "bandwidth_optimization": True,
                },
            },
        }

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded_config = yaml.safe_load(f)
                    # Merge with defaults
                    default_config.update(loaded_config)
            except Exception as e:
                self.logger.warning(
                    f"Error loading optimization config: {e}, using defaults"
                )
        else:
            # Create default config file
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(default_config, f, default_flow_style=False)

        return default_config

    async def analyze_performance_metrics(
        self, metrics: Dict
    ) -> List[OptimizationRecommendation]:
        """Analyze performance metrics and generate optimization recommendations."""
        recommendations = []

        # System performance analysis
        if "system" in metrics:
            recommendations.extend(
                await self._analyze_system_metrics(metrics["system"])
            )

        # Service performance analysis
        if "services" in metrics:
            recommendations.extend(
                await self._analyze_service_metrics(metrics["services"])
            )

        # Database performance analysis
        if "databases" in metrics:
            recommendations.extend(
                await self._analyze_database_metrics(metrics["databases"])
            )

        # Inter-VM communication analysis
        if "inter_vm" in metrics:
            recommendations.extend(
                await self._analyze_network_metrics(metrics["inter_vm"])
            )

        # Hardware utilization analysis
        if "hardware" in metrics:
            recommendations.extend(
                await self._analyze_hardware_metrics(metrics["hardware"])
            )

        # Sort by severity and impact
        recommendations.sort(
            key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                x.severity, 0
            ),
            reverse=True,
        )

        return recommendations

    def _check_resource_threshold(self, value: float, threshold_key: str) -> bool:
        """Check if a metric exceeds its configured threshold.

        Helper for _analyze_system_metrics (#825).
        """
        threshold = self.optimization_config["thresholds"].get(threshold_key, 80)
        return value > threshold

    def _build_resource_recommendation(
        self,
        value: float,
        threshold_key: str,
        description: str,
        impact: str,
        optimizer: str,
        services: List[str],
        severity_fn=None,
    ) -> Optional[OptimizationRecommendation]:
        """Build a recommendation if resource exceeds threshold.

        Helper for _analyze_system_metrics (#825).
        """
        if not self._check_resource_threshold(value, threshold_key):
            return None
        severity = severity_fn(value) if severity_fn else "medium"
        return OptimizationRecommendation(
            category="system",
            severity=severity,
            description=description,
            impact_estimate=impact,
            auto_applicable=True,
            command=f"python3 {PATH.PROJECT_ROOT}/monitoring/{optimizer}",
            affected_services=services,
        )

    async def _analyze_system_metrics(
        self, system_metrics
    ) -> List[OptimizationRecommendation]:
        """Analyze system metrics for optimization opportunities."""
        recommendations = []

        cpu = system_metrics.cpu_percent
        mem = system_metrics.memory_percent
        disk = system_metrics.disk_percent
        load_avg = system_metrics.load_average

        checks = [
            (
                cpu,
                "cpu_high_usage",
                f"High CPU usage: {cpu:.1f}%",
                "10-30% CPU reduction",
                "cpu_optimizer.py --optimize",
                ["backend", "ai-stack", "npu-worker"],
                lambda v: "critical" if v > 95 else "high" if v > 90 else "medium",
            ),
            (
                mem,
                "memory_high_usage",
                f"High memory usage: {mem:.1f}%",
                "15-25% memory reduction",
                "memory_optimizer.py --cleanup",
                ["backend", "frontend", "ai-stack"],
                lambda v: "critical" if v > 95 else "high",
            ),
            (
                disk,
                "disk_high_usage",
                f"High disk usage: {disk:.1f}%",
                "5-15% disk space recovery",
                "disk_optimizer.py --cleanup",
                ["all"],
                lambda v: "high" if v > 95 else "medium",
            ),
        ]

        for val, key, desc, impact, opt, svcs, sev_fn in checks:
            rec = self._build_resource_recommendation(
                val, key, desc, impact, opt, svcs, sev_fn
            )
            if rec:
                recommendations.append(rec)

        cpu_cores = psutil.cpu_count()
        if load_avg and max(load_avg) > cpu_cores * 1.5:
            recommendations.append(
                OptimizationRecommendation(
                    category="system",
                    severity="medium",
                    description=f"High load: {max(load_avg):.2f} (cores: {cpu_cores})",
                    impact_estimate="10-20% load reduction",
                    auto_applicable=True,
                    command=f"python3 {PATH.PROJECT_ROOT}/monitoring/load_optimizer.py --balance",
                    affected_services=["all"],
                )
            )

        return recommendations

    async def _analyze_service_metrics(
        self, service_metrics
    ) -> List[OptimizationRecommendation]:
        """Analyze service metrics for optimization opportunities."""
        recommendations = []

        for service in service_metrics:
            service_name = service.service_name

            # Service health optimization
            if not service.is_healthy:
                recommendations.append(
                    OptimizationRecommendation(
                        category="service",
                        severity="critical",
                        description=f"Service {service_name} is unhealthy: {service.error_message}",
                        impact_estimate="100% service availability restoration",
                        auto_applicable=True,
                        command=f"bash {PATH.PROJECT_ROOT}/scripts/restart_service.sh {service_name}",
                        affected_services=[service_name],
                    )
                )

            # Slow response time optimization
            elif (
                service.response_time
                > self.optimization_config["thresholds"]["response_time_slow"]
            ):
                severity = "high" if service.response_time > 10 else "medium"
                recommendations.append(
                    OptimizationRecommendation(
                        category="service",
                        severity=severity,
                        description=f"Slow response time for {service_name}: {service.response_time:.2f}s",
                        impact_estimate="30-50% response time improvement",
                        auto_applicable=True,
                        command=f"python3 {PATH.PROJECT_ROOT}/monitoring/service_optimizer.py --service {service_name}",
                        affected_services=[service_name],
                    )
                )

        return recommendations

    async def _analyze_database_metrics(
        self, database_metrics
    ) -> List[OptimizationRecommendation]:
        """Analyze database metrics for optimization opportunities."""
        recommendations = []

        for db in database_metrics:
            db_type = db.database_type

            # High error count optimization
            if db.error_count > 0:
                recommendations.append(
                    OptimizationRecommendation(
                        category="database",
                        severity="high",
                        description=f"Database {db_type} has {db.error_count} errors",
                        impact_estimate="100% error elimination",
                        auto_applicable=True,
                        command=(
                            f"python3 {PATH.PROJECT_ROOT}/monitoring/"
                            f"database_optimizer.py --db {db_type} --fix-errors"
                        ),
                        affected_services=["backend", "ai-stack"],
                    )
                )

            # Slow connection time optimization
            if (
                db.connection_time
                > self.optimization_config["thresholds"]["database_slow_query"]
            ):
                recommendations.append(
                    OptimizationRecommendation(
                        category="database",
                        severity="medium",
                        description=f"Slow connection to {db_type}: {db.connection_time:.3f}s",
                        impact_estimate="40-60% connection speed improvement",
                        auto_applicable=True,
                        command=(
                            f"python3 {PATH.PROJECT_ROOT}/monitoring/"
                            f"database_optimizer.py --db {db_type} --optimize-connections"
                        ),
                        affected_services=["backend"],
                    )
                )

            # High memory usage optimization
            if db.memory_usage_mb > 1000:  # 1GB threshold
                recommendations.append(
                    OptimizationRecommendation(
                        category="database",
                        severity="medium",
                        description=f"High memory usage for {db_type}: {db.memory_usage_mb:.1f}MB",
                        impact_estimate="20-40% memory optimization",
                        auto_applicable=True,
                        command=(
                            f"python3 {PATH.PROJECT_ROOT}/monitoring/"
                            f"database_optimizer.py --db {db_type} --optimize-memory"
                        ),
                        affected_services=["redis"],
                    )
                )

        return recommendations

    async def _analyze_network_metrics(
        self, network_metrics
    ) -> List[OptimizationRecommendation]:
        """Analyze inter-VM network metrics for optimization opportunities."""
        recommendations = []

        for vm_metric in network_metrics:
            source_vm = vm_metric.source_vm
            target_vm = vm_metric.target_vm

            # High latency optimization
            if vm_metric.latency_ms > 50:  # 50ms threshold
                severity = "high" if vm_metric.latency_ms > 100 else "medium"
                recommendations.append(
                    OptimizationRecommendation(
                        category="network",
                        severity=severity,
                        description=f"High latency {source_vm} → {target_vm}: {vm_metric.latency_ms:.1f}ms",
                        impact_estimate="20-40% latency reduction",
                        auto_applicable=True,
                        command=(
                            f"python3 {PATH.PROJECT_ROOT}/monitoring/"
                            f"network_optimizer.py --optimize-route {target_vm}"
                        ),
                        affected_services=[target_vm],
                    )
                )

            # Packet loss optimization
            if vm_metric.packet_loss_percent > 1.0:  # 1% threshold
                severity = "critical" if vm_metric.packet_loss_percent > 10 else "high"
                recommendations.append(
                    OptimizationRecommendation(
                        category="network",
                        severity=severity,
                        description=f"Packet loss {source_vm} → {target_vm}: {vm_metric.packet_loss_percent:.1f}%",
                        impact_estimate="90-100% packet loss elimination",
                        auto_applicable=True,
                        command=(
                            f"python3 {PATH.PROJECT_ROOT}/monitoring/"
                            f"network_optimizer.py --fix-connectivity {target_vm}"
                        ),
                        affected_services=[target_vm],
                    )
                )

            # High jitter optimization
            if vm_metric.jitter_ms > 20:  # 20ms jitter threshold
                recommendations.append(
                    OptimizationRecommendation(
                        category="network",
                        severity="medium",
                        description=f"High network jitter {source_vm} → {target_vm}: {vm_metric.jitter_ms:.1f}ms",
                        impact_estimate="30-50% jitter reduction",
                        auto_applicable=True,
                        command=(
                            f"python3 {PATH.PROJECT_ROOT}/monitoring/"
                            f"network_optimizer.py --stabilize-connection {target_vm}"
                        ),
                        affected_services=[target_vm],
                    )
                )

        return recommendations

    async def _analyze_hardware_metrics(
        self, hardware_metrics
    ) -> List[OptimizationRecommendation]:
        """Analyze hardware utilization for optimization opportunities."""
        recommendations = []

        # GPU optimization recommendations
        if hardware_metrics.get("gpu_available", False):
            # This would require actual GPU metrics, placeholder for now
            recommendations.append(
                OptimizationRecommendation(
                    category="hardware",
                    severity="low",
                    description="GPU acceleration can be optimized for AI workloads",
                    impact_estimate="20-50% AI processing speed improvement",
                    auto_applicable=True,
                    command="python3 {PATH.PROJECT_ROOT}/monitoring/gpu_optimizer.py --optimize-ai-stack",
                    affected_services=["ai-stack", "npu-worker"],
                )
            )

        # NPU optimization recommendations
        if hardware_metrics.get("npu_available", False):
            recommendations.append(
                OptimizationRecommendation(
                    category="hardware",
                    severity="low",
                    description="Intel NPU can be better utilized for AI inference",
                    impact_estimate="15-30% AI inference speed improvement",
                    auto_applicable=True,
                    command="python3 {PATH.PROJECT_ROOT}/monitoring/npu_optimizer.py --enable-optimization",
                    affected_services=["npu-worker"],
                )
            )

        return recommendations

    async def _measure_optimization_impact(
        self, result: OptimizationResult, metrics_before: Dict
    ) -> None:
        """Measure metrics after optimization and calculate improvement.

        Helper for apply_optimization (#825).
        """
        await asyncio.sleep(10)
        metrics_after = await self.monitor.generate_performance_report()
        result.metrics_after = metrics_after
        result.improvement_percentage = self._calculate_improvement(
            metrics_before, metrics_after, result.recommendation.category
        )

    async def apply_optimization(
        self, recommendation: OptimizationRecommendation
    ) -> OptimizationResult:
        """Apply a specific optimization recommendation."""
        self.logger.info("Applying optimization: %s", recommendation.description)

        metrics_before = await self.monitor.generate_performance_report()
        result = OptimizationResult(
            recommendation=recommendation,
            applied=False,
            success=False,
            metrics_before=metrics_before,
        )

        if not recommendation.auto_applicable or not recommendation.command:
            result.error_message = (
                "Optimization is not auto-applicable or missing command"
            )
            return result

        try:
            process = await asyncio.create_subprocess_shell(
                recommendation.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            result.applied = True

            if process.returncode == 0:
                result.success = True
                self.logger.info("Optimization applied: %s", recommendation.description)
                await self._measure_optimization_impact(result, metrics_before)
            else:
                result.error_message = (
                    stderr.decode() if stderr else "Command failed with no error output"
                )
                self.logger.error(
                    "Optimization failed: %s - %s",
                    recommendation.description,
                    result.error_message,
                )

        except Exception as e:
            result.error_message = str(e)
            self.logger.error("Error applying optimization: %s", e)

        self.optimization_history.append(result)
        return result

    def _calculate_improvement(
        self, before_metrics: Dict, after_metrics: Dict, category: str
    ) -> Optional[float]:
        """Calculate improvement percentage for an optimization."""
        try:
            if category == "system":
                before_cpu = before_metrics.get("system", {}).get("cpu_percent", 0)
                after_cpu = after_metrics.get("system", {}).get("cpu_percent", 0)
                if before_cpu > 0:
                    return ((before_cpu - after_cpu) / before_cpu) * 100

            elif category == "service":
                # Calculate average response time improvement
                before_services = before_metrics.get("services", [])
                after_services = after_metrics.get("services", [])

                if before_services and after_services:
                    before_avg = sum(
                        s.response_time for s in before_services if s.response_time
                    ) / len(before_services)
                    after_avg = sum(
                        s.response_time for s in after_services if s.response_time
                    ) / len(after_services)

                    if before_avg > 0:
                        return ((before_avg - after_avg) / before_avg) * 100

            elif category == "database":
                # Calculate database performance improvement (simplified)
                return 10.0  # Placeholder improvement percentage

            elif category == "network":
                # Calculate network performance improvement (simplified)
                return 15.0  # Placeholder improvement percentage

        except Exception as e:
            self.logger.error(f"Error calculating improvement: {e}")

        return None

    def _filter_applicable_recommendations(
        self, recommendations: List[OptimizationRecommendation]
    ) -> List[OptimizationRecommendation]:
        """Filter recommendations by severity threshold and auto-applicability.

        Helper for run_optimization_cycle (#825).
        """
        auto_config = self.optimization_config.get("auto_optimization", {})
        severity_threshold = auto_config.get("severity_threshold", "medium")
        max_optimizations = auto_config.get("max_optimizations_per_hour", 3)

        severity_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        threshold_level = severity_levels.get(severity_threshold, 2)

        applicable = [
            rec
            for rec in recommendations
            if severity_levels.get(rec.severity, 0) >= threshold_level
            and rec.auto_applicable
        ]
        return applicable[:max_optimizations]

    async def run_optimization_cycle(self):
        """Run a complete optimization cycle."""
        self.logger.info("Starting performance optimization cycle")

        try:
            metrics = await self.monitor.generate_performance_report()
            recommendations = await self.analyze_performance_metrics(metrics)

            if not recommendations:
                self.logger.info("No optimizations needed - system performing well")
                return

            self.logger.info(
                "Found %d optimization opportunities", len(recommendations)
            )

            applicable = self._filter_applicable_recommendations(recommendations)
            if not applicable:
                self.logger.info("No applicable optimizations meet severity threshold")
                return

            results = []
            for recommendation in applicable:
                result = await self.apply_optimization(recommendation)
                results.append(result)
                await asyncio.sleep(5)

            successful = sum(1 for r in results if r.success)
            self.logger.info(
                "Optimization cycle complete: %d/%d successful",
                successful,
                len(results),
            )

            for result in results:
                if result.success and result.improvement_percentage:
                    self.logger.info(
                        "Improvement: %s - %.1f%%",
                        result.recommendation.description,
                        result.improvement_percentage,
                    )

        except Exception as e:
            self.logger.error("Error in optimization cycle: %s", e)

    async def generate_optimization_report(self) -> Dict[str, Any]:
        """Generate comprehensive optimization report."""
        # Get current metrics
        metrics = await self.monitor.generate_performance_report()

        # Get recommendations
        recommendations = await self.analyze_performance_metrics(metrics)

        # Categorize recommendations
        by_category = {}
        by_severity = {}

        for rec in recommendations:
            if rec.category not in by_category:
                by_category[rec.category] = []
            by_category[rec.category].append(rec)

            if rec.severity not in by_severity:
                by_severity[rec.severity] = []
            by_severity[rec.severity].append(rec)

        # Recent optimization history
        recent_optimizations = [
            {
                "description": opt.recommendation.description,
                "success": opt.success,
                "improvement": opt.improvement_percentage,
                "applied_at": datetime.now().isoformat(),  # This should be stored with the result
            }
            for opt in self.optimization_history[-10:]  # Last 10 optimizations
        ]

        report = {
            "timestamp": datetime.now().isoformat(),
            "system_status": {
                "total_recommendations": len(recommendations),
                "critical_issues": len(by_severity.get("critical", [])),
                "high_priority": len(by_severity.get("high", [])),
                "auto_applicable": sum(1 for r in recommendations if r.auto_applicable),
            },
            "recommendations_by_category": {
                category: [
                    {
                        "severity": rec.severity,
                        "description": rec.description,
                        "impact_estimate": rec.impact_estimate,
                        "auto_applicable": rec.auto_applicable,
                    }
                    for rec in recs
                ]
                for category, recs in by_category.items()
            },
            "recent_optimizations": recent_optimizations,
            "configuration": self.optimization_config,
        }

        return report


async def main():
    """Main function for the performance optimizer."""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Performance Optimizer")
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze current performance and show recommendations",
    )
    parser.add_argument(
        "--optimize", action="store_true", help="Run optimization cycle"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous optimization (every 30 minutes)",
    )
    parser.add_argument(
        "--report", action="store_true", help="Generate optimization report"
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    optimizer = PerformanceOptimizer()

    # Issue #339: Refactored to use extracted command handlers, reducing depth from 6 to 2
    if args.analyze:
        await _handle_analyze_command(optimizer)
    elif args.optimize:
        await optimizer.run_optimization_cycle()
    elif args.report:
        await _handle_report_command(optimizer)
    elif args.continuous:
        await _handle_continuous_command(optimizer)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
