# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Diagnostic System for AutoBot with Performance Optimization
Provides system health monitoring, error reporting, and recovery suggestions
"""

import asyncio
import gc
import json
import logging
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

from src.constants.network_constants import NetworkConstants

try:
    from src.event_manager import event_manager
    from src.unified_config_manager import config as global_config_manager
    from src.utils.redis_client import get_redis_client
except ImportError as e:
    logging.warning(f"Import error in diagnostics: {e}")

logger = logging.getLogger(__name__)


class PerformanceOptimizedDiagnostics:
    """
    Enhanced diagnostics with performance monitoring and timeout optimization
    """

    def __init__(self):
        # Performance monitoring settings
        self.max_user_permission_timeout = 30.0  # Reduced from 600s to 30s
        self.permission_retry_attempts = 2
        self.memory_warning_threshold = 0.8  # 80% memory usage warning

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
            logger.error(f"Diagnostics: Redis initialization error: {e}")
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
            logger.error(f"Error gathering system info: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Get GPU information for performance monitoring"""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,  # Short timeout for GPU query
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

    async def request_user_permission_optimized(
        self, task_id: str, report: Dict[str, Any]
    ) -> bool:
        """
        PERFORMANCE OPTIMIZED: Request user permission with intelligent timeout handling

        CHANGES FROM ORIGINAL:
        - Reduced timeout from 600s (10 minutes) to 30s
        - Added retry mechanism for better user experience
        - Implemented automatic fallback with user notification
        - Added performance logging
        """
        start_time = time.time()

        for attempt in range(self.permission_retry_attempts):
            try:
                logger.info(
                    f"Requesting user permission for task {task_id} (attempt {attempt + 1})"
                )

                # Create permission future
                permission_future = asyncio.Future()

                # Publish permission request
                await event_manager.publish(
                    "user_permission_request",
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

                print(
                    f"Permission request sent for task {task_id} (attempt {attempt + 1}/{self.permission_retry_attempts})"
                )
                print(
                    f"Waiting up to {self.max_user_permission_timeout}s for response..."
                )

                try:
                    # PERFORMANCE FIX: Reduced from 600s to 30s
                    permission_granted = await asyncio.wait_for(
                        permission_future, timeout=self.max_user_permission_timeout
                    )

                    elapsed_time = time.time() - start_time
                    logger.info(
                        f"User permission received in {elapsed_time:.2f}s: {permission_granted}"
                    )
                    return permission_granted

                except asyncio.TimeoutError:
                    elapsed_time = time.time() - start_time
                    logger.warning(
                        f"User permission timeout after {elapsed_time:.2f}s (attempt {attempt + 1})"
                    )

                    if attempt < self.permission_retry_attempts - 1:
                        # Retry with notification
                        await event_manager.publish(
                            "log_message",
                            {
                                "level": "WARNING",
                                "message": (
                                    f"Permission request timeout (attempt {attempt + 1}). "
                                    f"Retrying... ({self.permission_retry_attempts - attempt - 1} attempts remaining)"
                                ),
                            },
                        )
                        await asyncio.sleep(2)  # Short delay before retry
                    else:
                        # Final timeout - use safe fallback
                        await self._handle_permission_timeout_fallback(
                            task_id, elapsed_time
                        )
                        return False

            except Exception as e:
                logger.error(
                    f"Error in permission request (attempt {attempt + 1}): {e}"
                )
                if attempt == self.permission_retry_attempts - 1:
                    return False
                await asyncio.sleep(1)

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
            logger.error(f"Error checking system resources: {e}")
            return {"error": str(e)}

    def _analyze_performance_bottlenecks(self) -> Dict[str, Any]:
        """Analyze current performance bottlenecks"""
        analysis = {"bottlenecks": [], "optimal_areas": [], "warnings": []}

        try:
            # CPU Analysis
            cpu_usage = self.system_info.get("cpu", {}).get("usage_percent", 0)
            if cpu_usage > 90:
                analysis["bottlenecks"].append(
                    {
                        "type": "cpu",
                        "severity": "high",
                        "message": f"CPU usage at {cpu_usage}% - potential bottleneck",
                    }
                )
            elif cpu_usage < 20:
                analysis["optimal_areas"].append(
                    {
                        "type": "cpu",
                        "message": f"CPU usage low at {cpu_usage}% - good performance headroom",
                    }
                )

            # Memory Analysis
            memory_info = self.system_info.get("memory", {})
            if memory_info.get("warning", False):
                analysis["bottlenecks"].append(
                    {
                        "type": "memory",
                        "severity": "high",
                        "message": f"Memory usage at {memory_info.get('used_percent', 0)}% - approaching limit",
                    }
                )

            # GPU Analysis
            gpu_info = self.system_info.get("gpu", {})
            gpu_util = gpu_info.get("utilization_percent")
            if gpu_util is not None:
                if gpu_util < 20:
                    analysis["warnings"].append(
                        {
                            "type": "gpu",
                            "severity": "medium",
                            "message": f"GPU utilization low at {gpu_util}% - AI workloads may not be GPU-accelerated",
                        }
                    )
                elif gpu_util > 95:
                    analysis["bottlenecks"].append(
                        {
                            "type": "gpu",
                            "severity": "medium",
                            "message": f"GPU utilization at {gpu_util}% - may be saturated",
                        }
                    )
                else:
                    analysis["optimal_areas"].append(
                        {
                            "type": "gpu",
                            "message": f"GPU utilization at {gpu_util}% - good performance",
                        }
                    )

            return analysis

        except Exception as e:
            logger.error(f"Performance analysis error: {e}")
            return {"error": str(e)}

    def _generate_performance_recommendations(self) -> List[Dict[str, str]]:
        """Generate performance optimization recommendations"""
        recommendations = []

        try:
            # Memory recommendations
            memory_info = self.system_info.get("memory", {})
            if memory_info.get("used_percent", 0) > 80:
                recommendations.append(
                    {
                        "category": "memory",
                        "priority": "high",
                        "recommendation": "Consider implementing more aggressive memory cleanup in chat history and conversation managers",
                        "action": "Add memory limits and periodic cleanup routines",
                    }
                )

            # GPU recommendations
            gpu_info = self.system_info.get("gpu", {})
            gpu_util = gpu_info.get("utilization_percent")
            if gpu_util is not None and gpu_util < 30:
                recommendations.append(
                    {
                        "category": "gpu",
                        "priority": "medium",
                        "recommendation": "GPU underutilized - verify semantic chunking and AI workloads are GPU-accelerated",
                        "action": "Check CUDA availability and batch sizes in AI processing",
                    }
                )

            # CPU recommendations
            cpu_cores = self.system_info.get("cpu", {}).get("logical_cores", 0)
            if cpu_cores > 16:
                recommendations.append(
                    {
                        "category": "cpu",
                        "priority": "low",
                        "recommendation": f"High-core system ({cpu_cores} cores) - ensure parallel processing is optimized",
                        "action": "Verify thread pool sizes and async concurrency limits",
                    }
                )

            return recommendations

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
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
            logger.error(f"Memory cleanup error: {e}")
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
        "max_user_permission_timeout": performance_diagnostics.max_user_permission_timeout,
        "performance_mode": "optimized",
    }


if __name__ == "__main__":
    # Performance testing
    print("AutoBot Performance-Optimized Diagnostics Test")
    print("=" * 50)

    # Test system info gathering
    system_info = get_system_info()
    print(f"System Info: {json.dumps(system_info, indent=2)}")

    # Test memory cleanup
    cleanup_result = force_memory_cleanup()
    print(f"Memory Cleanup: {json.dumps(cleanup_result, indent=2)}")

    # Test performance metrics
    metrics = get_performance_metrics()
    print(f"Performance Metrics: {json.dumps(metrics, indent=2)}")


# Backward compatibility aliases
Diagnostics = PerformanceOptimizedDiagnostics
performance_diagnostics = PerformanceOptimizedDiagnostics()
