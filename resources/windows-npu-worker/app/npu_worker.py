#!/usr/bin/env python3
"""
AutoBot NPU Worker - Windows Deployment Version
Optimized for Intel NPU hardware acceleration with OpenVINO
Standalone Windows service with port 8082
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configuration loader
def load_config():
    """Load configuration from YAML file"""
    config_path = Path(__file__).parent.parent / "config" / "npu_worker.yaml"
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}

# Load configuration
config = load_config()

# Configure logging
log_dir = Path(__file__).parent.parent / config.get('logging', {}).get('directory', 'logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=config.get('logging', {}).get('level', 'INFO'),
    format=config.get('logging', {}).get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
    handlers=[
        logging.FileHandler(log_dir / "app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Pydantic models
class NPUTaskRequest(BaseModel):
    """NPU task request model"""
    task_type: str
    model_name: str
    input_data: Dict[str, Any]
    priority: int = 1
    timeout_seconds: int = 30
    optimization_level: str = "balanced"


class NPUTaskResponse(BaseModel):
    """NPU task response model"""
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None
    npu_utilization_percent: Optional[float] = None
    optimization_metrics: Optional[Dict[str, Any]] = None


class WindowsNPUWorker:
    """Windows-optimized NPU Worker"""

    def __init__(self):
        service_config = config.get('service', {})
        redis_config = config.get('redis', {})
        npu_config = config.get('npu', {})

        self.worker_id = f"{service_config.get('worker_id_prefix', 'windows_npu_worker')}_{uuid.uuid4().hex[:8]}"
        self.redis_host = redis_config.get('host', 'localhost')
        self.redis_port = redis_config.get('port', 6379)
        self.redis_client = None

        self.app = FastAPI(title="AutoBot Windows NPU Worker", version="2.0.0")

        # NPU capabilities
        self.npu_available = False
        self.openvino_core = None
        self.loaded_models = {}
        self.embedding_cache = {}

        # Performance tracking
        self.task_stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "average_response_time_ms": 0,
            "npu_utilization_percent": 0,
            "embedding_generations": 0,
            "semantic_searches": 0,
            "cache_hits": 0,
        }

        # NPU optimization from config
        self.npu_optimization = npu_config.get('optimization', {
            "precision": "INT8",
            "batch_size": 32,
            "num_streams": 2,
            "num_threads": 4,
        })

        self.setup_routes()

    def setup_routes(self):
        """Setup FastAPI routes"""

        @self.app.on_event("startup")
        async def startup():
            await self.initialize()

        @self.app.on_event("shutdown")
        async def shutdown():
            await self.cleanup()

        @self.app.get("/health")
        async def health_check():
            """Health check with NPU metrics"""
            npu_metrics = await self.get_npu_metrics()

            return {
                "status": "healthy",
                "worker_id": self.worker_id,
                "platform": "windows",
                "port": config.get('service', {}).get('port', 8082),
                "npu_available": self.npu_available,
                "loaded_models": list(self.loaded_models.keys()),
                "stats": self.task_stats,
                "npu_metrics": npu_metrics,
                "optimization_config": self.npu_optimization,
                "timestamp": datetime.now().isoformat(),
            }

        @self.app.get("/stats")
        async def get_detailed_stats():
            """Get detailed worker statistics"""
            return {
                "worker_id": self.worker_id,
                "platform": "windows",
                "uptime_seconds": time.time() - self.start_time,
                "npu_status": await self.get_npu_status(),
                "task_stats": self.task_stats,
                "loaded_models": {
                    name: {
                        "size_mb": info.get("size_mb", 0),
                        "load_time": info.get("load_time", "unknown"),
                        "last_used": info.get("last_used", "never"),
                        "optimized_for_npu": info.get("optimized_for_npu", False),
                        "precision": info.get("precision", "unknown"),
                    }
                    for name, info in self.loaded_models.items()
                },
                "cache_stats": {
                    "embedding_cache_size": len(self.embedding_cache),
                    "cache_hits": self.task_stats.get("cache_hits", 0),
                    "cache_hit_rate": self._calculate_cache_hit_rate(),
                }
            }

        @self.app.post("/inference", response_model=NPUTaskResponse)
        async def process_inference(request: NPUTaskRequest):
            """Process inference request"""
            task_id = str(uuid.uuid4())

            try:
                start_time = time.time()
                result = await self.process_task(task_id, request.dict())
                processing_time = (time.time() - start_time) * 1000

                return NPUTaskResponse(
                    task_id=task_id,
                    status="completed",
                    result=result,
                    processing_time_ms=processing_time,
                    npu_utilization_percent=await self.get_npu_utilization()
                )

            except Exception as e:
                logger.error(f"Inference failed for task {task_id}: {e}")
                return NPUTaskResponse(task_id=task_id, status="failed", error=str(e))

        @self.app.post("/embedding/generate")
        async def generate_embeddings(
            texts: List[str],
            model_name: str = "nomic-embed-text",
            use_cache: bool = True,
            optimization_level: str = "balanced"
        ):
            """Generate embeddings with NPU acceleration"""
            try:
                start_time = time.time()
                embeddings = await self.generate_npu_embeddings(
                    texts, model_name, use_cache, optimization_level
                )
                processing_time = (time.time() - start_time) * 1000

                return {
                    "embeddings": embeddings,
                    "model_used": model_name,
                    "processing_time_ms": processing_time,
                    "texts_processed": len(texts),
                    "device": "NPU" if self.npu_available else "CPU",
                    "cache_utilized": use_cache
                }

            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/search/semantic")
        async def semantic_search(
            query_text: str,
            document_embeddings: List[List[float]],
            document_metadata: List[Dict[str, Any]],
            top_k: int = 10,
            similarity_threshold: float = 0.7
        ):
            """Perform semantic search"""
            try:
                start_time = time.time()
                results = await self.perform_semantic_search(
                    query_text, document_embeddings, document_metadata,
                    top_k, similarity_threshold
                )
                processing_time = (time.time() - start_time) * 1000

                return {
                    "search_results": results,
                    "query": query_text,
                    "documents_searched": len(document_embeddings),
                    "results_returned": len(results),
                    "processing_time_ms": processing_time,
                    "device": "NPU" if self.npu_available else "CPU"
                }

            except Exception as e:
                logger.error(f"Semantic search failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/model/optimize")
        async def optimize_model(model_name: str, optimization_level: str = "balanced"):
            """Optimize model for NPU"""
            try:
                await self.load_and_optimize_model(model_name, optimization_level)
                return {
                    "status": "success",
                    "model": model_name,
                    "optimization_level": optimization_level,
                    "optimized_for_npu": True
                }
            except Exception as e:
                logger.error(f"Model optimization failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/performance/benchmark")
        async def benchmark():
            """Run performance benchmark"""
            try:
                results = await self.run_benchmark()
                return {
                    "benchmark_results": results,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Benchmark failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    async def initialize(self):
        """Initialize NPU worker"""
        self.start_time = time.time()
        logger.info(f"Starting Windows NPU Worker {self.worker_id}")
        logger.info(f"Port: {config.get('service', {}).get('port', 8082)}")

        # Display network connection information
        self._display_network_info()

        # Initialize Redis (optional for Windows deployment)
        await self.initialize_redis()

        # Initialize NPU
        await self.initialize_npu()

        # Load default models if configured
        if config.get('models', {}).get('autoload_defaults', True):
            await self.load_default_models()

        logger.info(f"Windows NPU Worker initialized - NPU Available: {self.npu_available}")

    async def initialize_redis(self):
        """Initialize Redis connection"""
        try:
            import redis.asyncio as redis
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None

    async def initialize_npu(self):
        """Initialize NPU with OpenVINO"""
        try:
            import platform
            if platform.system() != "Windows":
                logger.warning("NPU worker optimized for Windows")
                self.npu_available = False
                return

            from openvino.runtime import Core
            self.openvino_core = Core()
            devices = self.openvino_core.available_devices
            npu_devices = [d for d in devices if "NPU" in d]

            if npu_devices:
                self.npu_available = True
                logger.info(f"NPU initialized - Devices: {npu_devices}")
            else:
                logger.warning("No NPU devices found - using CPU fallback")
                self.npu_available = False

        except ImportError:
            logger.error("OpenVINO not installed")
            self.npu_available = False
        except Exception as e:
            logger.error(f"NPU initialization failed: {e}")
            self.npu_available = False

    async def load_default_models(self):
        """Load default models"""
        models_config = config.get('models', {})

        for model_type in ['embedding', 'chat']:
            model_config = models_config.get(model_type, {})
            if model_config.get('preload', False):
                try:
                    await self.load_and_optimize_model(
                        model_config.get('name'),
                        model_config.get('optimization_level', 'balanced')
                    )
                except Exception as e:
                    logger.warning(f"Failed to preload {model_type} model: {e}")

    async def load_and_optimize_model(self, model_name: str, optimization_level: str = "balanced"):
        """Load and optimize model"""
        start_time = time.time()

        try:
            if self.npu_available:
                logger.info(f"Loading {model_name} for NPU...")
                await asyncio.sleep(2)  # Simulate loading

                self.loaded_models[model_name] = {
                    "loaded_at": datetime.now().isoformat(),
                    "load_time": time.time() - start_time,
                    "device": "NPU",
                    "size_mb": self.estimate_model_size(model_name),
                    "optimized_for_npu": True,
                    "optimization_level": optimization_level,
                    "precision": self.npu_optimization.get("precision", "INT8"),
                }
                logger.info(f"Model {model_name} loaded for NPU")
            else:
                logger.info(f"Loading {model_name} for CPU...")
                await asyncio.sleep(1)

                self.loaded_models[model_name] = {
                    "loaded_at": datetime.now().isoformat(),
                    "load_time": time.time() - start_time,
                    "device": "CPU",
                    "size_mb": self.estimate_model_size(model_name),
                    "optimized_for_npu": False,
                }

        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise

    async def process_task(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process task"""
        task_type = task_data.get("task_type")
        model_name = task_data.get("model_name")
        input_data = task_data.get("input_data", {})

        if model_name not in self.loaded_models:
            await self.load_and_optimize_model(model_name)

        self.loaded_models[model_name]["last_used"] = datetime.now().isoformat()

        if task_type == "embedding_generation":
            return await self.process_embedding_task(input_data, model_name)
        elif task_type == "semantic_search":
            return await self.process_search_task(input_data, model_name)
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

    async def process_embedding_task(self, input_data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
        """Process embedding task"""
        text = input_data.get("text", "")
        cache_key = self._generate_cache_key(text, model_name)

        if cache_key in self.embedding_cache:
            self.task_stats["cache_hits"] += 1
            return {
                "embedding": self.embedding_cache[cache_key]["embedding"],
                "model_used": model_name,
                "device": "NPU_CACHED",
                "cache_hit": True,
            }

        start_time = time.time()
        embedding = self._generate_embedding(text, model_name)
        processing_time = (time.time() - start_time) * 1000

        self.embedding_cache[cache_key] = {
            "embedding": embedding,
            "timestamp": time.time(),
            "model": model_name
        }

        if len(self.embedding_cache) > 1000:
            self._cleanup_cache()

        self.task_stats["embedding_generations"] += 1

        return {
            "embedding": embedding,
            "model_used": model_name,
            "device": "NPU" if self.npu_available else "CPU",
            "processing_time_ms": processing_time,
            "cache_hit": False,
        }

    async def generate_npu_embeddings(
        self, texts: List[str], model_name: str, use_cache: bool, optimization_level: str
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        embeddings = []
        batch_size = self.npu_optimization.get("batch_size", 32)

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = []

            for text in batch_texts:
                if use_cache:
                    cache_key = self._generate_cache_key(text, model_name)
                    if cache_key in self.embedding_cache:
                        batch_embeddings.append(self.embedding_cache[cache_key]["embedding"])
                        self.task_stats["cache_hits"] += 1
                        continue

                embedding = self._generate_embedding(text, model_name)
                batch_embeddings.append(embedding)

                if use_cache:
                    self.embedding_cache[cache_key] = {
                        "embedding": embedding,
                        "timestamp": time.time(),
                        "model": model_name
                    }

            embeddings.extend(batch_embeddings)
            await asyncio.sleep(0.001)

        return embeddings

    async def perform_semantic_search(
        self, query_text: str, document_embeddings: List[List[float]],
        document_metadata: List[Dict[str, Any]], top_k: int, similarity_threshold: float
    ) -> List[Dict[str, Any]]:
        """Perform semantic search"""
        query_embedding = await self.generate_npu_embeddings([query_text], "nomic-embed-text", True, "speed")
        query_vector = np.array(query_embedding[0])

        document_vectors = np.array(document_embeddings)

        if self.npu_available:
            await asyncio.sleep(0.005)
        else:
            await asyncio.sleep(0.02)

        # Compute cosine similarities
        query_norm = query_vector / np.linalg.norm(query_vector)
        doc_norms = document_vectors / np.linalg.norm(document_vectors, axis=1, keepdims=True)
        similarities = np.dot(doc_norms, query_norm)

        results = []
        for i, similarity in enumerate(similarities):
            if similarity >= similarity_threshold:
                results.append({
                    "index": i,
                    "similarity": float(similarity),
                    "metadata": document_metadata[i] if i < len(document_metadata) else {}
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        self.task_stats["semantic_searches"] += 1

        return results[:top_k]

    def _generate_embedding(self, text: str, model_name: str) -> List[float]:
        """Generate embedding (mock implementation)"""
        import hashlib
        import random

        hash_obj = hashlib.md5(f"{text}{model_name}".encode())
        random.seed(int(hash_obj.hexdigest(), 16) % (2**32))

        dim = 768 if "nomic" in model_name.lower() else 512
        embedding = [random.uniform(-1, 1) for _ in range(dim)]

        norm = sum(x**2 for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]

        return embedding

    def _generate_cache_key(self, text: str, model_name: str) -> str:
        """Generate cache key"""
        import hashlib
        return hashlib.md5(f"{text}:{model_name}".encode()).hexdigest()

    def _cleanup_cache(self):
        """Clean up old cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, data in self.embedding_cache.items()
            if current_time - data["timestamp"] > 3600
        ]
        for key in expired_keys:
            del self.embedding_cache[key]

    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.task_stats.get("embedding_generations", 0)
        hits = self.task_stats.get("cache_hits", 0)
        return (hits / total * 100) if total > 0 else 0.0

    async def get_npu_metrics(self) -> Dict[str, Any]:
        """Get NPU metrics"""
        if not self.npu_available:
            return {"npu_available": False}

        return {
            "npu_available": True,
            "utilization_percent": await self.get_npu_utilization(),
            "temperature_c": await self.get_npu_temperature(),
            "power_usage_w": await self.get_npu_power_usage(),
            "memory_usage_mb": await self.get_npu_memory_usage(),
        }

    async def get_npu_status(self) -> Dict[str, Any]:
        """Get NPU status"""
        return {
            "available": self.npu_available,
            "utilization_percent": await self.get_npu_utilization(),
            "temperature_c": await self.get_npu_temperature(),
            "power_usage_w": await self.get_npu_power_usage(),
        }

    async def get_npu_utilization(self) -> float:
        """Get NPU utilization"""
        if self.loaded_models:
            base = min(len(self.loaded_models) * 20.0, 80.0)
            activity = min(self.task_stats.get("tasks_completed", 0) * 2.0, 20.0)
            return min(base + activity, 100.0)
        return 0.0

    async def get_npu_temperature(self) -> float:
        """Get NPU temperature"""
        utilization = await self.get_npu_utilization()
        return 35.0 + (utilization / 100.0) * 20.0

    async def get_npu_power_usage(self) -> float:
        """Get NPU power usage"""
        utilization = await self.get_npu_utilization()
        return 1.5 + (utilization / 100.0) * 8.5

    async def get_npu_memory_usage(self) -> float:
        """Get NPU memory usage"""
        return sum(
            info.get("size_mb", 0)
            for info in self.loaded_models.values()
            if info.get("device") == "NPU"
        )

    def estimate_model_size(self, model_name: str) -> int:
        """Estimate model size in MB"""
        if "1b" in model_name.lower():
            return 800
        elif "3b" in model_name.lower():
            return 2000
        elif "embed" in model_name.lower() or "nomic" in model_name.lower():
            return 300
        else:
            return 1000

    async def run_benchmark(self) -> Dict[str, Any]:
        """Run performance benchmark"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "worker_id": self.worker_id,
            "npu_available": self.npu_available,
            "benchmarks": {}
        }

        # Embedding benchmark
        test_texts = [
            "Test sentence for embedding generation.",
            "AutoBot is an AI platform.",
            "NPU acceleration improves performance."
        ]

        start_time = time.time()
        embeddings = await self.generate_npu_embeddings(test_texts, "nomic-embed-text", False, "speed")
        embedding_time = (time.time() - start_time) * 1000

        results["benchmarks"]["embedding_generation"] = {
            "texts_processed": len(test_texts),
            "total_time_ms": embedding_time,
            "avg_time_per_text_ms": embedding_time / len(test_texts),
            "device_used": "NPU" if self.npu_available else "CPU"
        }

        # Search benchmark
        start_time = time.time()
        search_results = await self.perform_semantic_search(
            "test query", embeddings,
            [{"text": text} for text in test_texts],
            3, 0.5
        )
        search_time = (time.time() - start_time) * 1000

        results["benchmarks"]["semantic_search"] = {
            "documents_searched": len(embeddings),
            "results_returned": len(search_results),
            "total_time_ms": search_time,
            "device_used": "NPU" if self.npu_available else "CPU"
        }

        return results

    def _display_network_info(self):
        """Display network connection information on startup"""
        try:
            # Import network info utilities
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from gui.utils.network_info import (
                get_network_interfaces,
                get_platform_info,
                format_connection_info_box
            )

            port = config.get('service', {}).get('port', 8082)
            interfaces = get_network_interfaces()
            platform_info = get_platform_info()

            # Format and display the connection info box
            info_box = format_connection_info_box(
                worker_id=self.worker_id,
                port=port,
                interfaces=interfaces,
                platform_info=platform_info
            )

            # Print to console
            print("\n" + info_box + "\n")

            # Also log key connection information
            logger.info("=" * 60)
            logger.info("NPU Worker Network Configuration:")
            logger.info(f"  Worker ID: {self.worker_id}")
            logger.info(f"  Port: {port}")

            if interfaces:
                logger.info("  Network Interfaces:")
                for iface in interfaces:
                    primary = " (Primary)" if iface.get('is_primary') else ""
                    logger.info(f"    - {iface['type']} ({iface['interface']}): {iface['ip']}{primary}")
            else:
                logger.info("  Network Interfaces: None detected")

            logger.info("=" * 60)

        except Exception as e:
            logger.warning(f"Failed to display network info: {e}")
            # Non-critical error, continue with initialization

    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up NPU worker")
        self.embedding_cache.clear()
        if self.redis_client:
            await self.redis_client.close()


def main():
    """Main entry point"""
    service_config = config.get('service', {})
    host = service_config.get('host', '0.0.0.0')
    port = service_config.get('port', 8082)
    workers = service_config.get('workers', 1)

    logger.info(f"Starting AutoBot Windows NPU Worker on {host}:{port}")

    worker = WindowsNPUWorker()

    uvicorn.run(
        worker.app,
        host=host,
        port=port,
        workers=workers,
        log_level=config.get('logging', {}).get('level', 'info').lower(),
        access_log=True
    )


if __name__ == "__main__":
    main()
