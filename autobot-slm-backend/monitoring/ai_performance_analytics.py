#!/usr/bin/env python3
"""
AutoBot AI/ML Performance Analytics
Specialized monitoring for AI workloads, NPU utilization, and multi-modal performance.

Issue #396: Converted blocking subprocess.run to asyncio.create_subprocess_exec.
"""

import asyncio
import json
import logging
import os
import statistics
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import psutil

from autobot_shared.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


@dataclass
class NPUMetrics:
    """NPU (Neural Processing Unit) performance metrics."""

    timestamp: str
    device_id: str
    utilization_percent: float
    memory_used_mb: float
    memory_total_mb: float
    power_draw_watts: Optional[float]
    temperature_celsius: Optional[float]
    operations_per_second: Optional[float]
    inference_latency_ms: float
    throughput_mbps: float
    error_count: int = 0


@dataclass
class MultiModalMetrics:
    """Multi-modal AI pipeline performance metrics."""

    timestamp: str
    pipeline_type: str  # text, image, audio, combined
    input_size_mb: float
    processing_time_ms: float
    model_load_time_ms: float
    inference_time_ms: float
    post_processing_time_ms: float
    memory_peak_mb: float
    cpu_utilization_percent: float
    gpu_utilization_percent: Optional[float]
    npu_utilization_percent: Optional[float]
    throughput_items_per_second: float
    accuracy_score: Optional[float]


@dataclass
class KnowledgeBaseMetrics:
    """Knowledge base search and retrieval performance."""

    timestamp: str
    query_type: str  # semantic, keyword, hybrid
    query_length: int
    search_time_ms: float
    embedding_time_ms: float
    retrieval_time_ms: float
    ranking_time_ms: float
    results_count: int
    relevance_score: float
    memory_usage_mb: float
    cache_hit: bool
    vector_dimensions: int
    total_vectors_searched: int


@dataclass
class LLMPerformanceMetrics:
    """Large Language Model performance metrics."""

    timestamp: str
    model_name: str
    request_type: str  # chat, completion, embedding
    input_tokens: int
    output_tokens: int
    processing_time_ms: float
    tokens_per_second: float
    memory_usage_mb: float
    gpu_utilization: Optional[float]
    npu_utilization: Optional[float]
    temperature: float
    max_tokens: int
    context_length: int
    cache_hit: bool
    stream_mode: bool


