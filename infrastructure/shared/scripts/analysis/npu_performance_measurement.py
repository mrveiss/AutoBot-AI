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

import aiohttp
import numpy as np

# Add AutoBot to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.ai_hardware_accelerator import HardwareDevice
from src.constants.network_constants import NetworkConstants
from src.npu_semantic_search import get_npu_search_engine
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("npu_performance_measurement")


class NPUPerformanceMeasurement:
    """Comprehensive NPU performance measurement and analysis."""

    def __init__(self):
        self.npu_worker_url = f"http://{NetworkConstants.NPU_WORKER_LINUX_VM_IP}:{NetworkConstants.NPU_WORKER_PORT}"
        self.backend_url = (
            f"http://{NetworkConstants.LOCALHOST_IP}:{NetworkConstants.BACKEND_PORT}"
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
        logger.info("🚀 Starting comprehensive NPU performance measurement")

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
            # 1. Hardware Baseline Measurement
            logger.info("📊 Step 1: Measuring hardware baseline performance")
            benchmark_results[
                "hardware_baseline"
            ] = await self._measure_hardware_baseline()

            # 2. NPU Worker Direct Tests
            logger.info("🔧 Step 2: Testing NPU Worker direct performance")
            benchmark_results["npu_worker_tests"] = await self._test_npu_worker_direct()

            # 3. Semantic Search Engine Tests
            logger.info("🔍 Step 3: Testing semantic search engine performance")
            benchmark_results[
                "semantic_search_tests"
            ] = await self._test_semantic_search_engine()

            # 4. API Endpoint Tests
            logger.info("🌐 Step 4: Testing API endpoint performance")
            benchmark_results["api_endpoint_tests"] = await self._test_api_endpoints()

            # 5. Performance Comparison Analysis
            logger.info("📈 Step 5: Analyzing performance comparisons")
            benchmark_results[
                "performance_comparison"
            ] = await self._analyze_performance_comparison(benchmark_results)

            # 6. Generate Recommendations
            logger.info("💡 Step 6: Generating optimization recommendations")
            benchmark_results["recommendations"] = await self._generate_recommendations(
                benchmark_results
            )

            logger.info("✅ Comprehensive benchmark completed successfully")

        except Exception as e:
            logger.error("❌ Benchmark failed: %s", e)
            benchmark_results["error"] = str(e)

        return benchmark_results

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
            # Get CPU information
            import psutil

            baseline_results["cpu_info"] = {
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

            # Get GPU information
            try:
                import torch

                if torch.cuda.is_available():
                    baseline_results["gpu_info"] = {
                        "gpu_available": True,
                        "gpu_name": torch.cuda.get_device_name(0),
                        "gpu_count": torch.cuda.device_count(),
                        "gpu_memory_total_gb": round(
                            torch.cuda.get_device_properties(0).total_memory
                            / (1024**3),
                            2,
                        ),
                    }

                    # GPU memory usage
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        baseline_results["gpu_info"]["gpu_memory_allocated_gb"] = round(
                            torch.cuda.memory_allocated(0) / (1024**3), 2
                        )
                else:
                    baseline_results["gpu_info"] = {"gpu_available": False}
            except ImportError:
                baseline_results["gpu_info"] = {
                    "gpu_available": False,
                    "torch_not_available": True,
                }

            # Test CPU embedding performance
            baseline_results[
                "cpu_embedding_performance"
            ] = await self._test_cpu_embedding_performance()

            # Test GPU embedding performance if available
            if baseline_results["gpu_info"].get("gpu_available", False):
                baseline_results[
                    "gpu_embedding_performance"
                ] = await self._test_gpu_embedding_performance()

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
            from src.utils.semantic_chunker import get_semantic_chunker

            chunker = get_semantic_chunker()

            # Force CPU-only mode
            original_model = chunker._embedding_model
            chunker._embedding_model = None

            # Test single text embedding
            test_text = (
                "This is a test sentence for CPU embedding performance measurement."
            )

            for i in range(5):
                start_time = time.time()
                chunker._compute_sentence_embeddings([test_text])
                end_time = time.time()

                cpu_results["single_text_times"].append((end_time - start_time) * 1000)

            # Test batch embedding
            batch_sizes = [1, 5, 10, 25, 50]
            for batch_size in batch_sizes:
                batch_texts = [
                    f"Test sentence number {i} for batch processing."
                    for i in range(batch_size)
                ]

                start_time = time.time()
                chunker._compute_sentence_embeddings(batch_texts)
                end_time = time.time()

                cpu_results["batch_times"][str(batch_size)] = {
                    "total_time_ms": (end_time - start_time) * 1000,
                    "per_text_ms": ((end_time - start_time) * 1000) / batch_size,
                }

            # Calculate averages
            cpu_results["average_performance"] = {
                "avg_single_text_ms": np.mean(cpu_results["single_text_times"]),
                "std_single_text_ms": np.std(cpu_results["single_text_times"]),
                "min_single_text_ms": np.min(cpu_results["single_text_times"]),
                "max_single_text_ms": np.max(cpu_results["single_text_times"]),
            }

            # Restore original model
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
            from src.utils.semantic_chunker import get_semantic_chunker

            chunker = get_semantic_chunker()
            await chunker._initialize_model()

            # Test single text embedding with GPU
            test_text = (
                "This is a test sentence for GPU embedding performance measurement."
            )

            for i in range(5):
                start_time = time.time()
                embeddings = await chunker._compute_sentence_embeddings_async(
                    [test_text]
                )
                end_time = time.time()

                gpu_results["single_text_times"].append((end_time - start_time) * 1000)

            # Test batch embedding
            batch_sizes = [1, 5, 10, 25, 50, 100]
            for batch_size in batch_sizes:
                batch_texts = [
                    f"Test sentence number {i} for GPU batch processing."
                    for i in range(batch_size)
                ]

                start_time = time.time()
                embeddings = await chunker._compute_sentence_embeddings_async(
                    batch_texts
                )
                end_time = time.time()

                gpu_results["batch_times"][str(batch_size)] = {
                    "total_time_ms": (end_time - start_time) * 1000,
                    "per_text_ms": ((end_time - start_time) * 1000) / batch_size,
                }

            # Calculate averages
            gpu_results["average_performance"] = {
                "avg_single_text_ms": np.mean(gpu_results["single_text_times"]),
                "std_single_text_ms": np.std(gpu_results["single_text_times"]),
                "min_single_text_ms": np.min(gpu_results["single_text_times"]),
                "max_single_text_ms": np.max(gpu_results["single_text_times"]),
            }

        except Exception as e:
            logger.error("GPU embedding performance test failed: %s", e)
            gpu_results["error"] = str(e)

        return gpu_results

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
            # Test connectivity
            start_time = time.time()
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                try:
                    async with session.get(f"{self.npu_worker_url}/health") as response:
                        if response.status == 200:
                            health_data = await response.json()
                            npu_results["connectivity"] = {
                                "success": True,
                                "response_time_ms": (time.time() - start_time) * 1000,
                                "npu_available": health_data.get(
                                    "npu_available", False
                                ),
                            }
                            npu_results["health_check"] = health_data
                        else:
                            npu_results["connectivity"] = {
                                "success": False,
                                "status_code": response.status,
                                "response_time_ms": (time.time() - start_time) * 1000,
                            }
                except Exception as e:
                    npu_results["connectivity"] = {
                        "success": False,
                        "error": str(e),
                        "response_time_ms": (time.time() - start_time) * 1000,
                    }

                # Test embedding generation if connected
                if npu_results["connectivity"]["success"]:
                    npu_results[
                        "embedding_generation"
                    ] = await self._test_npu_embedding_generation(session)
                    npu_results[
                        "semantic_search"
                    ] = await self._test_npu_semantic_search(session)

        except Exception as e:
            logger.error("NPU Worker direct test failed: %s", e)
            npu_results["error"] = str(e)

        return npu_results

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
            # Test single embedding generation
            test_texts = [
                "NPU embedding generation test",
                "AutoBot semantic search optimization",
                "Intel NPU hardware acceleration",
            ]

            for text in test_texts:
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
                        end_time = time.time()

                        embedding_results["single_embeddings"].append(
                            {
                                "text": text,
                                "processing_time_ms": (end_time - start_time) * 1000,
                                "npu_time_ms": result.get("processing_time_ms", 0),
                                "device_used": result.get("device", "unknown"),
                                "embedding_dimension": len(
                                    result.get("embeddings", [])
                                ),
                                "success": True,
                            }
                        )
                    else:
                        embedding_results["single_embeddings"].append(
                            {
                                "text": text,
                                "error": f"HTTP {response.status}",
                                "success": False,
                            }
                        )

            # Test batch embedding generation
            batch_sizes = [5, 10, 25]
            for batch_size in batch_sizes:
                batch_texts = [f"Batch test sentence {i}" for i in range(batch_size)]

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
                        end_time = time.time()

                        embedding_results["batch_embeddings"][str(batch_size)] = {
                            "total_time_ms": (end_time - start_time) * 1000,
                            "npu_time_ms": result.get("processing_time_ms", 0),
                            "per_text_ms": ((end_time - start_time) * 1000)
                            / batch_size,
                            "device_used": result.get("device", "unknown"),
                            "texts_processed": result.get("texts_processed", 0),
                            "success": True,
                        }
                    else:
                        embedding_results["batch_embeddings"][str(batch_size)] = {
                            "error": f"HTTP {response.status}",
                            "success": False,
                        }

            # Calculate performance metrics
            successful_single = [
                r for r in embedding_results["single_embeddings"] if r["success"]
            ]
            if successful_single:
                times = [r["processing_time_ms"] for r in successful_single]
                embedding_results["performance_metrics"] = {
                    "avg_single_time_ms": np.mean(times),
                    "min_single_time_ms": np.min(times),
                    "max_single_time_ms": np.max(times),
                    "std_single_time_ms": np.std(times),
                    "success_rate": len(successful_single)
                    / len(embedding_results["single_embeddings"])
                    * 100,
                }

        except Exception as e:
            logger.error("NPU embedding generation test failed: %s", e)
            embedding_results["error"] = str(e)

        return embedding_results

    async def _test_npu_semantic_search(
        self, session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """Test NPU Worker semantic search."""
        search_results = {"search_tests": [], "performance_metrics": {}}

        try:
            # Create test documents with embeddings
            test_documents = [
                "Linux system administration and file management",
                "Docker container orchestration and deployment",
                "Python programming and async development",
                "AutoBot configuration and setup procedures",
                "Redis database optimization and management",
            ]

            # Generate embeddings for test documents
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
                    document_embeddings = embedding_result.get("embeddings", [])

                    # Test semantic search with different queries
                    test_queries = [
                        "file operations in linux",
                        "container management",
                        "async python programming",
                    ]

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
                                end_time = time.time()

                                search_results["search_tests"].append(
                                    {
                                        "query": query,
                                        "total_time_ms": (end_time - start_time) * 1000,
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
                                    }
                                )
                            else:
                                search_results["search_tests"].append(
                                    {
                                        "query": query,
                                        "error": f"HTTP {search_response.status}",
                                        "success": False,
                                    }
                                )

                    # Calculate performance metrics
                    successful_searches = [
                        r for r in search_results["search_tests"] if r["success"]
                    ]
                    if successful_searches:
                        times = [r["total_time_ms"] for r in successful_searches]
                        search_results["performance_metrics"] = {
                            "avg_search_time_ms": np.mean(times),
                            "min_search_time_ms": np.min(times),
                            "max_search_time_ms": np.max(times),
                            "success_rate": len(successful_searches)
                            / len(search_results["search_tests"])
                            * 100,
                        }

        except Exception as e:
            logger.error("NPU semantic search test failed: %s", e)
            search_results["error"] = str(e)

        return search_results

    async def _test_semantic_search_engine(self) -> Dict[str, Any]:
        """Test the integrated semantic search engine."""
        engine_results = {
            "initialization": {},
            "search_performance": {},
            "hardware_utilization": {},
            "cache_performance": {},
        }

        try:
            # Test initialization
            start_time = time.time()
            search_engine = await get_npu_search_engine()
            init_time = (time.time() - start_time) * 1000

            engine_results["initialization"] = {
                "init_time_ms": init_time,
                "success": True,
            }

            # Test search performance with different configurations
            search_configs = [
                {"enable_npu": True, "force_device": None},
                {"enable_npu": True, "force_device": "npu"},
                {"enable_npu": True, "force_device": "gpu"},
                {"enable_npu": False, "force_device": "cpu"},
            ]

            engine_results["search_performance"] = {}

            for i, config in enumerate(search_configs):
                config_name = f"config_{i+1}"
                config_results = []

                for query in self.test_queries[:5]:  # Test with first 5 queries
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

                        end_time = time.time()

                        config_results.append(
                            {
                                "query": query,
                                "total_time_ms": (end_time - start_time) * 1000,
                                "results_count": len(results),
                                "device_used": metrics.device_used,
                                "embedding_time_ms": metrics.embedding_generation_time_ms,
                                "search_time_ms": metrics.similarity_computation_time_ms,
                                "success": True,
                            }
                        )

                    except Exception as e:
                        config_results.append(
                            {"query": query, "error": str(e), "success": False}
                        )

                # Calculate averages for this configuration
                successful_results = [r for r in config_results if r["success"]]
                if successful_results:
                    times = [r["total_time_ms"] for r in successful_results]
                    embedding_times = [
                        r["embedding_time_ms"] for r in successful_results
                    ]
                    search_times = [r["search_time_ms"] for r in successful_results]

                    engine_results["search_performance"][config_name] = {
                        "config": config,
                        "avg_total_time_ms": np.mean(times),
                        "avg_embedding_time_ms": np.mean(embedding_times),
                        "avg_search_time_ms": np.mean(search_times),
                        "success_rate": len(successful_results)
                        / len(config_results)
                        * 100,
                        "detailed_results": config_results,
                    }

            # Test hardware utilization
            engine_results[
                "hardware_utilization"
            ] = await search_engine.get_search_statistics()

        except Exception as e:
            logger.error("Semantic search engine test failed: %s", e)
            engine_results["error"] = str(e)

        return engine_results

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
                # Test health check
                start_time = time.time()
                async with session.get(
                    f"{self.backend_url}/api/search/health"
                ) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        api_results["health_check"] = {
                            "success": True,
                            "response_time_ms": (time.time() - start_time) * 1000,
                            "data": health_data,
                        }
                    else:
                        api_results["health_check"] = {
                            "success": False,
                            "status_code": response.status,
                            "response_time_ms": (time.time() - start_time) * 1000,
                        }

                # Test semantic search endpoint
                if api_results["health_check"]["success"]:
                    search_tests = []

                    for query in self.test_queries[:3]:  # Test with first 3 queries
                        start_time = time.time()

                        async with session.post(
                            f"{self.backend_url}/api/search/semantic",
                            json={
                                "query": query,
                                "similarity_top_k": 5,
                                "enable_npu_acceleration": True,
                            },
                        ) as response:
                            if response.status == 200:
                                search_data = await response.json()
                                search_tests.append(
                                    {
                                        "query": query,
                                        "response_time_ms": (time.time() - start_time)
                                        * 1000,
                                        "api_search_time_ms": search_data.get(
                                            "search_time_ms", 0
                                        ),
                                        "results_count": search_data.get(
                                            "total_results", 0
                                        ),
                                        "device_used": search_data.get(
                                            "device_used", "unknown"
                                        ),
                                        "success": True,
                                    }
                                )
                            else:
                                search_tests.append(
                                    {
                                        "query": query,
                                        "error": f"HTTP {response.status}",
                                        "success": False,
                                    }
                                )

                    api_results["semantic_search"] = {
                        "tests": search_tests,
                        "avg_response_time_ms": np.mean(
                            [
                                t["response_time_ms"]
                                for t in search_tests
                                if t["success"]
                            ]
                        )
                        if any(t["success"] for t in search_tests)
                        else 0,
                    }

                    # Test hardware status endpoint
                    start_time = time.time()
                    async with session.get(
                        f"{self.backend_url}/api/search/hardware/status"
                    ) as response:
                        if response.status == 200:
                            hardware_data = await response.json()
                            api_results["hardware_status"] = {
                                "success": True,
                                "response_time_ms": (time.time() - start_time) * 1000,
                                "data": hardware_data,
                            }
                        else:
                            api_results["hardware_status"] = {
                                "success": False,
                                "status_code": response.status,
                            }

        except Exception as e:
            logger.error("API endpoint test failed: %s", e)
            api_results["error"] = str(e)

        return api_results

    async def _analyze_performance_comparison(
        self, benchmark_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze performance comparisons between different configurations."""
        comparison = {
            "device_performance": {},
            "speedup_analysis": {},
            "efficiency_metrics": {},
            "hardware_utilization": {},
        }

        try:
            # Extract performance data from different tests
            hardware_baseline = benchmark_results.get("hardware_baseline", {})
            npu_worker = benchmark_results.get("npu_worker_tests", {})
            semantic_search = benchmark_results.get("semantic_search_tests", {})

            # Device performance comparison
            cpu_perf = hardware_baseline.get("cpu_embedding_performance", {}).get(
                "average_performance", {}
            )
            gpu_perf = hardware_baseline.get("gpu_embedding_performance", {}).get(
                "average_performance", {}
            )
            npu_perf = npu_worker.get("embedding_generation", {}).get(
                "performance_metrics", {}
            )

            if cpu_perf and gpu_perf and npu_perf:
                comparison["device_performance"] = {
                    "cpu_avg_ms": cpu_perf.get("avg_single_text_ms", 0),
                    "gpu_avg_ms": gpu_perf.get("avg_single_text_ms", 0),
                    "npu_avg_ms": npu_perf.get("avg_single_time_ms", 0),
                }

                # Calculate speedup factors
                cpu_time = cpu_perf.get("avg_single_text_ms", 1)
                gpu_time = gpu_perf.get("avg_single_text_ms", 1)
                npu_time = npu_perf.get("avg_single_time_ms", 1)

                comparison["speedup_analysis"] = {
                    "gpu_vs_cpu_speedup": cpu_time / gpu_time if gpu_time > 0 else 0,
                    "npu_vs_cpu_speedup": cpu_time / npu_time if npu_time > 0 else 0,
                    "npu_vs_gpu_speedup": gpu_time / npu_time if npu_time > 0 else 0,
                }

            # Efficiency metrics
            search_performance = semantic_search.get("search_performance", {})
            if search_performance:
                config_times = {}
                for config_name, config_data in search_performance.items():
                    if "avg_total_time_ms" in config_data:
                        config_times[config_name] = config_data["avg_total_time_ms"]

                comparison["efficiency_metrics"] = {
                    "configuration_performance": config_times,
                    "best_configuration": min(
                        config_times.keys(), key=lambda k: config_times[k]
                    )
                    if config_times
                    else None,
                    "worst_configuration": max(
                        config_times.keys(), key=lambda k: config_times[k]
                    )
                    if config_times
                    else None,
                }

            # Hardware utilization analysis
            hardware_info = hardware_baseline.get("cpu_info", {})
            gpu_info = hardware_baseline.get("gpu_info", {})

            comparison["hardware_utilization"] = {
                "cpu_cores_available": hardware_info.get("cpu_count_logical", 0),
                "cpu_utilization_during_test": hardware_info.get("cpu_percent", 0),
                "gpu_available": gpu_info.get("gpu_available", False),
                "gpu_memory_total_gb": gpu_info.get("gpu_memory_total_gb", 0),
                "npu_worker_available": npu_worker.get("connectivity", {}).get(
                    "success", False
                ),
                "npu_available": npu_worker.get("health_check", {}).get(
                    "npu_available", False
                ),
            }

        except Exception as e:
            logger.error("Performance comparison analysis failed: %s", e)
            comparison["error"] = str(e)

        return comparison

    async def _generate_recommendations(
        self, benchmark_results: Dict[str, Any]
    ) -> List[str]:
        """Generate optimization recommendations based on benchmark results."""
        recommendations = []

        try:
            comparison = benchmark_results.get("performance_comparison", {})
            npu_worker = benchmark_results.get("npu_worker_tests", {})
            benchmark_results.get("hardware_baseline", {})

            # NPU availability recommendations
            npu_available = npu_worker.get("health_check", {}).get(
                "npu_available", False
            )
            npu_connected = npu_worker.get("connectivity", {}).get("success", False)

            if not npu_connected:
                recommendations.append(
                    "CRITICAL: NPU Worker not accessible - verify VM2 (172.16.168.22) is running and NPU Worker service is started"
                )
            elif not npu_available:
                recommendations.append(
                    "NPU hardware not available - install Intel NPU drivers and OpenVINO for optimal performance"
                )
            else:
                recommendations.append(
                    "✅ NPU Worker is operational - NPU acceleration is available"
                )

            # Performance optimization recommendations
            speedup = comparison.get("speedup_analysis", {})
            if speedup:
                npu_vs_cpu = speedup.get("npu_vs_cpu_speedup", 0)
                npu_vs_gpu = speedup.get("npu_vs_gpu_speedup", 0)

                if npu_vs_cpu > 5:
                    recommendations.append(
                        f"Excellent NPU performance: {npu_vs_cpu:.1f}x faster than CPU - route lightweight tasks to NPU"
                    )
                elif npu_vs_cpu > 2:
                    recommendations.append(
                        f"Good NPU performance: {npu_vs_cpu:.1f}x faster than CPU - optimize NPU utilization"
                    )
                elif npu_vs_cpu < 1:
                    recommendations.append(
                        "NPU performance suboptimal - check NPU optimization settings and model quantization"
                    )

                if npu_vs_gpu > 1.5:
                    recommendations.append(
                        f"NPU outperforms GPU for embedding tasks ({npu_vs_gpu:.1f}x) - prioritize NPU for semantic search"
                    )
                elif npu_vs_gpu < 0.7:
                    recommendations.append(
                        "GPU outperforms NPU for these tasks - consider GPU-first routing strategy"
                    )

            # Hardware utilization recommendations
            hardware_util = comparison.get("hardware_utilization", {})
            if hardware_util:
                cpu_cores = hardware_util.get("cpu_cores_available", 0)
                gpu_available = hardware_util.get("gpu_available", False)

                if cpu_cores >= 16:
                    recommendations.append(
                        f"High-core CPU detected ({cpu_cores} cores) - optimize parallel processing and batch sizes"
                    )

                if gpu_available:
                    gpu_memory = hardware_util.get("gpu_memory_total_gb", 0)
                    if gpu_memory >= 8:
                        recommendations.append(
                            f"High-memory GPU available ({gpu_memory}GB) - optimize for large batch processing"
                        )

            # Configuration recommendations
            efficiency = comparison.get("efficiency_metrics", {})
            if efficiency:
                best_config = efficiency.get("best_configuration")
                if best_config:
                    recommendations.append(
                        f"Optimal configuration identified: {best_config} - use this for production workloads"
                    )

            # General recommendations
            if len(recommendations) == 0:
                recommendations.append(
                    "System performance analysis incomplete - run full benchmark for detailed recommendations"
                )

            recommendations.append(
                "Monitor hardware utilization during production workloads for ongoing optimization"
            )
            recommendations.append(
                "Consider workload-specific optimization (latency vs throughput vs quality)"
            )

        except Exception as e:
            logger.error("Recommendation generation failed: %s", e)
            recommendations.append(f"Recommendation generation failed: {e}")

        return recommendations

    def save_results(self, results: Dict[str, Any], filename: str = None):
        """Save benchmark results to file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"npu_performance_results_{timestamp}.json"

        results_dir = Path(__file__).parent.parent.parent / "reports" / "performance"
        results_dir.mkdir(parents=True, exist_ok=True)

        results_path = results_dir / filename

        try:
            with open(results_path, "w") as f:
                json.dump(results, f, indent=2, default=str)

            logger.info("✅ Results saved to: %s", results_path)
            return str(results_path)

        except Exception as e:
            logger.error("Failed to save results: %s", e)
            return None

    def print_summary(self, results: Dict[str, Any]):
        """Print a summary of benchmark results."""
        print("\n" + "=" * 80)
        print("NPU SEMANTIC SEARCH PERFORMANCE BENCHMARK RESULTS")
        print("=" * 80)

        # Hardware baseline
        hardware = results.get("hardware_baseline", {})
        print("\n🖥️  HARDWARE CONFIGURATION:")
        cpu_info = hardware.get("cpu_info", {})
        gpu_info = hardware.get("gpu_info", {})

        print(f"   CPU Cores: {cpu_info.get('cpu_count_logical', 'Unknown')}")
        print(f"   Memory: {cpu_info.get('memory_total_gb', 'Unknown')} GB")
        print(f"   GPU Available: {gpu_info.get('gpu_available', False)}")
        if gpu_info.get("gpu_available"):
            print(f"   GPU: {gpu_info.get('gpu_name', 'Unknown')}")
            print(f"   GPU Memory: {gpu_info.get('gpu_memory_total_gb', 'Unknown')} GB")

        # NPU Worker status
        npu_worker = results.get("npu_worker_tests", {})
        print("\n🔧 NPU WORKER STATUS:")
        connectivity = npu_worker.get("connectivity", {})
        print(f"   Connected: {connectivity.get('success', False)}")
        if connectivity.get("success"):
            health = npu_worker.get("health_check", {})
            print(f"   NPU Available: {health.get('npu_available', False)}")
            print(f"   Response Time: {connectivity.get('response_time_ms', 0):.2f}ms")

        # Performance comparison
        comparison = results.get("performance_comparison", {})
        print("\n📊 PERFORMANCE COMPARISON:")
        device_perf = comparison.get("device_performance", {})
        if device_perf:
            print(f"   CPU Embedding: {device_perf.get('cpu_avg_ms', 0):.2f}ms")
            print(f"   GPU Embedding: {device_perf.get('gpu_avg_ms', 0):.2f}ms")
            print(f"   NPU Embedding: {device_perf.get('npu_avg_ms', 0):.2f}ms")

        speedup = comparison.get("speedup_analysis", {})
        if speedup:
            print("\n🚀 SPEEDUP FACTORS:")
            print(f"   NPU vs CPU: {speedup.get('npu_vs_cpu_speedup', 0):.1f}x")
            print(f"   NPU vs GPU: {speedup.get('npu_vs_gpu_speedup', 0):.1f}x")
            print(f"   GPU vs CPU: {speedup.get('gpu_vs_cpu_speedup', 0):.1f}x")

        # Recommendations
        recommendations = results.get("recommendations", [])
        print("\n💡 OPTIMIZATION RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"   {i}. {rec}")

        print("\n" + "=" * 80)


async def main():
    """Main function to run NPU performance measurement."""
    print("🚀 Starting AutoBot NPU Performance Measurement")
    print("This will comprehensively test NPU semantic search acceleration")
    print()

    measurement = NPUPerformanceMeasurement()

    # Run comprehensive benchmark
    results = await measurement.run_comprehensive_benchmark()

    # Print summary
    measurement.print_summary(results)

    # Save results
    results_file = measurement.save_results(results)
    if results_file:
        print(f"\n📁 Detailed results saved to: {results_file}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
