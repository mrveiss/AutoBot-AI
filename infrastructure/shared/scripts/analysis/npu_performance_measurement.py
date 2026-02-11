#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Performance Measurement and Analysis for AutoBot
Comprehensive testing and benchmarking of NPU semantic search acceleration
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import logging

logger = logging.getLogger(__name__)

# Add AutoBot to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from ai_hardware_accelerator import HardwareDevice
from constants.network_constants import NetworkConstants
from npu_semantic_search import get_npu_search_engine
from utils.logging_manager import get_llm_logger

logger = get_llm_logger("npu_performance_measurement")


class NPUPerformanceMeasurement:
    """Comprehensive NPU performance measurement and analysis."""

    def __init__(self):
        self.npu_worker_url = (
            f"http://{NetworkConstants.NPU_WORKER_LINUX_VM_IP}"
            f":{NetworkConstants.NPU_WORKER_PORT}"
        )
        self.backend_url = (
            f"http://{NetworkConstants.LOCALHOST_IP}"
            f":{NetworkConstants.BACKEND_PORT}"
        )
        self.results = {}
        self.test_queries = [
            "linux file management commands",
            "docker container orchestration",
            "python async programming patterns",
            "autobot system configuration",
            "redis database optimization",
            "machine learning model deployment",
            "kubernetes cluster management",
            "typescript frontend development",
            "database query optimization",
            "network security protocols",
        ]

    async def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive performance benchmark."""
        logger.info("Starting comprehensive NPU performance measurement")

        benchmark_results = {
            "timestamp": datetime.now().isoformat(),
            "test_configuration": {
                "test_queries": len(self.test_queries),
                "npu_worker_url": self.npu_worker_url,
                "backend_url": self.backend_url,
            },
            "hardware_baseline": {},
            "npu_worker_tests": {},
            "semantic_search_tests": {},
            "api_endpoint_tests": {},
            "performance_comparison": {},
            "recommendations": [],
        }

        try:
            await self._run_benchmark_steps(benchmark_results)
            logger.info("Comprehensive benchmark completed successfully")
        except Exception as e:
            logger.error("Benchmark failed: %s", e)
            benchmark_results["error"] = str(e)

        return benchmark_results

    async def _run_benchmark_steps(self, results: Dict[str, Any]):
        """Execute all benchmark steps sequentially.

        Helper for run_comprehensive_benchmark (#825).
        """
        logger.info("Step 1: Measuring hardware baseline performance")
        results["hardware_baseline"] = await self._measure_hardware_baseline()

        logger.info("Step 2: Testing NPU Worker direct performance")
        results["npu_worker_tests"] = await self._test_npu_worker_direct()

        logger.info("Step 3: Testing semantic search engine performance")
        results["semantic_search_tests"] = (
            await self._test_semantic_search_engine()
        )

        logger.info("Step 4: Testing API endpoint performance")
        results["api_endpoint_tests"] = await self._test_api_endpoints()

        logger.info("Step 5: Analyzing performance comparisons")
        results["performance_comparison"] = (
            await self._analyze_performance_comparison(results)
        )

        logger.info("Step 6: Generating optimization recommendations")
        results["recommendations"] = (
            await self._generate_recommendations(results)
        )

    def _collect_cpu_info(self) -> Dict[str, Any]:
        """Collect CPU and memory information via psutil.

        Helper for _measure_hardware_baseline (#825).
        """
        import psutil

        return {
            "cpu_count": psutil.cpu_count(),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_total_gb": round(
                psutil.virtual_memory().total / (1024**3), 2
            ),
            "memory_available_gb": round(
                psutil.virtual_memory().available / (1024**3), 2
            ),
        }

    def _collect_gpu_info(self) -> Dict[str, Any]:
        """Collect GPU information via torch.

        Helper for _measure_hardware_baseline (#825).
        """
        try:
            import torch

            if torch.cuda.is_available():
                gpu_info = {
                    "gpu_available": True,
                    "gpu_name": torch.cuda.get_device_name(0),
                    "gpu_count": torch.cuda.device_count(),
                    "gpu_memory_total_gb": round(
                        torch.cuda.get_device_properties(0).total_memory
                        / (1024**3),
                        2,
                    ),
                }
                torch.cuda.empty_cache()
                gpu_info["gpu_memory_allocated_gb"] = round(
                    torch.cuda.memory_allocated(0) / (1024**3), 2
                )
                return gpu_info
            return {"gpu_available": False}
        except ImportError:
            return {"gpu_available": False, "torch_not_available": True}

    async def _measure_hardware_baseline(self) -> Dict[str, Any]:
        """Measure hardware baseline performance without NPU acceleration."""
        baseline_results = {
            "cpu_info": {},
            "gpu_info": {},
            "memory_info": {},
            "cpu_embedding_performance": {},
            "gpu_embedding_performance": {},
        }

        try:
            baseline_results["cpu_info"] = self._collect_cpu_info()
            baseline_results["gpu_info"] = self._collect_gpu_info()

            baseline_results["cpu_embedding_performance"] = (
                await self._test_cpu_embedding_performance()
            )

            if baseline_results["gpu_info"].get("gpu_available", False):
                baseline_results["gpu_embedding_performance"] = (
                    await self._test_gpu_embedding_performance()
                )

        except Exception as e:
            logger.error("Hardware baseline measurement failed: %s", e)
            baseline_results["error"] = str(e)

        return baseline_results

    async def _test_cpu_embedding_performance(self) -> Dict[str, Any]:
        """Test CPU-only embedding performance."""
        cpu_results = {
            "single_text_times": [],
            "batch_times": {},
            "average_performance": {},
        }

        try:
            from utils.semantic_chunker import get_semantic_chunker

            chunker = get_semantic_chunker()
            original_model = chunker._embedding_model
            chunker._embedding_model = None

            test_text = (
                "This is a test sentence for CPU embedding performance."
            )

            for _i in range(5):
                start_time = time.time()
                chunker._compute_sentence_embeddings([test_text])
                elapsed = (time.time() - start_time) * 1000
                cpu_results["single_text_times"].append(elapsed)

            cpu_results["batch_times"] = self._run_batch_embedding_test(
                chunker._compute_sentence_embeddings, [1, 5, 10, 25, 50],
            )

            cpu_results["average_performance"] = (
                self._compute_time_stats(cpu_results["single_text_times"])
            )

            chunker._embedding_model = original_model

        except Exception as e:
            logger.error("CPU embedding performance test failed: %s", e)
            cpu_results["error"] = str(e)

        return cpu_results

    async def _test_gpu_embedding_performance(self) -> Dict[str, Any]:
        """Test GPU embedding performance."""
        gpu_results = {
            "single_text_times": [],
            "batch_times": {},
            "average_performance": {},
        }

        try:
            from utils.semantic_chunker import get_semantic_chunker

            chunker = get_semantic_chunker()
            await chunker._initialize_model()

            test_text = (
                "This is a test sentence for GPU embedding performance."
            )

            for _i in range(5):
                start_time = time.time()
                await chunker._compute_sentence_embeddings_async([test_text])
                elapsed = (time.time() - start_time) * 1000
                gpu_results["single_text_times"].append(elapsed)

            for batch_size in [1, 5, 10, 25, 50, 100]:
                batch_texts = [
                    f"Test sentence number {i} for GPU batch processing."
                    for i in range(batch_size)
                ]
                start_time = time.time()
                await chunker._compute_sentence_embeddings_async(batch_texts)
                elapsed = (time.time() - start_time) * 1000
                gpu_results["batch_times"][str(batch_size)] = {
                    "total_time_ms": elapsed,
                    "per_text_ms": elapsed / batch_size,
                }

            gpu_results["average_performance"] = (
                self._compute_time_stats(gpu_results["single_text_times"])
            )

        except Exception as e:
            logger.error("GPU embedding performance test failed: %s", e)
            gpu_results["error"] = str(e)

        return gpu_results

    def _run_batch_embedding_test(self, embed_fn, batch_sizes) -> Dict:
        """Run batch embedding tests across multiple batch sizes.

        Helper for _test_cpu_embedding_performance (#825).
        """
        batch_times = {}
        for batch_size in batch_sizes:
            batch_texts = [
                f"Test sentence number {i} for batch processing."
                for i in range(batch_size)
            ]
            start_time = time.time()
            embed_fn(batch_texts)
            elapsed = (time.time() - start_time) * 1000
            batch_times[str(batch_size)] = {
                "total_time_ms": elapsed,
                "per_text_ms": elapsed / batch_size,
            }
        return batch_times

    def _compute_time_stats(self, times: List[float]) -> Dict[str, float]:
        """Compute average/std/min/max statistics for timing data.

        Helper for _test_cpu_embedding_performance (#825).
        """
        return {
            "avg_single_text_ms": np.mean(times),
            "std_single_text_ms": np.std(times),
            "min_single_text_ms": np.min(times),
            "max_single_text_ms": np.max(times),
        }

    async def _test_npu_worker_direct(self) -> Dict[str, Any]:
        """Test NPU Worker direct API performance."""
        npu_results = {
            "connectivity": {},
            "health_check": {},
            "embedding_generation": {},
            "semantic_search": {},
            "model_optimization": {},
        }

        try:
            start_time = time.time()
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                npu_results["connectivity"] = (
                    await self._check_npu_connectivity(session, start_time)
                )
                if npu_results["connectivity"].get("npu_available"):
                    npu_results["health_check"] = (
                        npu_results["connectivity"].pop("_health_data", {})
                    )

                if npu_results["connectivity"]["success"]:
                    npu_results["embedding_generation"] = (
                        await self._test_npu_embedding_generation(session)
                    )
                    npu_results["semantic_search"] = (
                        await self._test_npu_semantic_search(session)
                    )

        except Exception as e:
            logger.error("NPU Worker direct test failed: %s", e)
            npu_results["error"] = str(e)

        return npu_results

    async def _check_npu_connectivity(
        self, session, start_time: float,
    ) -> Dict[str, Any]:
        """Check NPU worker connectivity and health.

        Helper for _test_npu_worker_direct (#825).
        """
        try:
            async with session.get(
                f"{self.npu_worker_url}/health"
            ) as response:
                elapsed = (time.time() - start_time) * 1000
                if response.status == 200:
                    health_data = await response.json()
                    return {
                        "success": True,
                        "response_time_ms": elapsed,
                        "npu_available": health_data.get(
                            "npu_available", False
                        ),
                        "_health_data": health_data,
                    }
                return {
                    "success": False,
                    "status_code": response.status,
                    "response_time_ms": elapsed,
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response_time_ms": (time.time() - start_time) * 1000,
            }

    async def _test_single_npu_embedding(
        self, session, text: str,
    ) -> Dict[str, Any]:
        """Test a single NPU embedding generation request.

        Helper for _test_npu_embedding_generation (#825).
        """
        start_time = time.time()
        async with session.post(
            f"{self.npu_worker_url}/embedding/generate",
            json={
                "texts": [text],
                "model_name": "nomic-embed-text",
                "use_cache": False,
                "optimization_level": "speed",
            },
        ) as response:
            if response.status == 200:
                result = await response.json()
                elapsed = (time.time() - start_time) * 1000
                return {
                    "text": text,
                    "processing_time_ms": elapsed,
                    "npu_time_ms": result.get("processing_time_ms", 0),
                    "device_used": result.get("device", "unknown"),
                    "embedding_dimension": len(
                        result.get("embeddings", [])
                    ),
                    "success": True,
                }
            return {
                "text": text,
                "error": f"HTTP {response.status}",
                "success": False,
            }

    async def _test_npu_batch_embedding(
        self, session, batch_size: int,
    ) -> Dict[str, Any]:
        """Test a batch NPU embedding generation request.

        Helper for _test_npu_embedding_generation (#825).
        """
        batch_texts = [
            f"Batch test sentence {i}" for i in range(batch_size)
        ]
        start_time = time.time()
        async with session.post(
            f"{self.npu_worker_url}/embedding/generate",
            json={
                "texts": batch_texts,
                "model_name": "nomic-embed-text",
                "use_cache": False,
                "optimization_level": "balanced",
            },
        ) as response:
            if response.status == 200:
                result = await response.json()
                elapsed = (time.time() - start_time) * 1000
                return {
                    "total_time_ms": elapsed,
                    "npu_time_ms": result.get("processing_time_ms", 0),
                    "per_text_ms": elapsed / batch_size,
                    "device_used": result.get("device", "unknown"),
                    "texts_processed": result.get("texts_processed", 0),
                    "success": True,
                }
            return {
                "error": f"HTTP {response.status}",
                "success": False,
            }

    async def _test_npu_embedding_generation(
        self, session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """Test NPU Worker embedding generation."""
        embedding_results = {
            "single_embeddings": [],
            "batch_embeddings": {},
            "performance_metrics": {},
        }

        try:
            test_texts = [
                "NPU embedding generation test",
                "AutoBot semantic search optimization",
                "Intel NPU hardware acceleration",
            ]

            for text in test_texts:
                result = await self._test_single_npu_embedding(session, text)
                embedding_results["single_embeddings"].append(result)

            for batch_size in [5, 10, 25]:
                batch_result = await self._test_npu_batch_embedding(
                    session, batch_size,
                )
                embedding_results["batch_embeddings"][str(batch_size)] = (
                    batch_result
                )

            embedding_results["performance_metrics"] = (
                self._calc_embedding_metrics(
                    embedding_results["single_embeddings"]
                )
            )

        except Exception as e:
            logger.error("NPU embedding generation test failed: %s", e)
            embedding_results["error"] = str(e)

        return embedding_results

    def _calc_embedding_metrics(
        self, single_results: List[Dict],
    ) -> Dict[str, Any]:
        """Calculate performance metrics from single embedding results.

        Helper for _test_npu_embedding_generation (#825).
        """
        successful = [r for r in single_results if r["success"]]
        if not successful:
            return {}

        times = [r["processing_time_ms"] for r in successful]
        return {
            "avg_single_time_ms": np.mean(times),
            "min_single_time_ms": np.min(times),
            "max_single_time_ms": np.max(times),
            "std_single_time_ms": np.std(times),
            "success_rate": len(successful) / len(single_results) * 100,
        }

    async def _run_semantic_search_queries(
        self, session, document_embeddings, test_documents,
    ) -> List[Dict[str, Any]]:
        """Run semantic search queries against NPU worker.

        Helper for _test_npu_semantic_search (#825).
        """
        test_queries = [
            "file operations in linux",
            "container management",
            "async python programming",
        ]
        results = []

        for query in test_queries:
            start_time = time.time()
            async with session.post(
                f"{self.npu_worker_url}/search/semantic",
                json={
                    "query_text": query,
                    "document_embeddings": document_embeddings,
                    "document_metadata": [
                        {"text": doc} for doc in test_documents
                    ],
                    "top_k": 3,
                    "similarity_threshold": 0.5,
                },
            ) as search_response:
                if search_response.status == 200:
                    search_result = await search_response.json()
                    elapsed = (time.time() - start_time) * 1000
                    results.append({
                        "query": query,
                        "total_time_ms": elapsed,
                        "npu_time_ms": search_result.get(
                            "processing_time_ms", 0
                        ),
                        "documents_searched": search_result.get(
                            "documents_searched", 0
                        ),
                        "results_returned": search_result.get(
                            "results_returned", 0
                        ),
                        "device_used": search_result.get(
                            "device", "unknown"
                        ),
                        "success": True,
                    })
                else:
                    results.append({
                        "query": query,
                        "error": f"HTTP {search_response.status}",
                        "success": False,
                    })

        return results

    async def _test_npu_semantic_search(
        self, session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """Test NPU Worker semantic search."""
        search_results = {"search_tests": [], "performance_metrics": {}}

        try:
            test_documents = [
                "Linux system administration and file management",
                "Docker container orchestration and deployment",
                "Python programming and async development",
                "AutoBot configuration and setup procedures",
                "Redis database optimization and management",
            ]

            async with session.post(
                f"{self.npu_worker_url}/embedding/generate",
                json={
                    "texts": test_documents,
                    "model_name": "nomic-embed-text",
                    "use_cache": True,
                    "optimization_level": "balanced",
                },
            ) as response:
                if response.status == 200:
                    embedding_result = await response.json()
                    doc_embeddings = embedding_result.get("embeddings", [])

                    search_results["search_tests"] = (
                        await self._run_semantic_search_queries(
                            session, doc_embeddings, test_documents,
                        )
                    )

                    successful = [
                        r for r in search_results["search_tests"]
                        if r["success"]
                    ]
                    if successful:
                        times = [r["total_time_ms"] for r in successful]
                        search_results["performance_metrics"] = {
                            "avg_search_time_ms": np.mean(times),
                            "min_search_time_ms": np.min(times),
                            "max_search_time_ms": np.max(times),
                            "success_rate": (
                                len(successful)
                                / len(search_results["search_tests"])
                                * 100
                            ),
                        }

        except Exception as e:
            logger.error("NPU semantic search test failed: %s", e)
            search_results["error"] = str(e)

        return search_results

    async def _run_search_config_test(
        self, search_engine, config: Dict, queries: List[str],
    ) -> List[Dict[str, Any]]:
        """Run search tests for a single configuration.

        Helper for _test_semantic_search_engine (#825).
        """
        config_results = []

        for query in queries:
            try:
                start_time = time.time()
                force_device = None
                if config["force_device"]:
                    force_device = HardwareDevice(config["force_device"])

                results, metrics = await search_engine.enhanced_search(
                    query=query,
                    similarity_top_k=5,
                    enable_npu_acceleration=config["enable_npu"],
                    force_device=force_device,
                )
                elapsed = (time.time() - start_time) * 1000

                config_results.append({
                    "query": query,
                    "total_time_ms": elapsed,
                    "results_count": len(results),
                    "device_used": metrics.device_used,
                    "embedding_time_ms": (
                        metrics.embedding_generation_time_ms
                    ),
                    "search_time_ms": (
                        metrics.similarity_computation_time_ms
                    ),
                    "success": True,
                })
            except Exception as e:
                config_results.append({
                    "query": query,
                    "error": str(e),
                    "success": False,
                })

        return config_results

    def _summarize_config_results(
        self, config: Dict, config_results: List[Dict],
    ) -> Dict[str, Any]:
        """Summarize results for a single search configuration.

        Helper for _test_semantic_search_engine (#825).
        """
        successful = [r for r in config_results if r["success"]]
        if not successful:
            return {"config": config, "detailed_results": config_results}

        times = [r["total_time_ms"] for r in successful]
        embedding_times = [r["embedding_time_ms"] for r in successful]
        search_times = [r["search_time_ms"] for r in successful]

        return {
            "config": config,
            "avg_total_time_ms": np.mean(times),
            "avg_embedding_time_ms": np.mean(embedding_times),
            "avg_search_time_ms": np.mean(search_times),
            "success_rate": (
                len(successful) / len(config_results) * 100
            ),
            "detailed_results": config_results,
        }

    async def _test_semantic_search_engine(self) -> Dict[str, Any]:
        """Test the integrated semantic search engine."""
        engine_results = {
            "initialization": {},
            "search_performance": {},
            "hardware_utilization": {},
            "cache_performance": {},
        }

        try:
            start_time = time.time()
            search_engine = await get_npu_search_engine()
            init_time = (time.time() - start_time) * 1000

            engine_results["initialization"] = {
                "init_time_ms": init_time,
                "success": True,
            }

            search_configs = [
                {"enable_npu": True, "force_device": None},
                {"enable_npu": True, "force_device": "npu"},
                {"enable_npu": True, "force_device": "gpu"},
                {"enable_npu": False, "force_device": "cpu"},
            ]

            engine_results["search_performance"] = {}
            queries = self.test_queries[:5]

            for i, config in enumerate(search_configs):
                config_results = await self._run_search_config_test(
                    search_engine, config, queries,
                )
                engine_results["search_performance"][f"config_{i+1}"] = (
                    self._summarize_config_results(config, config_results)
                )

            engine_results["hardware_utilization"] = (
                await search_engine.get_search_statistics()
            )

        except Exception as e:
            logger.error("Semantic search engine test failed: %s", e)
            engine_results["error"] = str(e)

        return engine_results

    async def _test_api_health_check(self, session) -> Dict[str, Any]:
        """Test the search API health endpoint.

        Helper for _test_api_endpoints (#825).
        """
        start_time = time.time()
        async with session.get(
            f"{self.backend_url}/api/search/health"
        ) as response:
            elapsed = (time.time() - start_time) * 1000
            if response.status == 200:
                return {
                    "success": True,
                    "response_time_ms": elapsed,
                    "data": await response.json(),
                }
            return {
                "success": False,
                "status_code": response.status,
                "response_time_ms": elapsed,
            }

    async def _test_api_semantic_search(
        self, session, queries: List[str],
    ) -> Dict[str, Any]:
        """Test the semantic search API endpoint.

        Helper for _test_api_endpoints (#825).
        """
        search_tests = []
        for query in queries:
            start_time = time.time()
            async with session.post(
                f"{self.backend_url}/api/search/semantic",
                json={
                    "query": query,
                    "similarity_top_k": 5,
                    "enable_npu_acceleration": True,
                },
            ) as response:
                elapsed = (time.time() - start_time) * 1000
                if response.status == 200:
                    data = await response.json()
                    search_tests.append({
                        "query": query,
                        "response_time_ms": elapsed,
                        "api_search_time_ms": data.get(
                            "search_time_ms", 0
                        ),
                        "results_count": data.get("total_results", 0),
                        "device_used": data.get("device_used", "unknown"),
                        "success": True,
                    })
                else:
                    search_tests.append({
                        "query": query,
                        "error": f"HTTP {response.status}",
                        "success": False,
                    })

        avg_time = 0
        successful = [t for t in search_tests if t["success"]]
        if successful:
            avg_time = np.mean([t["response_time_ms"] for t in successful])

        return {"tests": search_tests, "avg_response_time_ms": avg_time}

    async def _test_api_hardware_status(self, session) -> Dict[str, Any]:
        """Test the hardware status API endpoint.

        Helper for _test_api_endpoints (#825).
        """
        start_time = time.time()
        async with session.get(
            f"{self.backend_url}/api/search/hardware/status"
        ) as response:
            if response.status == 200:
                return {
                    "success": True,
                    "response_time_ms": (time.time() - start_time) * 1000,
                    "data": await response.json(),
                }
            return {
                "success": False,
                "status_code": response.status,
            }

    async def _test_api_endpoints(self) -> Dict[str, Any]:
        """Test the enhanced search API endpoints."""
        api_results = {
            "health_check": {},
            "semantic_search": {},
            "hardware_status": {},
            "benchmark": {},
        }

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                api_results["health_check"] = (
                    await self._test_api_health_check(session)
                )

                if api_results["health_check"]["success"]:
                    api_results["semantic_search"] = (
                        await self._test_api_semantic_search(
                            session, self.test_queries[:3],
                        )
                    )
                    api_results["hardware_status"] = (
                        await self._test_api_hardware_status(session)
                    )

        except Exception as e:
            logger.error("API endpoint test failed: %s", e)
            api_results["error"] = str(e)

        return api_results

    def _compute_device_comparison(
        self, cpu_perf: Dict, gpu_perf: Dict, npu_perf: Dict,
    ) -> Dict[str, Dict]:
        """Compute device performance and speedup analysis.

        Helper for _analyze_performance_comparison (#825).
        """
        device_performance = {
            "cpu_avg_ms": cpu_perf.get("avg_single_text_ms", 0),
            "gpu_avg_ms": gpu_perf.get("avg_single_text_ms", 0),
            "npu_avg_ms": npu_perf.get("avg_single_time_ms", 0),
        }

        cpu_time = cpu_perf.get("avg_single_text_ms", 1)
        gpu_time = gpu_perf.get("avg_single_text_ms", 1)
        npu_time = npu_perf.get("avg_single_time_ms", 1)

        speedup_analysis = {
            "gpu_vs_cpu_speedup": (
                cpu_time / gpu_time if gpu_time > 0 else 0
            ),
            "npu_vs_cpu_speedup": (
                cpu_time / npu_time if npu_time > 0 else 0
            ),
            "npu_vs_gpu_speedup": (
                gpu_time / npu_time if npu_time > 0 else 0
            ),
        }

        return {
            "device_performance": device_performance,
            "speedup_analysis": speedup_analysis,
        }

    def _compute_efficiency_metrics(
        self, search_performance: Dict,
    ) -> Dict[str, Any]:
        """Compute efficiency metrics from search configuration results.

        Helper for _analyze_performance_comparison (#825).
        """
        config_times = {}
        for config_name, config_data in search_performance.items():
            if "avg_total_time_ms" in config_data:
                config_times[config_name] = config_data["avg_total_time_ms"]

        if not config_times:
            return {}

        return {
            "configuration_performance": config_times,
            "best_configuration": min(
                config_times.keys(), key=lambda k: config_times[k]
            ),
            "worst_configuration": max(
                config_times.keys(), key=lambda k: config_times[k]
            ),
        }

    async def _analyze_performance_comparison(
        self, benchmark_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze performance comparisons between configurations."""
        comparison = {
            "device_performance": {},
            "speedup_analysis": {},
            "efficiency_metrics": {},
            "hardware_utilization": {},
        }

        try:
            hardware_baseline = benchmark_results.get(
                "hardware_baseline", {}
            )
            npu_worker = benchmark_results.get("npu_worker_tests", {})
            semantic_search = benchmark_results.get(
                "semantic_search_tests", {}
            )

            cpu_perf = hardware_baseline.get(
                "cpu_embedding_performance", {}
            ).get("average_performance", {})
            gpu_perf = hardware_baseline.get(
                "gpu_embedding_performance", {}
            ).get("average_performance", {})
            npu_perf = npu_worker.get(
                "embedding_generation", {}
            ).get("performance_metrics", {})

            if cpu_perf and gpu_perf and npu_perf:
                device_data = self._compute_device_comparison(
                    cpu_perf, gpu_perf, npu_perf,
                )
                comparison.update(device_data)

            search_performance = semantic_search.get(
                "search_performance", {}
            )
            if search_performance:
                comparison["efficiency_metrics"] = (
                    self._compute_efficiency_metrics(search_performance)
                )

            comparison["hardware_utilization"] = (
                self._build_hardware_utilization(
                    hardware_baseline, npu_worker,
                )
            )

        except Exception as e:
            logger.error("Performance comparison analysis failed: %s", e)
            comparison["error"] = str(e)

        return comparison

    def _build_hardware_utilization(
        self, hardware_baseline: Dict, npu_worker: Dict,
    ) -> Dict[str, Any]:
        """Build hardware utilization summary dict.

        Helper for _analyze_performance_comparison (#825).
        """
        hardware_info = hardware_baseline.get("cpu_info", {})
        gpu_info = hardware_baseline.get("gpu_info", {})

        return {
            "cpu_cores_available": hardware_info.get(
                "cpu_count_logical", 0
            ),
            "cpu_utilization_during_test": hardware_info.get(
                "cpu_percent", 0
            ),
            "gpu_available": gpu_info.get("gpu_available", False),
            "gpu_memory_total_gb": gpu_info.get("gpu_memory_total_gb", 0),
            "npu_worker_available": npu_worker.get(
                "connectivity", {}
            ).get("success", False),
            "npu_available": npu_worker.get(
                "health_check", {}
            ).get("npu_available", False),
        }

    def _get_npu_availability_recs(
        self, npu_worker: Dict,
    ) -> List[str]:
        """Generate NPU availability recommendations.

        Helper for _generate_recommendations (#825).
        """
        npu_available = npu_worker.get("health_check", {}).get(
            "npu_available", False
        )
        npu_connected = npu_worker.get("connectivity", {}).get(
            "success", False
        )

        if not npu_connected:
            return [
                "CRITICAL: NPU Worker not accessible"
                " - verify VM2 (172.16.168.22) is running"
                " and NPU Worker service is started"
            ]
        if not npu_available:
            return [
                "NPU hardware not available"
                " - install Intel NPU drivers and OpenVINO"
                " for optimal performance"
            ]
        return [
            "NPU Worker is operational"
            " - NPU acceleration is available"
        ]

    def _get_speedup_recs(self, speedup: Dict) -> List[str]:
        """Generate speedup-based recommendations.

        Helper for _generate_recommendations (#825).
        """
        recs = []
        npu_vs_cpu = speedup.get("npu_vs_cpu_speedup", 0)
        npu_vs_gpu = speedup.get("npu_vs_gpu_speedup", 0)

        if npu_vs_cpu > 5:
            recs.append(
                f"Excellent NPU performance: {npu_vs_cpu:.1f}x"
                " faster than CPU - route lightweight tasks to NPU"
            )
        elif npu_vs_cpu > 2:
            recs.append(
                f"Good NPU performance: {npu_vs_cpu:.1f}x"
                " faster than CPU - optimize NPU utilization"
            )
        elif npu_vs_cpu < 1:
            recs.append(
                "NPU performance suboptimal"
                " - check NPU optimization settings"
                " and model quantization"
            )

        if npu_vs_gpu > 1.5:
            recs.append(
                f"NPU outperforms GPU for embedding tasks"
                f" ({npu_vs_gpu:.1f}x)"
                " - prioritize NPU for semantic search"
            )
        elif npu_vs_gpu < 0.7:
            recs.append(
                "GPU outperforms NPU for these tasks"
                " - consider GPU-first routing strategy"
            )

        return recs

    def _get_hardware_util_recs(
        self, hardware_util: Dict,
    ) -> List[str]:
        """Generate hardware utilization recommendations.

        Helper for _generate_recommendations (#825).
        """
        recs = []
        cpu_cores = hardware_util.get("cpu_cores_available", 0)
        gpu_available = hardware_util.get("gpu_available", False)

        if cpu_cores >= 16:
            recs.append(
                f"High-core CPU detected ({cpu_cores} cores)"
                " - optimize parallel processing and batch sizes"
            )

        if gpu_available:
            gpu_memory = hardware_util.get("gpu_memory_total_gb", 0)
            if gpu_memory >= 8:
                recs.append(
                    f"High-memory GPU available ({gpu_memory}GB)"
                    " - optimize for large batch processing"
                )

        return recs

    async def _generate_recommendations(
        self, benchmark_results: Dict[str, Any]
    ) -> List[str]:
        """Generate optimization recommendations based on benchmarks."""
        recommendations = []

        try:
            comparison = benchmark_results.get(
                "performance_comparison", {}
            )
            npu_worker = benchmark_results.get("npu_worker_tests", {})

            recommendations.extend(
                self._get_npu_availability_recs(npu_worker)
            )

            speedup = comparison.get("speedup_analysis", {})
            if speedup:
                recommendations.extend(self._get_speedup_recs(speedup))

            hardware_util = comparison.get("hardware_utilization", {})
            if hardware_util:
                recommendations.extend(
                    self._get_hardware_util_recs(hardware_util)
                )

            efficiency = comparison.get("efficiency_metrics", {})
            if efficiency:
                best_config = efficiency.get("best_configuration")
                if best_config:
                    recommendations.append(
                        f"Optimal configuration identified:"
                        f" {best_config}"
                        " - use this for production workloads"
                    )

            if not recommendations:
                recommendations.append(
                    "System performance analysis incomplete"
                    " - run full benchmark for detailed"
                    " recommendations"
                )

            recommendations.append(
                "Monitor hardware utilization during production"
                " workloads for ongoing optimization"
            )
            recommendations.append(
                "Consider workload-specific optimization"
                " (latency vs throughput vs quality)"
            )

        except Exception as e:
            logger.error("Recommendation generation failed: %s", e)
            recommendations.append(
                f"Recommendation generation failed: {e}"
            )

        return recommendations

    def save_results(
        self, results: Dict[str, Any], filename: str = None,
    ):
        """Save benchmark results to file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"npu_performance_results_{timestamp}.json"

        results_dir = (
            Path(__file__).parent.parent.parent / "reports" / "performance"
        )
        results_dir.mkdir(parents=True, exist_ok=True)

        results_path = results_dir / filename

        try:
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)

            logger.info("Results saved to: %s", results_path)
            return str(results_path)

        except Exception as e:
            logger.error("Failed to save results: %s", e)
            return None

    def _log_hardware_summary(self, results: Dict[str, Any]):
        """Log hardware configuration section of summary.

        Helper for print_summary (#825).
        """
        hardware = results.get("hardware_baseline", {})
        cpu_info = hardware.get("cpu_info", {})
        gpu_info = hardware.get("gpu_info", {})

        logger.info("\nHARDWARE CONFIGURATION:")
        logger.info(
            "   CPU Cores: %s", cpu_info.get('cpu_count_logical', 'Unknown')
        )
        logger.info(
            "   Memory: %s GB", cpu_info.get('memory_total_gb', 'Unknown')
        )
        logger.info(
            "   GPU Available: %s", gpu_info.get('gpu_available', False)
        )
        if gpu_info.get("gpu_available"):
            logger.info(
                "   GPU: %s", gpu_info.get('gpu_name', 'Unknown')
            )
            logger.info(
                "   GPU Memory: %s GB",
                gpu_info.get('gpu_memory_total_gb', 'Unknown'),
            )

    def _log_npu_and_comparison_summary(self, results: Dict[str, Any]):
        """Log NPU status and performance comparison summary.

        Helper for print_summary (#825).
        """
        npu_worker = results.get("npu_worker_tests", {})
        logger.info("\nNPU WORKER STATUS:")
        connectivity = npu_worker.get("connectivity", {})
        logger.info(
            "   Connected: %s", connectivity.get('success', False)
        )
        if connectivity.get("success"):
            health = npu_worker.get("health_check", {})
            logger.info(
                "   NPU Available: %s",
                health.get('npu_available', False),
            )
            logger.info(
                "   Response Time: %.2fms",
                connectivity.get('response_time_ms', 0),
            )

        comparison = results.get("performance_comparison", {})
        logger.info("\nPERFORMANCE COMPARISON:")
        device_perf = comparison.get("device_performance", {})
        if device_perf:
            logger.info(
                "   CPU Embedding: %.2fms",
                device_perf.get('cpu_avg_ms', 0),
            )
            logger.info(
                "   GPU Embedding: %.2fms",
                device_perf.get('gpu_avg_ms', 0),
            )
            logger.info(
                "   NPU Embedding: %.2fms",
                device_perf.get('npu_avg_ms', 0),
            )

        speedup = comparison.get("speedup_analysis", {})
        if speedup:
            logger.info("\nSPEEDUP FACTORS:")
            logger.info(
                "   NPU vs CPU: %.1fx",
                speedup.get('npu_vs_cpu_speedup', 0),
            )
            logger.info(
                "   NPU vs GPU: %.1fx",
                speedup.get('npu_vs_gpu_speedup', 0),
            )
            logger.info(
                "   GPU vs CPU: %.1fx",
                speedup.get('gpu_vs_cpu_speedup', 0),
            )

    def print_summary(self, results: Dict[str, Any]):
        """Print a summary of benchmark results."""
        logger.info("\n" + "=" * 80)
        logger.info("NPU SEMANTIC SEARCH PERFORMANCE BENCHMARK RESULTS")
        logger.info("=" * 80)

        self._log_hardware_summary(results)
        self._log_npu_and_comparison_summary(results)

        recommendations = results.get("recommendations", [])
        logger.info("\nOPTIMIZATION RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations[:5], 1):
            logger.info("   %d. %s", i, rec)

        logger.info("\n" + "=" * 80)


async def main():
    """Main function to run NPU performance measurement."""
    logger.info("Starting AutoBot NPU Performance Measurement")
    logger.info(
        "This will comprehensively test NPU semantic search acceleration"
    )

    measurement = NPUPerformanceMeasurement()

    results = await measurement.run_comprehensive_benchmark()
    measurement.print_summary(results)

    results_file = measurement.save_results(results)
    if results_file:
        logger.info("Detailed results saved to: %s", results_file)

    return results


if __name__ == "__main__":
    asyncio.run(main())