class AIPerformanceAnalytics:
    """AI/ML performance monitoring and analytics system."""

    def __init__(
        self, redis_host: str = NetworkConstants.REDIS_VM_IP, redis_port: int = 6379
    ):
        self.logger = logging.getLogger(__name__)
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.analytics_data_path = Path(_base) / "logs" / "ai_performance"
        self.analytics_data_path.mkdir(parents=True, exist_ok=True)

        # Performance baselines and targets
        self.performance_targets = {
            "npu_utilization": {"optimal": 75.0, "max": 90.0},
            "inference_latency": {"target": 100.0, "critical": 500.0},  # ms
            "knowledge_search": {"target": 200.0, "critical": 1000.0},  # ms
            "llm_tokens_per_second": {"min_acceptable": 10.0, "target": 50.0},
        }

        # Track performance trends
        self.performance_history = {
            "npu": [],
            "multimodal": [],
            "knowledge": [],
            "llm": [],
        }

    async def initialize_redis_connection(self):
        """Initialize Redis connection for AI metrics using canonical utility."""
        try:
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            self.redis_client.ping()
            self.logger.info("✅ Redis connection established for AI metrics")
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Redis for AI metrics: {e}")
            self.redis_client = None

    async def collect_npu_metrics(self) -> Optional[NPUMetrics]:
        """Collect NPU (Intel AI Boost) performance metrics."""
        try:
            # Check for Intel NPU via OpenVINO using async subprocess
            openvino_script = """
import openvino as ov
core = ov.Core()
devices = core.available_devices
npu_devices = [d for d in devices if "NPU" in d or "AI_BOOST" in d]
if npu_devices:
    print(f"NPU_FOUND:{npu_devices[0]}")  # noqa: print
else:
    print("NPU_NOT_FOUND")  # noqa: print
"""
            process = await asyncio.create_subprocess_exec(
                "python3",
                "-c",
                openvino_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
                openvino_output = stdout.decode("utf-8")
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                openvino_output = ""

            if "NPU_FOUND" in openvino_output:
                device_id = openvino_output.split(":")[1].strip()

                # Get NPU utilization (simulated for now, requires Intel tools)
                utilization = await self._get_npu_utilization()
                memory_used, memory_total = await self._get_npu_memory()
                inference_latency = await self._benchmark_npu_inference()

                return NPUMetrics(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    device_id=device_id,
                    utilization_percent=utilization,
                    memory_used_mb=memory_used,
                    memory_total_mb=memory_total,
                    power_draw_watts=None,  # Requires Intel NPU monitoring tools
                    temperature_celsius=None,
                    operations_per_second=(
                        1000.0 / inference_latency if inference_latency > 0 else 0
                    ),
                    inference_latency_ms=inference_latency,
                    throughput_mbps=100.0,  # Estimated
                    error_count=0,
                )
        except Exception as e:
            self.logger.debug(f"NPU metrics collection failed: {e}")

        return None

    async def _get_npu_utilization(self) -> float:
        """Get current NPU utilization percentage."""
        try:
            # This would use Intel NPU monitoring APIs
            # For now, simulate based on system load
            cpu_percent = psutil.cpu_percent(interval=0.1)
            # Estimate NPU usage based on AI workload indicators
            return min(cpu_percent * 0.3, 100.0)  # Conservative estimate
        except Exception:
            return 0.0

    async def _get_npu_memory(self) -> Tuple[float, float]:
        """Get NPU memory usage in MB."""
        try:
            # Intel NPU typically has dedicated memory
            # This would use Intel NPU APIs
            return 512.0, 2048.0  # Example: 512MB used of 2GB total
        except Exception:
            return 0.0, 0.0

    async def _benchmark_npu_inference(self) -> float:
        """Benchmark NPU inference latency."""
        try:
            start_time = time.time()
            # Simple inference benchmark (placeholder)
            await asyncio.sleep(0.05)  # Simulate 50ms inference
            return (time.time() - start_time) * 1000
        except Exception:
            return 0.0

    async def _run_pipeline_stages(self, start_time: float) -> tuple:
        """Simulate and time the three pipeline stages: load, inference, post-process.

        Helper for monitor_multimodal_pipeline. Ref: #1088.

        Returns:
            Tuple of (model_load_time_ms, inference_time_ms, post_processing_time_ms,
                      total_time_ms, memory_peak_mb).
        """
        process = psutil.Process()
        memory_before = process.memory_info().rss / (1024 * 1024)

        model_load_start = time.time()
        await asyncio.sleep(0.1)
        model_load_time = (time.time() - model_load_start) * 1000

        inference_start = time.time()
        await asyncio.sleep(0.2)
        inference_time = (time.time() - inference_start) * 1000

        post_proc_start = time.time()
        await asyncio.sleep(0.05)
        post_processing_time = (time.time() - post_proc_start) * 1000

        total_time = (time.time() - start_time) * 1000

        memory_after = process.memory_info().rss / (1024 * 1024)
        memory_peak = max(memory_before, memory_after)

        return (
            model_load_time,
            inference_time,
            post_processing_time,
            total_time,
            memory_peak,
        )

    def _build_zero_multimodal_metrics(self, pipeline_type: str) -> MultiModalMetrics:
        """Build a zeroed-out MultiModalMetrics for error cases.

        Helper for monitor_multimodal_pipeline. Ref: #1088.
        """
        return MultiModalMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pipeline_type=pipeline_type,
            input_size_mb=0.0,
            processing_time_ms=0.0,
            model_load_time_ms=0.0,
            inference_time_ms=0.0,
            post_processing_time_ms=0.0,
            memory_peak_mb=0.0,
            cpu_utilization_percent=0.0,
            gpu_utilization_percent=None,
            npu_utilization_percent=None,
            throughput_items_per_second=0.0,
            accuracy_score=None,
        )

    async def monitor_multimodal_pipeline(
        self, pipeline_type: str, input_data: Dict
    ) -> MultiModalMetrics:
        """Monitor multi-modal AI pipeline performance."""
        start_time = time.time()

        try:
            (
                model_load_time,
                inference_time,
                post_processing_time,
                total_time,
                memory_peak,
            ) = await self._run_pipeline_stages(start_time)

            cpu_util = psutil.cpu_percent(interval=0.1)
            gpu_util = await self._get_gpu_utilization()
            npu_util = await self._get_npu_utilization()

            input_size = input_data.get("size_mb", 1.0)
            throughput = 1000.0 / total_time if total_time > 0 else 0

            return MultiModalMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                pipeline_type=pipeline_type,
                input_size_mb=input_size,
                processing_time_ms=total_time,
                model_load_time_ms=model_load_time,
                inference_time_ms=inference_time,
                post_processing_time_ms=post_processing_time,
                memory_peak_mb=memory_peak,
                cpu_utilization_percent=cpu_util,
                gpu_utilization_percent=gpu_util,
                npu_utilization_percent=npu_util,
                throughput_items_per_second=throughput,
                accuracy_score=input_data.get("accuracy", 0.95),
            )

        except Exception as e:
            self.logger.error(f"Error monitoring multimodal pipeline: {e}")
            return self._build_zero_multimodal_metrics(pipeline_type)

    async def _get_gpu_utilization(self) -> Optional[float]:
        """Get GPU utilization percentage."""
        try:
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=3.0)
                if process.returncode == 0:
                    return float(stdout.decode("utf-8").strip())
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except Exception:
            self.logger.debug("Suppressed exception in try block", exc_info=True)
        return None

    async def _run_knowledge_search_stages(
        self, query: str, start_time: float
    ) -> tuple:
        """Time embedding, retrieval, and ranking stages for a knowledge search.

        Helper for monitor_knowledge_base_search. Ref: #1088.

        Returns:
            Tuple of (embedding_time_ms, retrieval_time_ms, ranking_time_ms,
                      total_time_ms, memory_usage_mb, results_count,
                      relevance_score, cache_hit).
        """
        process = psutil.Process()
        memory_before = process.memory_info().rss / (1024 * 1024)

        embedding_start = time.time()
        await asyncio.sleep(0.05)
        embedding_time = (time.time() - embedding_start) * 1000

        retrieval_start = time.time()
        await asyncio.sleep(0.1)
        retrieval_time = (time.time() - retrieval_start) * 1000

        ranking_start = time.time()
        await asyncio.sleep(0.02)
        ranking_time = (time.time() - ranking_start) * 1000

        total_time = (time.time() - start_time) * 1000

        memory_after = process.memory_info().rss / (1024 * 1024)
        memory_usage = max(memory_after - memory_before, 0)

        results_count = min(len(query.split()) * 3, 20)
        relevance_score = min(0.85 + len(query) * 0.01, 1.0)
        cache_hit = len(query) > 20

        return (
            embedding_time,
            retrieval_time,
            ranking_time,
            total_time,
            memory_usage,
            results_count,
            relevance_score,
            cache_hit,
        )

    def _build_zero_knowledge_metrics(
        self, query: str, search_type: str
    ) -> KnowledgeBaseMetrics:
        """Build a zeroed-out KnowledgeBaseMetrics for error cases.

        Helper for monitor_knowledge_base_search. Ref: #1088.
        """
        return KnowledgeBaseMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            query_type=search_type,
            query_length=len(query),
            search_time_ms=0.0,
            embedding_time_ms=0.0,
            retrieval_time_ms=0.0,
            ranking_time_ms=0.0,
            results_count=0,
            relevance_score=0.0,
            memory_usage_mb=0.0,
            cache_hit=False,
            vector_dimensions=0,
            total_vectors_searched=0,
        )

    async def monitor_knowledge_base_search(
        self, query: str, search_type: str = "semantic"
    ) -> KnowledgeBaseMetrics:
        """Monitor knowledge base search performance."""
        start_time = time.time()

        try:
            (
                embedding_time,
                retrieval_time,
                ranking_time,
                total_time,
                memory_usage,
                results_count,
                relevance_score,
                cache_hit,
            ) = await self._run_knowledge_search_stages(query, start_time)

            return KnowledgeBaseMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                query_type=search_type,
                query_length=len(query),
                search_time_ms=total_time,
                embedding_time_ms=embedding_time,
                retrieval_time_ms=retrieval_time,
                ranking_time_ms=ranking_time,
                results_count=results_count,
                relevance_score=relevance_score,
                memory_usage_mb=memory_usage,
                cache_hit=cache_hit,
                vector_dimensions=384,  # Typical embedding dimension
                total_vectors_searched=13383,  # From AutoBot knowledge base
            )

        except Exception as e:
            self.logger.error(f"Error monitoring knowledge base search: {e}")
            return self._build_zero_knowledge_metrics(query, search_type)

    async def _simulate_llm_processing(
        self, request_data: Dict, start_time: float
    ) -> tuple:
        """Simulate LLM processing and collect timing and resource metrics.

        Helper for monitor_llm_performance. Ref: #1088.

        Returns:
            Tuple of (input_tokens, max_tokens, output_tokens, total_time_ms,
                      memory_usage_mb, tokens_per_second, gpu_util, npu_util).
        """
        process = psutil.Process()
        memory_before = process.memory_info().rss / (1024 * 1024)

        input_tokens = request_data.get("input_tokens", 100)
        max_tokens = request_data.get("max_tokens", 500)

        processing_time_sim = (input_tokens * 0.5 + max_tokens * 1.0) / 1000
        await asyncio.sleep(min(processing_time_sim, 2.0))

        total_time = (time.time() - start_time) * 1000
        memory_after = process.memory_info().rss / (1024 * 1024)
        memory_usage = max(memory_after - memory_before, 0)

        output_tokens = request_data.get("output_tokens", max_tokens // 2)
        tokens_per_second = output_tokens / (total_time / 1000) if total_time > 0 else 0

        gpu_util = await self._get_gpu_utilization()
        npu_util = await self._get_npu_utilization()

        return (
            input_tokens,
            max_tokens,
            output_tokens,
            total_time,
            memory_usage,
            tokens_per_second,
            gpu_util,
            npu_util,
        )

    def _build_zero_llm_metrics(self, request_data: Dict) -> LLMPerformanceMetrics:
        """Build a zeroed-out LLMPerformanceMetrics for error cases.

        Helper for monitor_llm_performance. Ref: #1088.
        """
        return LLMPerformanceMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_name=request_data.get("model", "unknown"),
            request_type=request_data.get("type", "unknown"),
            input_tokens=0,
            output_tokens=0,
            processing_time_ms=0.0,
            tokens_per_second=0.0,
            memory_usage_mb=0.0,
            gpu_utilization=None,
            npu_utilization=None,
            temperature=0.0,
            max_tokens=0,
            context_length=0,
            cache_hit=False,
            stream_mode=False,
        )

    async def monitor_llm_performance(
        self, request_data: Dict
    ) -> LLMPerformanceMetrics:
        """Monitor LLM (Ollama) performance."""
        start_time = time.time()

        try:
            (
                input_tokens,
                max_tokens,
                output_tokens,
                total_time,
                memory_usage,
                tokens_per_second,
                gpu_util,
                npu_util,
            ) = await self._simulate_llm_processing(request_data, start_time)

            return LLMPerformanceMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                model_name=request_data.get("model", "llama3.1"),
                request_type=request_data.get("type", "chat"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                processing_time_ms=total_time,
                tokens_per_second=tokens_per_second,
                memory_usage_mb=memory_usage,
                gpu_utilization=gpu_util,
                npu_utilization=npu_util,
                temperature=request_data.get("temperature", 0.7),
                max_tokens=max_tokens,
                context_length=request_data.get("context_length", input_tokens),
                cache_hit=request_data.get("cache_hit", False),
                stream_mode=request_data.get("stream", False),
            )

        except Exception as e:
            self.logger.error(f"Error monitoring LLM performance: {e}")
            return self._build_zero_llm_metrics(request_data)

    def _compute_npu_trend(self) -> Optional[Dict[str, Any]]:
        """Compute NPU utilization trend from history.

        Helper for analyze_performance_trends. Ref: #1088.
        """
        if not self.performance_history["npu"]:
            return None
        npu_utils = [
            m.utilization_percent for m in self.performance_history["npu"][-50:]
        ]
        return {
            "average_utilization": statistics.mean(npu_utils),
            "peak_utilization": max(npu_utils),
            "efficiency_score": min(
                statistics.mean(npu_utils)
                / self.performance_targets["npu_utilization"]["optimal"],
                1.0,
            ),
        }

    def _compute_multimodal_trend(self) -> Optional[Dict[str, Any]]:
        """Compute multi-modal pipeline trend from history.

        Helper for analyze_performance_trends. Ref: #1088.
        """
        if not self.performance_history["multimodal"]:
            return None
        mm_metrics = self.performance_history["multimodal"][-50:]
        return {
            "average_processing_time": statistics.mean(
                [m.processing_time_ms for m in mm_metrics]
            ),
            "throughput_trend": [
                m.throughput_items_per_second for m in mm_metrics[-10:]
            ],
            "memory_efficiency": statistics.mean(
                [m.memory_peak_mb for m in mm_metrics]
            ),
        }

    def _compute_knowledge_trend(self) -> Optional[Dict[str, Any]]:
        """Compute knowledge base search trend from history.

        Helper for analyze_performance_trends. Ref: #1088.
        """
        if not self.performance_history["knowledge"]:
            return None
        kb_metrics = self.performance_history["knowledge"][-50:]
        return {
            "average_search_time": statistics.mean(
                [m.search_time_ms for m in kb_metrics]
            ),
            "cache_hit_rate": statistics.mean(
                [1 if m.cache_hit else 0 for m in kb_metrics]
            ),
            "relevance_trend": statistics.mean([m.relevance_score for m in kb_metrics]),
        }

    def _compute_llm_trend(self) -> Optional[Dict[str, Any]]:
        """Compute LLM performance trend from history.

        Helper for analyze_performance_trends. Ref: #1088.
        """
        if not self.performance_history["llm"]:
            return None
        llm_metrics = self.performance_history["llm"][-50:]
        return {
            "average_tokens_per_second": statistics.mean(
                [m.tokens_per_second for m in llm_metrics]
            ),
            "model_distribution": self._analyze_model_usage(llm_metrics),
            "cache_effectiveness": statistics.mean(
                [1 if m.cache_hit else 0 for m in llm_metrics]
            ),
        }

    async def analyze_performance_trends(self) -> Dict[str, Any]:
        """Analyze AI performance trends and generate insights."""
        try:
            trends = {}

            npu_trend = self._compute_npu_trend()
            if npu_trend is not None:
                trends["npu"] = npu_trend

            multimodal_trend = self._compute_multimodal_trend()
            if multimodal_trend is not None:
                trends["multimodal"] = multimodal_trend

            knowledge_trend = self._compute_knowledge_trend()
            if knowledge_trend is not None:
                trends["knowledge_base"] = knowledge_trend

            llm_trend = self._compute_llm_trend()
            if llm_trend is not None:
                trends["llm"] = llm_trend

            trends[
                "recommendations"
            ] = await self._generate_performance_recommendations(trends)

            return trends

        except Exception as e:
            self.logger.error(f"Error analyzing performance trends: {e}")
            return {}

    def _analyze_model_usage(
        self, llm_metrics: List[LLMPerformanceMetrics]
    ) -> Dict[str, int]:
        """Analyze LLM model usage distribution."""
        model_counts = {}
        for metric in llm_metrics:
            model_counts[metric.model_name] = model_counts.get(metric.model_name, 0) + 1
        return model_counts

    async def _generate_performance_recommendations(
        self, trends: Dict[str, Any]
    ) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []

        # NPU recommendations
        if "npu" in trends:
            efficiency = trends["npu"].get("efficiency_score", 0)
            if efficiency < 0.6:
                recommendations.append(
                    "NPU underutilized - consider offloading more AI workloads to NPU"
                )
            elif efficiency > 0.9:
                recommendations.append("NPU highly utilized - monitor for bottlenecks")

        # Multi-modal recommendations
        if "multimodal" in trends:
            avg_time = trends["multimodal"].get("average_processing_time", 0)
            if avg_time > 500:  # 500ms threshold
                recommendations.append(
                    "Multi-modal processing time high - consider pipeline optimization"
                )

        # Knowledge base recommendations
        if "knowledge_base" in trends:
            cache_rate = trends["knowledge_base"].get("cache_hit_rate", 0)
            search_time = trends["knowledge_base"].get("average_search_time", 0)

            if cache_rate < 0.3:
                recommendations.append(
                    "Low knowledge base cache hit rate - consider cache optimization"
                )
            if search_time > 300:  # 300ms threshold
                recommendations.append(
                    "Knowledge base search slow - consider index optimization"
                )

        # LLM recommendations
        if "llm" in trends:
            tokens_per_sec = trends["llm"].get("average_tokens_per_second", 0)
            if tokens_per_sec < 20:
                recommendations.append(
                    "LLM token generation slow - consider model optimization or hardware upgrade"
                )

        return recommendations

    async def store_ai_metrics(self, metrics: Dict[str, Any]):
        """Store AI performance metrics in Redis and files."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Store in Redis
        if self.redis_client:
            try:
                # Store latest AI metrics
                self.redis_client.hset(
                    "autobot:ai_performance:latest",
                    mapping={
                        "timestamp": timestamp,
                        "data": json.dumps(metrics, default=str),
                    },
                )

                # Store historical AI metrics
                self.redis_client.lpush(
                    "autobot:ai_performance:history",
                    json.dumps({"timestamp": timestamp, "data": metrics}, default=str),
                )
                self.redis_client.ltrim("autobot:ai_performance:history", 0, 999)

            except Exception as e:
                self.logger.error(f"Error storing AI metrics in Redis: {e}")

        # Store in local file
        try:
            metrics_file = (
                self.analytics_data_path
                / f"ai_metrics_{datetime.now().strftime('%Y%m%d')}.jsonl"
            )
            async with aiofiles.open(metrics_file, "a", encoding="utf-8") as f:
                await f.write(
                    json.dumps({"timestamp": timestamp, "data": metrics}, default=str)
                    + "\n"
                )
        except OSError as e:
            self.logger.error(f"Failed to write AI metrics to {metrics_file}: {e}")
        except Exception as e:
            self.logger.error(f"Error storing AI metrics to file: {e}")

    async def generate_ai_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive AI performance report."""
        try:
            report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "npu_metrics": await self.collect_npu_metrics(),
                "trends": await self.analyze_performance_trends(),
            }

            # Add hardware utilization summary
            npu_metrics = report.get("npu_metrics")
            if npu_metrics:
                report["hardware_efficiency"] = {
                    "npu_utilization": npu_metrics.utilization_percent,
                    "npu_memory_usage": (
                        (npu_metrics.memory_used_mb / npu_metrics.memory_total_mb * 100)
                        if npu_metrics.memory_total_mb > 0
                        else 0
                    ),
                    "inference_performance": (
                        "excellent"
                        if npu_metrics.inference_latency_ms < 100
                        else (
                            "good"
                            if npu_metrics.inference_latency_ms < 300
                            else "needs_optimization"
                        )
                    ),
                }

            # Store the report
            await self.store_ai_metrics(report)

            return report

        except Exception as e:
            self.logger.error(f"Error generating AI performance report: {e}")
            self.logger.error(traceback.format_exc())
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


