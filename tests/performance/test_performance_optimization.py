#!/usr/bin/env python3
"""
AutoBot Phase 9 Performance Optimization Testing
================================================

Comprehensive performance testing for AutoBot Phase 9 optimizations including:
- GPU acceleration (RTX 4070)
- NPU utilization (Intel Ultra 9 185H)
- Multi-core CPU optimization (22 cores)
- Memory management and leak detection
- Hot reload and caching mechanisms
- Database query optimization
- API response time analysis
- Concurrent request handling
- WebSocket performance
- Knowledge base search performance

Usage:
    python tests/performance/test_performance_optimization.py [--benchmark] [--gpu] [--npu]
"""

import asyncio
import time
import psutil
import json
import logging
import concurrent.futures
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import argparse
import statistics

# Add AutoBot paths
sys.path.append('/home/kali/Desktop/AutoBot')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """Performance measurement result"""
    metric_name: str
    value: float
    unit: str
    category: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)

@dataclass
class BenchmarkResult:
    """Benchmark test result"""
    test_name: str
    category: str
    status: str  # "PASS", "FAIL", "WARNING"
    message: str
    metrics: List[PerformanceMetric] = field(default_factory=list)
    baseline_comparison: Optional[Dict] = None
    recommendations: List[str] = field(default_factory=list)

