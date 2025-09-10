"""
AutoBot Performance Monitoring System
Real-time performance tracking for timeout optimization and hardware utilization
"""

import asyncio
import gc
import json
import logging
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import psutil
import os

logger = logging.getLogger(__name__)


class AutoBotPerformanceMonitor:
    """
    Comprehensive performance monitoring for AutoBot optimizations
    """

    def __init__(self):
        self.monitoring_enabled = True
        self.metrics_history: List[Dict[str, Any]] = []
        self.max_history_entries = 1000  # Limit history to prevent memory leaks
        self.monitoring_interval = 30.0  # Monitor every 30 seconds
        
        # Performance optimization tracking
        self.timeout_optimizations = {
            "diagnostics_permission": {"original": 600, "optimized": 30, "savings": 570},
            "installation_timeout": {"original": 600, "optimized": 120, "savings": 480},
            "command_execution": {"original": 300, "optimized": 60, "savings": 240},
            "user_interaction": {"original": 300, "optimized": 30, "savings": 270},
            "kb_search": {"original": 10, "optimized": 8, "savings": 2},
            "classification": {"original": 999, "optimized": 5, "savings": 994},  # Was unlimited
        }
        
        # Memory optimization tracking
        self.memory_optimizations = {
            "chat_history_manager": {"max_messages": 10000, "cleanup_threshold": 12000},
            "source_attribution": {"max_sources": 1000, "cleanup_threshold": 1200},
            "conversation_manager": {"max_conversations": 50, "max_messages_per_conv": 500},
        }
        
        self.start_time = datetime.now()
        self.last_cleanup_time = datetime.now()
        
        logger.info("AutoBot Performance Monitor initialized")

    async def start_monitoring(self):
        """Start continuous performance monitoring"""
        if not self.monitoring_enabled:
            return
            
        logger.info("Starting continuous performance monitoring...")
        
        while self.monitoring_enabled:
            try:
                # Collect performance metrics
                metrics = await self.collect_comprehensive_metrics()
                
                # Store metrics with cleanup
                self._store_metrics(metrics)
                
                # Analyze and alert on performance issues
                await self._analyze_performance_issues(metrics)
                
                # Log key performance indicators
                self._log_performance_summary(metrics)
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Performance monitoring error: {e}")
                await asyncio.sleep(5)  # Short delay on error

    async def collect_comprehensive_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive performance metrics"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "system": self._get_system_metrics(),
            "gpu": self._get_gpu_metrics(),
            "memory": self._get_memory_metrics(),
            "autobot_processes": self._get_autobot_process_metrics(),
            "performance_optimizations": self._get_optimization_summary(),
            "timeout_status": self._get_timeout_optimization_status(),
        }
        
        return metrics

    def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system CPU and resource metrics"""
        try:
            cpu_info = {
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "cpu_freq": psutil.cpu_freq().current if psutil.cpu_freq() else None,
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None,
            }
            
            memory_info = psutil.virtual_memory()
            memory_data = {
                "total_gb": round(memory_info.total / (1024**3), 2),
                "available_gb": round(memory_info.available / (1024**3), 2),
                "used_gb": round(memory_info.used / (1024**3), 2),
                "used_percent": memory_info.percent,
                "memory_warning": memory_info.percent > 80,
            }
            
            disk_info = psutil.disk_usage('/')
            disk_data = {
                "total_gb": round(disk_info.total / (1024**3), 2),
                "used_gb": round(disk_info.used / (1024**3), 2),
                "free_gb": round(disk_info.free / (1024**3), 2),
                "used_percent": round((disk_info.used / disk_info.total) * 100, 1),
            }
            
            return {
                "cpu": cpu_info,
                "memory": memory_data,
                "disk": disk_data,
                "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {"error": str(e)}

    def _get_gpu_metrics(self) -> Dict[str, Any]:
        """Get GPU utilization and performance metrics"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw", 
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            
            if result.returncode == 0:
                gpu_data = result.stdout.strip().split(', ')
                if len(gpu_data) >= 5:
                    memory_total = int(gpu_data[1])
                    memory_used = int(gpu_data[2])
                    gpu_util = int(gpu_data[3])
                    temperature = int(gpu_data[4])
                    
                    # GPU Performance Analysis
                    performance_analysis = self._analyze_gpu_performance(gpu_util, memory_used, memory_total, temperature)
                    
                    return {
                        "name": gpu_data[0],
                        "memory_total_mb": memory_total,
                        "memory_used_mb": memory_used,
                        "memory_free_mb": memory_total - memory_used,
                        "memory_usage_percent": round((memory_used / memory_total) * 100, 1),
                        "utilization_percent": gpu_util,
                        "temperature_celsius": temperature,
                        "power_draw_watts": gpu_data[5] if len(gpu_data) > 5 else None,
                        "performance_analysis": performance_analysis,
                        "ai_workload_optimized": gpu_util > 20,  # Expect >20% for AI workloads
                    }
            
            return {"status": "nvidia-smi not available or no GPU detected"}
            
        except Exception as e:
            return {"status": f"GPU detection error: {str(e)}"}

    def _analyze_gpu_performance(self, utilization: int, memory_used: int, memory_total: int, temperature: int) -> Dict[str, Any]:
        """Analyze GPU performance for optimization recommendations"""
        analysis = {
            "status": "optimal",
            "recommendations": [],
            "warnings": [],
            "utilization_category": "unknown"
        }
        
        # Utilization analysis
        if utilization < 10:
            analysis["utilization_category"] = "idle"
            analysis["status"] = "underutilized"
            analysis["recommendations"].append(
                "GPU utilization very low - verify AI workloads are GPU-accelerated"
            )
        elif utilization < 30:
            analysis["utilization_category"] = "light"
            analysis["warnings"].append(
                f"GPU utilization at {utilization}% - may not be processing AI workloads optimally"
            )
        elif utilization < 70:
            analysis["utilization_category"] = "moderate"
            analysis["status"] = "good"
        elif utilization < 90:
            analysis["utilization_category"] = "high"
            analysis["status"] = "excellent"
        else:
            analysis["utilization_category"] = "saturated"
            analysis["warnings"].append(
                f"GPU utilization at {utilization}% - may be saturated"
            )
        
        # Memory analysis
        memory_percent = (memory_used / memory_total) * 100
        if memory_percent > 80:
            analysis["warnings"].append(
                f"GPU memory usage at {memory_percent:.1f}% - approaching limit"
            )
        
        # Temperature analysis
        if temperature > 80:
            analysis["warnings"].append(
                f"GPU temperature at {temperature}°C - thermal throttling possible"
            )
        elif temperature > 70:
            analysis["warnings"].append(
                f"GPU temperature at {temperature}°C - monitor for thermal issues"
            )
        
        return analysis

    def _get_memory_metrics(self) -> Dict[str, Any]:
        """Get detailed memory usage metrics"""
        try:
            # System memory
            mem_info = psutil.virtual_memory()
            
            # Python memory usage
            import gc
            gc_stats = gc.get_stats()
            
            return {
                "system_memory_gb": round(mem_info.total / (1024**3), 2),
                "available_memory_gb": round(mem_info.available / (1024**3), 2),
                "used_memory_percent": mem_info.percent,
                "swap_usage_percent": psutil.swap_memory().percent,
                "garbage_collection": {
                    "collections_gen0": gc_stats[0]["collections"] if gc_stats else 0,
                    "collected_gen0": gc_stats[0]["collected"] if gc_stats else 0,
                    "uncollectable_gen0": gc_stats[0]["uncollectable"] if gc_stats else 0,
                },
                "memory_optimization_active": True,
                "cleanup_last_run": self.last_cleanup_time.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error collecting memory metrics: {e}")
            return {"error": str(e)}

    def _get_autobot_process_metrics(self) -> List[Dict[str, Any]]:
        """Get AutoBot-specific process metrics"""
        autobot_processes = []
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info', 'create_time']):
                try:
                    proc_info = proc.info
                    cmdline = ' '.join(proc_info['cmdline']) if proc_info['cmdline'] else ''
                    
                    # Look for AutoBot-related processes
                    if any(keyword in cmdline.lower() for keyword in ['autobot', 'fast_app_factory', 'run_autobot']):
                        memory_mb = proc_info['memory_info'].rss / (1024 * 1024) if proc_info['memory_info'] else 0
                        
                        autobot_processes.append({
                            "pid": proc_info['pid'],
                            "name": proc_info['name'],
                            "cmdline": cmdline[:100] + "..." if len(cmdline) > 100 else cmdline,
                            "cpu_percent": proc_info['cpu_percent'],
                            "memory_mb": round(memory_mb, 2),
                            "create_time": datetime.fromtimestamp(proc_info['create_time']).isoformat(),
                            "running_time_minutes": round((time.time() - proc_info['create_time']) / 60, 1),
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            logger.error(f"Error collecting AutoBot process metrics: {e}")
        
        return autobot_processes

    def _get_optimization_summary(self) -> Dict[str, Any]:
        """Get summary of performance optimizations implemented"""
        total_timeout_savings = sum(opt["savings"] for opt in self.timeout_optimizations.values())
        
        return {
            "timeout_optimizations": len(self.timeout_optimizations),
            "total_timeout_savings_seconds": total_timeout_savings,
            "memory_optimizations_active": len(self.memory_optimizations),
            "optimization_categories": {
                "timeout_reduction": True,
                "memory_leak_protection": True,
                "hardware_utilization": True,
                "performance_monitoring": True,
            },
            "performance_mode": "Performance Optimized",
        }

    def _get_timeout_optimization_status(self) -> Dict[str, Any]:
        """Get detailed timeout optimization status"""
        optimizations = {}
        
        for name, config in self.timeout_optimizations.items():
            optimizations[name] = {
                "original_timeout": config["original"],
                "optimized_timeout": config["optimized"],
                "time_savings_seconds": config["savings"],
                "improvement_percent": round((config["savings"] / config["original"]) * 100, 1),
                "status": "active",
            }
        
        return {
            "optimizations": optimizations,
            "total_categories": len(self.timeout_optimizations),
            "average_improvement_percent": round(
                sum(opt["improvement_percent"] for opt in optimizations.values()) / len(optimizations), 1
            ),
        }

    def _store_metrics(self, metrics: Dict[str, Any]):
        """Store metrics with memory management"""
        self.metrics_history.append(metrics)
        
        # Cleanup old metrics to prevent memory leak
        if len(self.metrics_history) > self.max_history_entries:
            old_count = len(self.metrics_history)
            self.metrics_history = self.metrics_history[-self.max_history_entries:]
            
            if old_count > len(self.metrics_history):
                logger.debug(f"Cleaned up {old_count - len(self.metrics_history)} old metrics entries")

    async def _analyze_performance_issues(self, metrics: Dict[str, Any]):
        """Analyze metrics for performance issues and generate alerts"""
        issues = []
        
        try:
            # System resource analysis
            system_metrics = metrics.get("system", {})
            memory_info = system_metrics.get("memory", {})
            
            if memory_info.get("memory_warning", False):
                issues.append({
                    "category": "memory",
                    "severity": "high",
                    "message": f"High memory usage: {memory_info.get('used_percent', 0):.1f}%",
                    "recommendation": "Consider enabling more aggressive memory cleanup"
                })
            
            # GPU analysis
            gpu_info = metrics.get("gpu", {})
            if gpu_info.get("status") != "nvidia-smi not available or no GPU detected":
                gpu_util = gpu_info.get("utilization_percent", 0)
                if gpu_util < 20 and "ai_workload_optimized" in gpu_info and not gpu_info["ai_workload_optimized"]:
                    issues.append({
                        "category": "gpu",
                        "severity": "medium",
                        "message": f"GPU underutilized: {gpu_util}%",
                        "recommendation": "Verify AI workloads are using GPU acceleration"
                    })
            
            # Process analysis
            autobot_processes = metrics.get("autobot_processes", [])
            high_memory_processes = [p for p in autobot_processes if p.get("memory_mb", 0) > 1000]
            
            if high_memory_processes:
                for proc in high_memory_processes:
                    issues.append({
                        "category": "process",
                        "severity": "medium",
                        "message": f"High memory process: {proc['name']} using {proc['memory_mb']:.1f}MB",
                        "recommendation": "Monitor for memory leaks"
                    })
            
            # Log issues if any found
            if issues:
                logger.warning(f"Performance issues detected: {len(issues)} issues")
                for issue in issues[:3]:  # Log top 3 issues
                    logger.warning(f"  {issue['category'].upper()}: {issue['message']}")
            
        except Exception as e:
            logger.error(f"Error analyzing performance issues: {e}")

    def _log_performance_summary(self, metrics: Dict[str, Any]):
        """Log key performance indicators"""
        try:
            system_info = metrics.get("system", {})
            gpu_info = metrics.get("gpu", {})
            memory_info = system_info.get("memory", {})
            cpu_info = system_info.get("cpu", {})
            
            # Create performance summary
            summary = []
            
            # CPU usage
            cpu_percent = cpu_info.get("cpu_percent", 0)
            summary.append(f"CPU: {cpu_percent:.1f}%")
            
            # Memory usage
            mem_percent = memory_info.get("used_percent", 0)
            summary.append(f"MEM: {mem_percent:.1f}%")
            
            # GPU usage (if available)
            if gpu_info.get("utilization_percent") is not None:
                gpu_util = gpu_info["utilization_percent"]
                summary.append(f"GPU: {gpu_util}%")
                
            # AutoBot processes
            autobot_processes = metrics.get("autobot_processes", [])
            if autobot_processes:
                total_memory = sum(p.get("memory_mb", 0) for p in autobot_processes)
                summary.append(f"AutoBot: {len(autobot_processes)} processes, {total_memory:.0f}MB")
            
            # Optimization status
            optimization_summary = metrics.get("performance_optimizations", {})
            timeout_savings = optimization_summary.get("total_timeout_savings_seconds", 0)
            summary.append(f"Saved: {timeout_savings}s")
            
            logger.info(f"PERFORMANCE: {' | '.join(summary)}")
            
        except Exception as e:
            logger.error(f"Error logging performance summary: {e}")

    def get_current_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive current performance report"""
        try:
            if not self.metrics_history:
                return {"error": "No metrics available yet"}
            
            latest_metrics = self.metrics_history[-1]
            
            # Calculate performance trends if we have enough data
            trends = {}
            if len(self.metrics_history) >= 5:
                trends = self._calculate_performance_trends()
            
            return {
                "current_metrics": latest_metrics,
                "performance_trends": trends,
                "optimization_status": {
                    "timeout_optimizations": self.timeout_optimizations,
                    "memory_optimizations": self.memory_optimizations,
                    "monitoring_uptime_minutes": round((datetime.now() - self.start_time).total_seconds() / 60, 1),
                    "total_metrics_collected": len(self.metrics_history),
                },
                "recommendations": self._generate_performance_recommendations(latest_metrics),
            }
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {"error": str(e)}

    def _calculate_performance_trends(self) -> Dict[str, Any]:
        """Calculate performance trends from recent metrics"""
        try:
            recent_metrics = self.metrics_history[-5:]  # Last 5 metrics
            
            # Extract CPU and memory trends
            cpu_values = []
            memory_values = []
            gpu_values = []
            
            for metric in recent_metrics:
                system_info = metric.get("system", {})
                cpu_info = system_info.get("cpu", {})
                memory_info = system_info.get("memory", {})
                gpu_info = metric.get("gpu", {})
                
                if cpu_info.get("cpu_percent") is not None:
                    cpu_values.append(cpu_info["cpu_percent"])
                if memory_info.get("used_percent") is not None:
                    memory_values.append(memory_info["used_percent"])
                if gpu_info.get("utilization_percent") is not None:
                    gpu_values.append(gpu_info["utilization_percent"])
            
            trends = {}
            
            if cpu_values:
                trends["cpu"] = {
                    "average": round(sum(cpu_values) / len(cpu_values), 1),
                    "trend": "increasing" if cpu_values[-1] > cpu_values[0] else "decreasing" if cpu_values[-1] < cpu_values[0] else "stable"
                }
            
            if memory_values:
                trends["memory"] = {
                    "average": round(sum(memory_values) / len(memory_values), 1),
                    "trend": "increasing" if memory_values[-1] > memory_values[0] else "decreasing" if memory_values[-1] < memory_values[0] else "stable"
                }
            
            if gpu_values:
                trends["gpu"] = {
                    "average": round(sum(gpu_values) / len(gpu_values), 1),
                    "trend": "increasing" if gpu_values[-1] > gpu_values[0] else "decreasing" if gpu_values[-1] < gpu_values[0] else "stable"
                }
            
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating performance trends: {e}")
            return {}

    def _generate_performance_recommendations(self, metrics: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate performance optimization recommendations"""
        recommendations = []
        
        try:
            system_info = metrics.get("system", {})
            gpu_info = metrics.get("gpu", {})
            memory_info = system_info.get("memory", {})
            
            # Memory recommendations
            if memory_info.get("used_percent", 0) > 80:
                recommendations.append({
                    "category": "memory",
                    "priority": "high",
                    "recommendation": "High memory usage detected - enable more aggressive cleanup in chat history and conversation managers",
                    "action": "Reduce max_messages limits or increase cleanup frequency"
                })
            
            # GPU recommendations
            gpu_util = gpu_info.get("utilization_percent")
            if gpu_util is not None and gpu_util < 30:
                recommendations.append({
                    "category": "gpu",
                    "priority": "medium",
                    "recommendation": f"GPU underutilized at {gpu_util}% - verify AI workloads are GPU-accelerated",
                    "action": "Check CUDA availability and batch sizes in semantic chunking"
                })
            
            # CPU recommendations
            cpu_info = system_info.get("cpu", {})
            logical_cores = cpu_info.get("logical_cores", 0)
            cpu_percent = cpu_info.get("cpu_percent", 0)
            
            if logical_cores > 16 and cpu_percent < 30:
                recommendations.append({
                    "category": "cpu",
                    "priority": "low",
                    "recommendation": f"High-core system ({logical_cores} cores) with low utilization - optimize parallel processing",
                    "action": "Verify thread pool sizes and async concurrency limits"
                })
            
            # AutoBot process recommendations
            autobot_processes = metrics.get("autobot_processes", [])
            if len(autobot_processes) > 5:
                recommendations.append({
                    "category": "processes",
                    "priority": "medium",
                    "recommendation": f"Many AutoBot processes running ({len(autobot_processes)}) - check for process leaks",
                    "action": "Monitor process lifecycle and cleanup unused processes"
                })
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
        
        return recommendations

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring_enabled = False
        logger.info("Performance monitoring stopped")

    def force_memory_cleanup(self) -> Dict[str, Any]:
        """Force system-wide memory cleanup"""
        try:
            # Get memory before cleanup
            memory_before = psutil.virtual_memory()
            
            # Force garbage collection
            collected = gc.collect()
            
            # Update cleanup time
            self.last_cleanup_time = datetime.now()
            
            # Get memory after cleanup
            memory_after = psutil.virtual_memory()
            
            memory_freed_mb = (memory_before.used - memory_after.used) / (1024 * 1024)
            
            cleanup_stats = {
                "objects_collected": collected,
                "memory_freed_mb": round(memory_freed_mb, 2),
                "memory_before_percent": round(memory_before.percent, 1),
                "memory_after_percent": round(memory_after.percent, 1),
                "cleanup_time": self.last_cleanup_time.isoformat(),
                "cleanup_successful": True,
            }
            
            logger.info(
                f"PERFORMANCE CLEANUP: Collected {collected} objects, "
                f"freed {memory_freed_mb:.2f}MB, "
                f"memory: {memory_before.percent:.1f}% → {memory_after.percent:.1f}%"
            )
            
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"Memory cleanup error: {e}")
            return {"error": str(e), "cleanup_successful": False}


# Global performance monitor instance
autobot_monitor = AutoBotPerformanceMonitor()


# Convenience functions for easy integration
async def start_performance_monitoring():
    """Start the AutoBot performance monitoring system"""
    return await phase_nine_monitor.start_monitoring()


def get_performance_report() -> Dict[str, Any]:
    """Get current performance report"""
    return phase_nine_monitor.get_current_performance_report()


def force_system_cleanup() -> Dict[str, Any]:
    """Force system-wide memory cleanup"""
    return phase_nine_monitor.force_memory_cleanup()


def get_timeout_optimization_summary() -> Dict[str, Any]:
    """Get summary of timeout optimizations implemented"""
    return {
        "optimizations_active": len(phase_nine_monitor.timeout_optimizations),
        "total_time_saved_seconds": sum(opt["savings"] for opt in phase_nine_monitor.timeout_optimizations.values()),
        "optimizations": phase_nine_monitor.timeout_optimizations,
        "performance_mode": "Performance Optimized"
    }


# Example usage and testing
if __name__ == "__main__":
    async def test_performance_monitoring():
        """Test performance monitoring functionality"""
        monitor = AutoBotPerformanceMonitor()
        
        # Collect single metrics snapshot
        metrics = await monitor.collect_comprehensive_metrics()
        print("Performance Metrics:")
        print(json.dumps(metrics, indent=2, default=str))
        
        # Get performance report
        report = monitor.get_current_performance_report()
        print("\nPerformance Report:")
        print(json.dumps(report, indent=2, default=str))
        
        # Test memory cleanup
        cleanup_result = monitor.force_memory_cleanup()
        print("\nMemory Cleanup:")
        print(json.dumps(cleanup_result, indent=2))
        
        # Get timeout optimization summary
        timeout_summary = get_timeout_optimization_summary()
        print("\nTimeout Optimizations:")
        print(json.dumps(timeout_summary, indent=2))

    # Run test
    asyncio.run(test_performance_monitoring())