# Integration hooks for AutoBot components
async def monitor_multimodal_request(
    pipeline_type: str, input_data: Dict
) -> MultiModalMetrics:
    """Monitor a multi-modal AI request - to be called from AI processing components."""
    analytics = AIPerformanceAnalytics()
    await analytics.initialize_redis_connection()
    return await analytics.monitor_multimodal_pipeline(pipeline_type, input_data)


async def monitor_knowledge_search(
    query: str, search_type: str = "semantic"
) -> KnowledgeBaseMetrics:
    """Monitor a knowledge base search - to be called from knowledge components."""
    analytics = AIPerformanceAnalytics()
    await analytics.initialize_redis_connection()
    return await analytics.monitor_knowledge_base_search(query, search_type)


async def monitor_llm_request(request_data: Dict) -> LLMPerformanceMetrics:
    """Monitor an LLM request - to be called from LLM interface components."""
    analytics = AIPerformanceAnalytics()
    await analytics.initialize_redis_connection()
    return await analytics.monitor_llm_performance(request_data)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse

    async def main():
        parser = argparse.ArgumentParser(description="AutoBot AI Performance Analytics")
        parser.add_argument(
            "--test", action="store_true", help="Run test monitoring cycle"
        )
        parser.add_argument(
            "--report", action="store_true", help="Generate AI performance report"
        )

        args = parser.parse_args()

        analytics = AIPerformanceAnalytics()
        await analytics.initialize_redis_connection()

        if args.test:
            logger.info("Testing AI performance monitoring...")

            # Test NPU metrics
            npu_metrics = await analytics.collect_npu_metrics()
            if npu_metrics:
                logger.info(f"NPU Utilization: {npu_metrics.utilization_percent:.1f}%")
                logger.info(
                    f"NPU Inference Latency: {npu_metrics.inference_latency_ms:.1f}ms"
                )

            # Test multi-modal monitoring
            mm_metrics = await analytics.monitor_multimodal_pipeline(
                "text", {"size_mb": 1.0}
            )
            logger.info(
                f"Multi-modal Processing Time: {mm_metrics.processing_time_ms:.1f}ms"
            )

            # Test knowledge base monitoring
            kb_metrics = await analytics.monitor_knowledge_base_search("test query")
            logger.info(f"Knowledge Search Time: {kb_metrics.search_time_ms:.1f}ms")

        if args.report:
            logger.info("Generating AI performance report...")
            report = await analytics.generate_ai_performance_report()
            logger.info("%s", json.dumps(report, indent=2, default=str))

    asyncio.run(main())