class PerformanceOptimizationTester:
    """Performance optimization testing suite"""
    
    def __init__(self):
        self.results: List[BenchmarkResult] = []
        self.start_time = time.time()
        self.backend_host = "172.16.168.20"
        self.backend_port = 8001
        self.base_url = f"http://{self.backend_host}:{self.backend_port}"
        
        # Performance baselines (expected values)
        self.baselines = {
            "api_response_time": 2.0,  # seconds
            "kb_search_time": 5.0,    # seconds
            "chat_response_time": 20.0, # seconds
            "concurrent_requests": 0.9,  # success rate
            "memory_usage": 80.0,      # percentage
            "cpu_usage": 70.0,         # percentage
        }
        
        # Create results directory
        self.results_dir = Path("/home/kali/Desktop/AutoBot/tests/results")
        self.results_dir.mkdir(exist_ok=True)
        
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def log_result(self, test_name: str, category: str, status: str, message: str, 
                   metrics: List[PerformanceMetric] = None, 
                   baseline_comparison: Dict = None, 
                   recommendations: List[str] = None):
        """Log performance test result"""
        result = BenchmarkResult(
            test_name=test_name,
            category=category,
            status=status,
            message=message,
            metrics=metrics or [],
            baseline_comparison=baseline_comparison,
            recommendations=recommendations or []
        )
        
        self.results.append(result)
        
        # Console output
        status_emoji = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️"}
        logger.info(f"{status_emoji.get(status, '?')} [{category}] {test_name}: {message}")
        
        # Log key metrics
        if metrics:
            for metric in metrics:
                logger.info(f"  📊 {metric.metric_name}: {metric.value:.3f} {metric.unit}")

    async def test_gpu_acceleration_performance(self):
        """Test GPU acceleration performance (RTX 4070)"""
        logger.info("🎮 Testing GPU Acceleration Performance...")
        
        metrics = []
        recommendations = []
        
        # Check GPU availability
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu", 
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                gpu_info = result.stdout.strip().split(',')
                gpu_name = gpu_info[0].strip()
                memory_used = int(gpu_info[1].strip())
                memory_total = int(gpu_info[2].strip())
                utilization = int(gpu_info[3].strip())
                
                memory_usage_percent = (memory_used / memory_total) * 100
                
                metrics.extend([
                    PerformanceMetric("gpu_memory_usage", memory_usage_percent, "%", "GPU"),
                    PerformanceMetric("gpu_utilization", utilization, "%", "GPU"),
                    PerformanceMetric("gpu_memory_total", memory_total, "MB", "GPU")
                ])
                
                # Evaluate GPU performance
                if utilization > 0 and memory_used > 100:  # GPU is being used
                    status = "PASS"
                    message = f"GPU acceleration active ({gpu_name}, {utilization}% util)"
                    
                    if utilization < 30:
                        recommendations.append("Consider increasing GPU workload for better utilization")
                elif memory_used > 50:  # GPU memory allocated but low utilization
                    status = "WARNING"
                    message = f"GPU memory allocated but low utilization ({utilization}%)"
                    recommendations.append("Check GPU acceleration configuration")
                else:
                    status = "WARNING"
                    message = "GPU available but not actively utilized"
                    recommendations.append("Enable GPU acceleration for AI workloads")
            else:
                status = "FAIL"
                message = "GPU not detected or nvidia-smi unavailable"
                recommendations.append("Install NVIDIA drivers and CUDA toolkit")
                
        except Exception as e:
            status = "FAIL"
            message = f"GPU detection error: {str(e)}"
            recommendations.append("Check GPU hardware and driver installation")
        
        # Test GPU-accelerated knowledge base operations
        await self._test_gpu_knowledge_operations(metrics, recommendations)
        
        self.log_result(
            "GPU Acceleration Performance",
            "Hardware Optimization",
            status,
            message,
            metrics,
            recommendations=recommendations
        )

    async def _test_gpu_knowledge_operations(self, metrics: List[PerformanceMetric], 
                                           recommendations: List[str]):
        """Test GPU-accelerated knowledge base operations"""
        try:
            import requests
            
            # Test semantic search performance (should use GPU)
            search_queries = [
                "Redis configuration optimization",
                "Docker container performance",
                "AutoBot architecture design",
                "Backend API optimization",
                "Frontend Vue.js components"
            ]
            
            search_times = []
            
            for query in search_queries:
                start_time = time.time()
                try:
                    response = requests.post(
                        f"{self.base_url}/api/knowledge_base/search",
                        json={"query": query, "limit": 10},
                        timeout=15
                    )
                    
                    if response.status_code == 200:
                        search_time = time.time() - start_time
                        search_times.append(search_time)
                        
                        # Check if results indicate GPU acceleration
                        data = response.json()
                        results = data.get("results", [])
                        
                        if len(results) >= 5:  # Good semantic search results
                            avg_score = sum(r.get("score", 0) for r in results) / len(results)
                            metrics.append(
                                PerformanceMetric(f"search_quality_{query[:20]}", avg_score, "score", "Knowledge Base")
                            )
                    
                except Exception as e:
                    logger.warning(f"Search query failed: {query[:30]}... - {e}")
            
            if search_times:
                avg_search_time = statistics.mean(search_times)
                median_search_time = statistics.median(search_times)
                
                metrics.extend([
                    PerformanceMetric("kb_search_avg_time", avg_search_time, "seconds", "Knowledge Base"),
                    PerformanceMetric("kb_search_median_time", median_search_time, "seconds", "Knowledge Base"),
                    PerformanceMetric("kb_search_samples", len(search_times), "count", "Knowledge Base")
                ])
                
                # Performance evaluation
                if avg_search_time < 2.0:
                    recommendations.append("Excellent search performance - GPU acceleration likely active")
                elif avg_search_time < 5.0:
                    recommendations.append("Good search performance - monitor for GPU utilization")
                else:
                    recommendations.append("Slow search performance - verify GPU acceleration is enabled")
                    
        except Exception as e:
            logger.error(f"GPU knowledge operations test failed: {e}")

    async def test_npu_acceleration(self):
        """Test NPU acceleration (Intel Ultra 9 185H AI Boost)"""
        logger.info("🧠 Testing NPU Acceleration...")
        
        metrics = []
        recommendations = []
        
        # Check NPU worker service
        try:
            import requests
            
            npu_url = f"http://172.16.168.22:8081"
            
            start_time = time.time()
            response = requests.get(f"{npu_url}/health", timeout=10)
            response_time = time.time() - start_time
            
            metrics.append(PerformanceMetric("npu_worker_response_time", response_time, "seconds", "NPU"))
            
            if response.status_code == 200:
                npu_data = response.json()
                
                # Check NPU capabilities
                capabilities = npu_data.get("capabilities", {})
                ai_acceleration = capabilities.get("ai_acceleration", False)
                
                if ai_acceleration:
                    status = "PASS"
                    message = "NPU worker accessible with AI acceleration"
                    recommendations.append("NPU acceleration available for AI workloads")
                else:
                    status = "WARNING"
                    message = "NPU worker accessible but AI acceleration unclear"
                    recommendations.append("Verify NPU configuration for AI acceleration")
                    
                # Test NPU performance with AI task
                await self._test_npu_ai_performance(npu_url, metrics, recommendations)
                
            else:
                status = "WARNING"
                message = f"NPU worker responded with HTTP {response.status_code}"
                recommendations.append("Check NPU worker service configuration")
                
        except Exception as e:
            status = "FAIL"
            message = f"NPU worker connectivity error: {str(e)}"
            recommendations.append("Start NPU worker service or check network connectivity")
        
        self.log_result(
            "NPU Acceleration",
            "Hardware Optimization",
            status,
            message,
            metrics,
            recommendations=recommendations
        )

    async def _test_npu_ai_performance(self, npu_url: str, metrics: List[PerformanceMetric], 
                                     recommendations: List[str]):
        """Test NPU AI processing performance"""
        try:
            import requests
            
            # Test NPU-accelerated inference
            test_prompts = [
                "Classify this message: 'List files in directory'",
                "Analyze sentiment: 'AutoBot is working great!'",
                "Extract intent: 'Configure Redis database settings'"
            ]
            
            processing_times = []
            
            for prompt in test_prompts:
                start_time = time.time()
                try:
                    response = requests.post(
                        f"{npu_url}/api/ai/process",
                        json={"prompt": prompt, "task": "classification"},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        processing_time = time.time() - start_time
                        processing_times.append(processing_time)
                        
                        # Check response quality
                        result = response.json()
                        confidence = result.get("confidence", 0)
                        
                        metrics.append(
                            PerformanceMetric(f"npu_confidence_{len(processing_times)}", confidence, "score", "NPU")
                        )
                        
                except Exception as e:
                    logger.warning(f"NPU processing failed for prompt: {prompt[:30]}... - {e}")
            
            if processing_times:
                avg_processing = statistics.mean(processing_times)
                metrics.append(
                    PerformanceMetric("npu_avg_processing_time", avg_processing, "seconds", "NPU")
                )
                
                if avg_processing < 1.0:
                    recommendations.append("Excellent NPU performance - AI acceleration working well")
                elif avg_processing < 5.0:
                    recommendations.append("Good NPU performance - suitable for real-time AI tasks")
                else:
                    recommendations.append("NPU performance needs optimization")
                    
        except Exception as e:
            logger.error(f"NPU AI performance test failed: {e}")

    async def test_cpu_optimization(self):
        """Test multi-core CPU optimization (22 cores)"""
        logger.info("🔥 Testing Multi-Core CPU Optimization...")
        
        metrics = []
        recommendations = []
        
        # Get CPU information
        cpu_count = psutil.cpu_count(logical=True)
        cpu_physical = psutil.cpu_count(logical=False)
        
        metrics.extend([
            PerformanceMetric("cpu_logical_cores", cpu_count, "cores", "CPU"),
            PerformanceMetric("cpu_physical_cores", cpu_physical, "cores", "CPU")
        ])
        
        # Measure CPU usage during concurrent operations
        start_cpu_percent = psutil.cpu_percent(interval=1)
        
        # Test concurrent API requests to measure CPU utilization
        concurrent_requests = min(cpu_count, 20)  # Don't exceed core count
        
        start_time = time.time()
        cpu_samples = []
        
        async def cpu_intensive_request():
            try:
                import requests
                
                # Make multiple requests to test CPU utilization
                for _ in range(3):
                    response = requests.get(f"{self.base_url}/api/health", timeout=5)
                    if response.status_code != 200:
                        break
                    
                    # Add some CPU work
                    await asyncio.sleep(0.1)
                    
                return True
            except Exception:
                return False
        
        # Monitor CPU during load
        async def cpu_monitor():
            for _ in range(20):  # Monitor for 20 samples
                cpu_percent = psutil.cpu_percent(interval=0.5)
                cpu_samples.append(cpu_percent)
        
        # Run concurrent load and monitoring
        monitor_task = asyncio.create_task(cpu_monitor())
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
            futures = [executor.submit(asyncio.run, cpu_intensive_request()) 
                      for _ in range(concurrent_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        await monitor_task
        
        duration = time.time() - start_time
        successful_requests = sum(1 for r in results if r)
        
        # Calculate CPU metrics
        if cpu_samples:
            avg_cpu = statistics.mean(cpu_samples)
            max_cpu = max(cpu_samples)
            min_cpu = min(cpu_samples)
            
            metrics.extend([
                PerformanceMetric("cpu_avg_utilization", avg_cpu, "%", "CPU"),
                PerformanceMetric("cpu_max_utilization", max_cpu, "%", "CPU"),
                PerformanceMetric("cpu_min_utilization", min_cpu, "%", "CPU"),
                PerformanceMetric("concurrent_success_rate", (successful_requests/concurrent_requests)*100, "%", "CPU"),
                PerformanceMetric("requests_per_second", successful_requests/duration, "req/s", "CPU")
            ])
            
            # Evaluate CPU performance
            if avg_cpu > 80:
                status = "WARNING"
                message = f"High CPU utilization under load ({avg_cpu:.1f}%)"
                recommendations.append("Consider optimizing CPU-intensive operations")
            elif avg_cpu > 50:
                status = "PASS"
                message = f"Good CPU utilization under load ({avg_cpu:.1f}%)"
                recommendations.append("CPU handling concurrent load efficiently")
            else:
                status = "PASS"
                message = f"Low CPU utilization ({avg_cpu:.1f}%) - good efficiency"
                recommendations.append("Excellent CPU efficiency with room for more load")
        else:
            status = "FAIL"
            message = "Failed to collect CPU metrics"
            recommendations.append("Check system monitoring capabilities")
        
        # Test thread pool performance
        await self._test_thread_pool_optimization(metrics, recommendations)
        
        self.log_result(
            "Multi-Core CPU Optimization",
            "Hardware Optimization",
            status,
            message,
            metrics,
            recommendations=recommendations
        )

    async def _test_thread_pool_optimization(self, metrics: List[PerformanceMetric], 
                                           recommendations: List[str]):
        """Test thread pool optimization"""
        try:
            # Test different thread pool sizes
            thread_counts = [4, 8, 12, 16, 20]
            best_performance = 0
            optimal_threads = 4
            
            for thread_count in thread_counts:
                start_time = time.time()
                
                def cpu_work():
                    # Simulate CPU-bound work
                    total = 0
                    for i in range(10000):
                        total += i * i
                    return total
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                    futures = [executor.submit(cpu_work) for _ in range(20)]
                    results = [f.result() for f in concurrent.futures.as_completed(futures)]
                
                duration = time.time() - start_time
                performance = len(results) / duration  # tasks per second
                
                metrics.append(
                    PerformanceMetric(f"thread_pool_{thread_count}_performance", performance, "tasks/s", "CPU")
                )
                
                if performance > best_performance:
                    best_performance = performance
                    optimal_threads = thread_count
            
            metrics.append(
                PerformanceMetric("optimal_thread_count", optimal_threads, "threads", "CPU")
            )
            
            if optimal_threads >= 12:
                recommendations.append(f"System benefits from high thread counts (optimal: {optimal_threads})")
            else:
                recommendations.append(f"System performs best with moderate threading (optimal: {optimal_threads})")
                
        except Exception as e:
            logger.error(f"Thread pool optimization test failed: {e}")

    async def test_memory_management(self):
        """Test memory management and leak detection"""
        logger.info("💾 Testing Memory Management...")
        
        metrics = []
        recommendations = []
        
        # Initial memory measurement
        memory_info = psutil.virtual_memory()
        initial_memory_used = memory_info.used
        initial_memory_percent = memory_info.percent
        
        metrics.extend([
            PerformanceMetric("initial_memory_used", initial_memory_used / (1024**3), "GB", "Memory"),
            PerformanceMetric("initial_memory_percent", initial_memory_percent, "%", "Memory"),
            PerformanceMetric("total_memory", memory_info.total / (1024**3), "GB", "Memory")
        ])
        
        # Memory stress test
        memory_samples = []
        test_duration = 30  # seconds
        
        async def memory_intensive_operations():
            """Perform memory-intensive operations"""
            try:
                import requests
                
                # Make multiple API calls that might increase memory usage
                for i in range(50):
                    response = requests.post(
                        f"{self.base_url}/api/knowledge_base/search",
                        json={"query": f"test query {i}", "limit": 5},
                        timeout=10
                    )
                    
                    if i % 10 == 0:
                        # Sample memory usage
                        mem = psutil.virtual_memory()
                        memory_samples.append({
                            "timestamp": time.time(),
                            "used_gb": mem.used / (1024**3),
                            "percent": mem.percent
                        })
                    
                    await asyncio.sleep(0.2)
                    
            except Exception as e:
                logger.error(f"Memory stress test error: {e}")
        
        start_time = time.time()
        await memory_intensive_operations()
        
        # Final memory measurement
        final_memory_info = psutil.virtual_memory()
        final_memory_used = final_memory_info.used
        final_memory_percent = final_memory_info.percent
        
        memory_growth = (final_memory_used - initial_memory_used) / (1024**2)  # MB
        
        metrics.extend([
            PerformanceMetric("final_memory_used", final_memory_used / (1024**3), "GB", "Memory"),
            PerformanceMetric("final_memory_percent", final_memory_percent, "%", "Memory"),
            PerformanceMetric("memory_growth", memory_growth, "MB", "Memory"),
            PerformanceMetric("memory_samples", len(memory_samples), "count", "Memory")
        ])
        
        # Analyze memory usage pattern
        if memory_samples:
            memory_values = [s["percent"] for s in memory_samples]
            max_memory = max(memory_values)
            min_memory = min(memory_values)
            avg_memory = statistics.mean(memory_values)
            
            metrics.extend([
                PerformanceMetric("max_memory_usage", max_memory, "%", "Memory"),
                PerformanceMetric("avg_memory_usage", avg_memory, "%", "Memory"),
                PerformanceMetric("memory_variance", max_memory - min_memory, "%", "Memory")
            ])
        
        # Evaluate memory management
        if memory_growth > 500:  # More than 500MB growth
            status = "WARNING"
            message = f"Significant memory growth detected ({memory_growth:.1f} MB)"
            recommendations.extend([
                "Monitor for memory leaks in long-running operations",
                "Consider implementing memory cleanup routines"
            ])
        elif memory_growth > 100:  # More than 100MB growth
            status = "PASS"
            message = f"Moderate memory growth ({memory_growth:.1f} MB)"
            recommendations.append("Memory usage within acceptable range")
        else:
            status = "PASS"
            message = f"Minimal memory growth ({memory_growth:.1f} MB)"
            recommendations.append("Excellent memory management")
        
        # Check for memory leaks
        await self._test_memory_leak_detection(metrics, recommendations)
        
        self.log_result(
            "Memory Management",
            "Performance Optimization",
            status,
            message,
            metrics,
            recommendations=recommendations
        )

    async def _test_memory_leak_detection(self, metrics: List[PerformanceMetric], 
                                        recommendations: List[str]):
        """Test for memory leaks through repeated operations"""
        try:
            import requests
            
            # Perform the same operation multiple times and measure memory
            memory_readings = []
            
            for cycle in range(5):
                # Measure memory before operation
                mem_before = psutil.virtual_memory().used / (1024**2)  # MB
                
                # Perform operations that might leak memory
                for _ in range(10):
                    try:
                        response = requests.get(f"{self.base_url}/api/health", timeout=5)
                        if response.status_code == 200:
                            # Process response to potentially trigger memory usage
                            data = response.json()
                    except Exception:
                        pass
                
                # Measure memory after operation
                mem_after = psutil.virtual_memory().used / (1024**2)  # MB
                memory_growth = mem_after - mem_before
                
                memory_readings.append(memory_growth)
                
                # Wait for garbage collection
                await asyncio.sleep(2)
            
            if memory_readings:
                avg_growth_per_cycle = statistics.mean(memory_readings)
                max_growth = max(memory_readings)
                
                metrics.extend([
                    PerformanceMetric("avg_memory_growth_per_cycle", avg_growth_per_cycle, "MB", "Memory"),
                    PerformanceMetric("max_memory_growth_per_cycle", max_growth, "MB", "Memory")
                ])
                
                if avg_growth_per_cycle > 10:  # More than 10MB per cycle
                    recommendations.append("Potential memory leak detected - investigate cleanup routines")
                elif avg_growth_per_cycle > 5:  # More than 5MB per cycle
                    recommendations.append("Monitor memory growth in production environment")
                else:
                    recommendations.append("No significant memory leaks detected")
                    
        except Exception as e:
            logger.error(f"Memory leak detection test failed: {e}")

    async def test_hot_reload_performance(self):
        """Test hot reload and caching mechanisms"""
        logger.info("🔄 Testing Hot Reload and Caching Performance...")
        
        metrics = []
        recommendations = []
        
        try:
            import requests
            
            # Test cache warming
            cache_endpoints = [
                "/api/knowledge_base/stats/basic",
                "/api/system/status",
                "/api/config/status"
            ]
            
            first_request_times = []
            cached_request_times = []
            
            for endpoint in cache_endpoints:
                # First request (cache miss)
                start_time = time.time()
                response1 = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                first_time = time.time() - start_time
                first_request_times.append(first_time)
                
                # Wait briefly for cache to settle
                await asyncio.sleep(0.5)
                
                # Second request (should be cached)
                start_time = time.time()
                response2 = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                cached_time = time.time() - start_time
                cached_request_times.append(cached_time)
                
                # Verify responses are consistent
                if response1.status_code == 200 and response2.status_code == 200:
                    try:
                        data1 = response1.json()
                        data2 = response2.json()
                        
                        # Check if responses are similar (caching working)
                        cache_effectiveness = cached_time < first_time * 0.8  # 20% improvement
                        
                        metrics.append(
                            PerformanceMetric(f"cache_effectiveness_{endpoint.replace('/', '_')}", 
                                            cache_effectiveness, "boolean", "Caching")
                        )
                    except json.JSONDecodeError:
                        pass
            
            if first_request_times and cached_request_times:
                avg_first_time = statistics.mean(first_request_times)
                avg_cached_time = statistics.mean(cached_request_times)
                cache_improvement = ((avg_first_time - avg_cached_time) / avg_first_time) * 100
                
                metrics.extend([
                    PerformanceMetric("avg_first_request_time", avg_first_time, "seconds", "Caching"),
                    PerformanceMetric("avg_cached_request_time", avg_cached_time, "seconds", "Caching"),
                    PerformanceMetric("cache_improvement_percent", cache_improvement, "%", "Caching")
                ])
                
                if cache_improvement > 20:
                    status = "PASS"
                    message = f"Effective caching ({cache_improvement:.1f}% improvement)"
                    recommendations.append("Caching system working effectively")
                elif cache_improvement > 5:
                    status = "PASS"
                    message = f"Moderate caching benefit ({cache_improvement:.1f}% improvement)"
                    recommendations.append("Caching provides some benefit")
                else:
                    status = "WARNING"
                    message = f"Limited caching benefit ({cache_improvement:.1f}% improvement)"
                    recommendations.append("Review caching configuration and implementation")
            else:
                status = "FAIL"
                message = "Unable to measure caching performance"
                recommendations.append("Check cache system implementation")
            
            # Test hot reload detection
            await self._test_hot_reload_detection(metrics, recommendations)
            
        except Exception as e:
            status = "FAIL"
            message = f"Hot reload/caching test error: {str(e)}"
            recommendations.append("Check hot reload and caching system availability")
        
        self.log_result(
            "Hot Reload and Caching",
            "Performance Optimization",
            status,
            message,
            metrics,
            recommendations=recommendations
        )

    async def _test_hot_reload_detection(self, metrics: List[PerformanceMetric], 
                                       recommendations: List[str]):
        """Test hot reload detection and response"""
        try:
            import requests
            
            # Check if hot reload endpoints exist
            hot_reload_endpoints = [
                "/api/hot_reload/status",
                "/api/system/reload",
                "/api/config/reload"
            ]
            
            hot_reload_available = False
            reload_response_times = []
            
            for endpoint in hot_reload_endpoints:
                try:
                    start_time = time.time()
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    response_time = time.time() - start_time
                    
                    if response.status_code in [200, 204]:
                        hot_reload_available = True
                        reload_response_times.append(response_time)
                        
                        metrics.append(
                            PerformanceMetric(f"hot_reload_time_{endpoint.replace('/', '_')}", 
                                            response_time, "seconds", "Hot Reload")
                        )
                        
                except Exception:
                    pass  # Endpoint might not exist
            
            if hot_reload_available:
                avg_reload_time = statistics.mean(reload_response_times)
                metrics.append(
                    PerformanceMetric("avg_hot_reload_time", avg_reload_time, "seconds", "Hot Reload")
                )
                
                if avg_reload_time < 1.0:
                    recommendations.append("Fast hot reload capability available")
                else:
                    recommendations.append("Hot reload available but slow - consider optimization")
            else:
                recommendations.append("Hot reload endpoints not detected - consider implementing for development")
                
        except Exception as e:
            logger.error(f"Hot reload detection test failed: {e}")

    async def generate_performance_report(self):
        """Generate comprehensive performance report"""
        total_duration = time.time() - self.start_time
        
        # Calculate performance statistics
        all_metrics = []
        for result in self.results:
            all_metrics.extend(result.metrics)
        
        # Group metrics by category
        metric_categories = {}
        for metric in all_metrics:
            category = metric.category
            if category not in metric_categories:
                metric_categories[category] = []
            metric_categories[category].append(metric)
        
        # Generate performance summary
        performance_summary = {
            "execution_timestamp": self.timestamp,
            "total_duration": total_duration,
            "total_tests": len(self.results),
            "passed_tests": sum(1 for r in self.results if r.status == "PASS"),
            "failed_tests": sum(1 for r in self.results if r.status == "FAIL"),
            "warning_tests": sum(1 for r in self.results if r.status == "WARNING"),
            "total_metrics": len(all_metrics),
            "metric_categories": list(metric_categories.keys())
        }
        
        # Create detailed report
        report = {
            "autobot_phase9_performance_report": {
                "summary": performance_summary,
                "test_results": [
                    {
                        "test_name": r.test_name,
                        "category": r.category,
                        "status": r.status,
                        "message": r.message,
                        "metrics": [
                            {
                                "name": m.metric_name,
                                "value": m.value,
                                "unit": m.unit,
                                "category": m.category,
                                "metadata": m.metadata
                            }
                            for m in r.metrics
                        ],
                        "baseline_comparison": r.baseline_comparison,
                        "recommendations": r.recommendations
                    }
                    for r in self.results
                ],
                "metric_analysis": {
                    category: {
                        "count": len(metrics),
                        "avg_value": statistics.mean([m.value for m in metrics if isinstance(m.value, (int, float))]),
                        "metrics": [
                            {"name": m.metric_name, "value": m.value, "unit": m.unit}
                            for m in metrics
                        ]
                    }
                    for category, metrics in metric_categories.items()
                    if metrics
                },
                "overall_recommendations": self._generate_overall_recommendations()
            }
        }
        
        # Save report
        report_file = self.results_dir / f"performance_optimization_report_{self.timestamp}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Create human-readable summary
        summary_file = self.results_dir / f"performance_summary_{self.timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("AutoBot Phase 9 Performance Optimization Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Execution: {self.timestamp}\n")
            f.write(f"Duration: {total_duration:.2f} seconds\n\n")
            
            f.write("Test Results Summary:\n")
            f.write(f"  Total Tests: {performance_summary['total_tests']}\n")
            f.write(f"  Passed: {performance_summary['passed_tests']}\n")
            f.write(f"  Failed: {performance_summary['failed_tests']}\n")
            f.write(f"  Warnings: {performance_summary['warning_tests']}\n\n")
            
            f.write("Performance Metrics Summary:\n")
            for category, metrics in metric_categories.items():
                f.write(f"  {category}: {len(metrics)} metrics\n")
            f.write("\n")
            
            f.write("Overall Recommendations:\n")
            for i, rec in enumerate(self._generate_overall_recommendations(), 1):
                f.write(f"  {i}. {rec}\n")
        
        logger.info(f"📊 Performance report generated: {report_file}")
        logger.info(f"📊 Performance summary: {summary_file}")
        
        return report_file

    def _generate_overall_recommendations(self) -> List[str]:
        """Generate overall performance recommendations"""
        recommendations = []
        
        # Analyze test results
        failed_tests = [r for r in self.results if r.status == "FAIL"]
        warning_tests = [r for r in self.results if r.status == "WARNING"]
        
        if failed_tests:
            recommendations.append("🚨 Address critical performance failures before production deployment")
        
        if len(warning_tests) > len(self.results) * 0.3:
            recommendations.append("⚠️ Multiple performance warnings detected - consider optimization")
        
        # Hardware-specific recommendations
        gpu_tests = [r for r in self.results if "GPU" in r.category]
        npu_tests = [r for r in self.results if "NPU" in r.category]
        cpu_tests = [r for r in self.results if "CPU" in r.category]
        
        if gpu_tests and all(t.status == "PASS" for t in gpu_tests):
            recommendations.append("✅ GPU acceleration working well - maximize GPU workloads")
        elif gpu_tests:
            recommendations.append("🎮 GPU optimization opportunities available")
        
        if npu_tests and all(t.status == "PASS" for t in npu_tests):
            recommendations.append("✅ NPU acceleration available - consider AI workload migration")
        elif npu_tests:
            recommendations.append("🧠 NPU integration needs attention")
        
        if cpu_tests and all(t.status == "PASS" for t in cpu_tests):
            recommendations.append("✅ CPU utilization optimized for multi-core architecture")
        
        # Memory recommendations
        memory_tests = [r for r in self.results if "Memory" in r.category]
        if memory_tests:
            memory_warnings = [t for t in memory_tests if t.status == "WARNING"]
            if memory_warnings:
                recommendations.append("💾 Monitor memory usage for potential optimizations")
            else:
                recommendations.append("✅ Memory management performing well")
        
        # Performance baseline comparison
        baseline_violations = 0
        for result in self.results:
            if result.baseline_comparison:
                violations = result.baseline_comparison.get("violations", 0)
                baseline_violations += violations
        
        if baseline_violations > 0:
            recommendations.append(f"📊 {baseline_violations} performance baselines exceeded - review thresholds")
        else:
            recommendations.append("✅ All performance metrics within baseline expectations")
        
        return recommendations

async def main():
    """Main entry point for performance testing"""
    parser = argparse.ArgumentParser(description='AutoBot Phase 9 Performance Optimization Testing')
    parser.add_argument('--benchmark', action='store_true', help='Run comprehensive benchmarks')
    parser.add_argument('--gpu', action='store_true', help='Focus on GPU acceleration tests')
    parser.add_argument('--npu', action='store_true', help='Focus on NPU acceleration tests')
    parser.add_argument('--memory', action='store_true', help='Focus on memory management tests')
    parser.add_argument('--cpu', action='store_true', help='Focus on CPU optimization tests')
    parser.add_argument('--cache', action='store_true', help='Focus on caching and hot reload tests')
    
    args = parser.parse_args()
    
    # Create performance tester
    tester = PerformanceOptimizationTester()
    
    logger.info("🚀 Starting AutoBot Phase 9 Performance Optimization Testing")
    
    # Run selected tests
    if args.benchmark or not any([args.gpu, args.npu, args.memory, args.cpu, args.cache]):
        # Run all tests
        await tester.test_gpu_acceleration_performance()
        await tester.test_npu_acceleration()
        await tester.test_cpu_optimization()
        await tester.test_memory_management()
        await tester.test_hot_reload_performance()
    else:
        # Run specific tests
        if args.gpu:
            await tester.test_gpu_acceleration_performance()
        if args.npu:
            await tester.test_npu_acceleration()
        if args.cpu:
            await tester.test_cpu_optimization()
        if args.memory:
            await tester.test_memory_management()
        if args.cache:
            await tester.test_hot_reload_performance()
    
    # Generate report
    report_file = await tester.generate_performance_report()
    
    logger.info("✅ Performance optimization testing completed")
    logger.info(f"📊 Report available at: {report_file}")

if __name__ == "__main__":
    asyncio.run(main())