# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Diagnostic System for AutoBot with Performance Optimization
Provides system health monitoring, error reporting, and recovery suggestions
"""

import asyncio
import gc
import logging
import platform
import subprocess  # nosec B404 - controlled system diagnostics
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil

try:
    from src.constants.threshold_constants import (
        ResourceThresholds,
        RetryConfig,
        TimingConstants,
    )
    from src.event_manager import event_manager
    from src.utils.redis_client import get_redis_client
except ImportError as e:
    logging.warning(f"Import error in diagnostics: {e}")

logger = logging.getLogger(__name__)


class PerformanceOptimizedDiagnostics:
    """
    Enhanced diagnostics with performance monitoring and timeout optimization
    """

    def __init__(self):
        """Initialize performance diagnostics with monitoring settings and Redis."""
        # Performance monitoring settings (Issue #376 - use named constants)
        self.max_user_permission_timeout = float(TimingConstants.SHORT_TIMEOUT)
        self.permission_retry_attempts = RetryConfig.MIN_RETRIES
        self.memory_warning_threshold = ResourceThresholds.MEMORY_WARNING_THRESHOLD

        self.system_info = self._get_system_info()
        self.redis_client = None
        self._initialize_redis()

        logger.info("Performance-optimized diagnostics initialized")

    def _initialize_redis(self):
        """Initialize Redis client with timeout protection"""
        try:
            self.redis_client = get_redis_client()
            if self.redis_client and self.redis_client.ping():
                logger.info("Diagnostics: Redis connection established")
            else:
                logger.warning("Diagnostics: Redis connection failed")
                self.redis_client = None
        except Exception as e:
            logger.error("Diagnostics: Redis initialization error: %s", e)
            self.redis_client = None

    def _get_system_info(self) -> Dict[str, Any]:
        """Gather comprehensive system information with performance metrics"""
        try:
            cpu_info = {
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "current_frequency": (
                    psutil.cpu_freq().current if psutil.cpu_freq() else None
                ),
                "usage_percent": psutil.cpu_percent(interval=1),
            }

            memory_info = psutil.virtual_memory()
            memory_data = {
                "total_gb": round(memory_info.total / (1024**3), 2),
                "available_gb": round(memory_info.available / (1024**3), 2),
                "used_percent": memory_info.percent,
                "warning": memory_info.percent > (self.memory_warning_threshold * 100),
            }

            # GPU Information (if available)
            gpu_info = self._get_gpu_info()

            return {
                "platform": platform.platform(),
                "python_version": sys.version,
                "cpu": cpu_info,
                "memory": memory_data,
                "gpu": gpu_info,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("Error gathering system info: %s", e)
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Get GPU information for performance monitoring"""
        try:
            result = subprocess.run(  # nosec B607 - nvidia-smi is safe
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=TimingConstants.MEDIUM_DELAY,  # Short timeout for GPU query
            )

            if result.returncode == 0:
                gpu_data = result.stdout.strip().split(", ")
                if len(gpu_data) >= 4:
                    return {
                        "name": gpu_data[0],
                        "memory_total_mb": int(gpu_data[1]),
                        "memory_used_mb": int(gpu_data[2]),
                        "utilization_percent": int(gpu_data[3]),
                        "memory_usage_percent": round(
                            (int(gpu_data[2]) / int(gpu_data[1])) * 100, 1
                        ),
                    }
            return {"status": "nvidia-smi not available or no GPU detected"}
        except Exception as e:
            return {"status": f"GPU detection error: {str(e)}"}

    async def _publish_permission_request(
        self, task_id: str, report: Dict[str, Any], attempt: int
    ) -> asyncio.Future:
        """Publish permission request and return future (Issue #315 - extracted helper)."""
        permission_future = asyncio.Future()
        await event_manager.publish(
            "log_message",
            {
                "task_id": task_id,
                "report": report,
                "question": (
                    "A task failed. Do you approve applying the suggested fixes? "
                    f"(Auto-timeout in {self.max_user_permission_timeout}s)"
                ),
                "attempt": attempt + 1,
                "max_attempts": self.permission_retry_attempts,
                "timeout_seconds": self.max_user_permission_timeout,
            },
        )
        logger.info(
            "Permission request sent for task %s (attempt %d/%d)",
            task_id,
            attempt + 1,
            self.permission_retry_attempts,
        )
        logger.info(
            "Waiting up to %ds for response...", self.max_user_permission_timeout
        )
        return permission_future

    async def _handle_permission_timeout(
        self, task_id: str, attempt: int, start_time: float
    ) -> bool:
        """Handle permission timeout with retry logic (Issue #315 - extracted helper)."""
        elapsed_time = time.time() - start_time
        logger.warning(
            "User permission timeout after %.2fs (attempt %s)",
            elapsed_time,
            attempt + 1,
        )

        if attempt < self.permission_retry_attempts - 1:
            await event_manager.publish(
                "log_message",
                {
                    "level": "WARNING",
                    "message": (
                        f"Permission request timeout (attempt {attempt + 1}). Retrying... "
                        f"({self.permission_retry_attempts - attempt - 1} attempts remaining)"
                    ),
                },
            )
            await asyncio.sleep(RetryConfig.BACKOFF_BASE)
            return True  # Should retry

        await self._handle_permission_timeout_fallback(task_id, elapsed_time)
        return False  # No more retries

    async def request_user_permission_optimized(
        self, task_id: str, report: Dict[str, Any]
    ) -> bool:
        """
        PERFORMANCE OPTIMIZED: Request user permission (Issue #315 - refactored depth 5 to 3).
        """
        start_time = time.time()

        for attempt in range(self.permission_retry_attempts):
            try:
                logger.info(
                    "Requesting user permission for task %s (attempt %s)",
                    task_id,
                    attempt + 1,
                )
                permission_future = await self._publish_permission_request(
                    task_id, report, attempt
                )

                try:
                    permission_granted = await asyncio.wait_for(
                        permission_future, timeout=self.max_user_permission_timeout
                    )
                    elapsed_time = time.time() - start_time
                    logger.info(
                        "User permission received in %.2fs: %s",
                        elapsed_time,
                        permission_granted,
                    )
                    return permission_granted

                except asyncio.TimeoutError:
                    should_retry = await self._handle_permission_timeout(
                        task_id, attempt, start_time
                    )
                    if not should_retry:
                        return False

            except Exception as e:
                logger.error(
                    "Error in permission request (attempt %s): %s", attempt + 1, e
                )
                if attempt == self.permission_retry_attempts - 1:
                    return False
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

        return False

    async def _handle_permission_timeout_fallback(
        self, task_id: str, elapsed_time: float
    ):
        """Handle user permission timeout with intelligent fallback"""
        await event_manager.publish(
            "log_message",
            {
                "level": "WARNING",
                "message": (
                    f"PERFORMANCE OPTIMIZATION: User permission for task {task_id} "
                    f"timed out after {elapsed_time:.2f}s. Using safe fallback (no fixes applied). "
                    f"This prevents system hangs. Previous timeout was 600s (10 minutes)."
                ),
            },
        )

        # Log performance improvement
        improvement_seconds = 600 - elapsed_time
        logger.info(
            f"TIMEOUT OPTIMIZATION: Saved {improvement_seconds:.2f}s by using "
            f"{self.max_user_permission_timeout}s timeout instead of 600s"
        )

    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resources with performance insights"""
        try:
            # Update system info
            self.system_info = self._get_system_info()

            # Analyze performance bottlenecks
            performance_analysis = self._analyze_performance_bottlenecks()

            return {
                "system_info": self.system_info,
                "performance_analysis": performance_analysis,
                "recommendations": self._generate_performance_recommendations(),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("Error checking system resources: %s", e)
            return {"error": str(e)}

    def _analyze_cpu_bottleneck(self, analysis: Dict[str, Any]) -> None:
        """Analyze CPU usage for bottlenecks (Issue #665: extracted helper)."""
        cpu_usage = self.system_info.get("cpu", {}).get("usage_percent", 0)
        cpu_high_pct = ResourceThresholds.CPU_HIGH_THRESHOLD * 100
        cpu_optimal_pct = ResourceThresholds.CPU_OPTIMAL_MAX * 100
        if cpu_usage > cpu_high_pct:
            analysis["bottlenecks"].append(
                {
                    "type": "cpu",
                    "severity": "high",
                    "message": f"CPU usage at {cpu_usage}% - potential bottleneck",
                }
            )
        elif cpu_usage < cpu_optimal_pct:
            analysis["optimal_areas"].append(
                {
                    "type": "cpu",
                    "message": (
                        f"CPU usage low at {cpu_usage}% - good performance headroom"
                    ),
                }
            )

    def _analyze_gpu_bottleneck(self, analysis: Dict[str, Any]) -> None:
        """Analyze GPU utilization for bottlenecks (Issue #665: extracted helper)."""
        gpu_info = self.system_info.get("gpu", {})
        gpu_util = gpu_info.get("utilization_percent")
        gpu_low_pct = ResourceThresholds.GPU_LOW_UTILIZATION * 100
        gpu_saturated_pct = ResourceThresholds.GPU_SATURATED * 100
        if gpu_util is not None:
            if gpu_util < gpu_low_pct:
                analysis["warnings"].append(
                    {
                        "type": "gpu",
                        "severity": "medium",
                        "message": (
                            f"GPU utilization low at {gpu_util}% - "
                            f"AI workloads may not be GPU-accelerated"
                        ),
                    }
                )
            elif gpu_util > gpu_saturated_pct:
                analysis["bottlenecks"].append(
                    {
                        "type": "gpu",
                        "severity": "medium",
                        "message": (
                            f"GPU utilization at {gpu_util}% - may be saturated"
                        ),
                    }
                )
            else:
                analysis["optimal_areas"].append(
                    {
                        "type": "gpu",
                        "message": (
                            f"GPU utilization at {gpu_util}% - good performance"
                        ),
                    }
                )

    def _analyze_performance_bottlenecks(self) -> Dict[str, Any]:
        """Analyze current performance bottlenecks (Issue #665: uses extracted helpers)."""
        analysis = {"bottlenecks": [], "optimal_areas": [], "warnings": []}

        try:
            # CPU Analysis (Issue #376 - use named constants)
            self._analyze_cpu_bottleneck(analysis)

            # Memory Analysis
            memory_info = self.system_info.get("memory", {})
            if memory_info.get("warning", False):
                analysis["bottlenecks"].append(
                    {
                        "type": "memory",
                        "severity": "high",
                        "message": (
                            f"Memory usage at {memory_info.get('used_percent', 0)}% "
                            f"- approaching limit"
                        ),
                    }
                )

            # GPU Analysis (Issue #376 - use named constants)
            self._analyze_gpu_bottleneck(analysis)

            return analysis

        except Exception as e:
            logger.error("Performance analysis error: %s", e)
            return {"error": str(e)}

    def _get_memory_recommendation(self) -> Optional[Dict[str, str]]:
        """
        Generate memory optimization recommendation if usage exceeds threshold.

        Returns recommendation dict if memory usage is high, None otherwise. Issue #620.
        """
        memory_info = self.system_info.get("memory", {})
        memory_warning_pct = ResourceThresholds.MEMORY_WARNING_THRESHOLD * 100
        if memory_info.get("used_percent", 0) > memory_warning_pct:
            return {
                "category": "memory",
                "priority": "high",
                "recommendation": (
                    "Consider implementing more aggressive memory "
                    "cleanup in chat history and conversation managers"
                ),
                "action": "Add memory limits and periodic cleanup routines",
            }
        return None

    def _get_gpu_recommendation(self) -> Optional[Dict[str, str]]:
        """
        Generate GPU optimization recommendation if utilization is low.

        Returns recommendation dict if GPU is underutilized, None otherwise. Issue #620.
        """
        gpu_info = self.system_info.get("gpu", {})
        gpu_util = gpu_info.get("utilization_percent")
        gpu_rec_pct = ResourceThresholds.GPU_RECOMMENDATION_THRESHOLD * 100
        if gpu_util is not None and gpu_util < gpu_rec_pct:
            return {
                "category": "gpu",
                "priority": "medium",
                "recommendation": (
                    "GPU underutilized - verify semantic chunking "
                    "and AI workloads are GPU-accelerated"
                ),
                "action": "Check CUDA availability and batch sizes in AI processing",
            }
        return None

    def _get_cpu_recommendation(self) -> Optional[Dict[str, str]]:
        """
        Generate CPU optimization recommendation for high-core systems.

        Returns recommendation dict if system has many cores, None otherwise. Issue #620.
        """
        cpu_cores = self.system_info.get("cpu", {}).get("logical_cores", 0)
        if cpu_cores > ResourceThresholds.HIGH_CORE_COUNT:
            return {
                "category": "cpu",
                "priority": "low",
                "recommendation": (
                    f"High-core system ({cpu_cores} cores) - ensure "
                    f"parallel processing is optimized"
                ),
                "action": "Verify thread pool sizes and async concurrency limits",
            }
        return None

    def _generate_performance_recommendations(self) -> List[Dict[str, str]]:
        """Generate performance optimization recommendations."""
        recommendations = []

        try:
            # Collect recommendations from each resource type (Issue #376)
            memory_rec = self._get_memory_recommendation()
            if memory_rec:
                recommendations.append(memory_rec)

            gpu_rec = self._get_gpu_recommendation()
            if gpu_rec:
                recommendations.append(gpu_rec)

            cpu_rec = self._get_cpu_recommendation()
            if cpu_rec:
                recommendations.append(cpu_rec)

            return recommendations

        except Exception as e:
            logger.error("Error generating recommendations: %s", e)
            return [{"category": "error", "recommendation": f"Error: {str(e)}"}]

    def cleanup_and_optimize_memory(self):
        """Force memory cleanup and optimization"""
        try:
            logger.info("Starting memory cleanup and optimization...")

            # Get memory before cleanup
            memory_before = psutil.virtual_memory()

            # Force garbage collection
            collected = gc.collect()

            # Get memory after cleanup
            memory_after = psutil.virtual_memory()

            memory_freed_mb = (memory_before.used - memory_after.used) / (1024 * 1024)

            logger.info(
                f"Memory cleanup completed: "
                f"Collected {collected} objects, "
                f"freed {memory_freed_mb:.2f}MB, "
                f"memory usage: {memory_before.percent:.1f}% → {memory_after.percent:.1f}%"
            )

            return {
                "objects_collected": collected,
                "memory_freed_mb": round(memory_freed_mb, 2),
                "memory_before_percent": round(memory_before.percent, 1),
                "memory_after_percent": round(memory_after.percent, 1),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Memory cleanup error: %s", e)
            return {"error": str(e)}


# Global instance with performance optimization
performance_diagnostics = PerformanceOptimizedDiagnostics()


# Legacy compatibility functions (with performance improvements)
async def request_user_permission(task_id: str, report: Dict[str, Any]) -> bool:
    """PERFORMANCE OPTIMIZED: Legacy wrapper with new timeout handling"""
    return await performance_diagnostics.request_user_permission_optimized(
        task_id, report
    )


def get_system_info() -> Dict[str, Any]:
    """Get system information with performance insights"""
    return performance_diagnostics.check_system_resources()


def force_memory_cleanup() -> Dict[str, Any]:
    """Force system-wide memory cleanup"""
    return performance_diagnostics.cleanup_and_optimize_memory()


# Additional performance monitoring functions
def get_performance_metrics() -> Dict[str, Any]:
    """Get current performance metrics"""
    return {
        "system_resources": performance_diagnostics.check_system_resources(),
        "memory_cleanup_available": True,
        "timeout_optimizations_active": True,
        "max_user_permission_timeout": (
            performance_diagnostics.max_user_permission_timeout
        ),
        "performance_mode": "optimized",
    }


if __name__ == "__main__":
    # Performance testing
    logger.info("AutoBot Performance-Optimized Diagnostics Test")
    logger.info("=" * 50)

    # Test system info gathering
    system_info = get_system_info()
    logger.info("System Info: {json.dumps(system_info, indent=2)}")

    # Test memory cleanup
    cleanup_result = force_memory_cleanup()
    logger.info("Memory Cleanup: {json.dumps(cleanup_result, indent=2)}")

    # Test performance metrics
    metrics = get_performance_metrics()
    logger.info("Performance Metrics: {json.dumps(metrics, indent=2)}")


# Backward compatibility aliases
Diagnostics = PerformanceOptimizedDiagnostics
performance_diagnostics = PerformanceOptimizedDiagnostics()
