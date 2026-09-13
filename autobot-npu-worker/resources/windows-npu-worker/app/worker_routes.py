# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The worker's HTTP surface, minus pairing (#2346, #15642).

Route registration and the handlers behind it: lifecycle events, health and
status, device info, inference, embeddings, semantic search and the model
routes. Pairing has its own module because it owns persisted state; this one
only reads the worker it is mixed into.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from api_schemas import NPUTaskRequest, NPUTaskResponse
from fastapi import HTTPException
from worker_settings import DEFAULT_PORT, DEFAULT_SEMANTIC_SEARCH_TOP_K, config

logger = logging.getLogger(__name__)


class WorkerRoutesMixin:
    """Route registration and handlers for :class:`WindowsNPUWorker`."""

    def setup_routes(self):
        """Register all API routes. Issue #2346: decomposed from monolithic method."""
        self._register_lifecycle_events()
        self._register_health_routes()
        self._register_pairing_routes()
        self._register_device_routes()
        self._register_inference_routes()
        self._register_model_routes()

    def _register_lifecycle_events(self):
        """Register FastAPI startup and shutdown event handlers."""

        @self.app.on_event("startup")
        async def startup():
            await self.initialize()

        @self.app.on_event("shutdown")
        async def shutdown():
            await self.cleanup()

    def _register_health_routes(self):
        """Register /health and /stats routes."""

        @self.app.get("/health")
        async def health_check():
            """Health check with NPU metrics"""
            npu_metrics = await self.get_npu_metrics()
            stats = await self.task_stats.get_all()

            return {
                "status": "healthy",
                "worker_id": self.worker_id,
                "platform": "windows",
                "port": config.get("service", {}).get("port", DEFAULT_PORT),
                "npu_available": self.npu_available,
                "loaded_models": list(self.loaded_models.keys()),
                "stats": stats,
                "npu_metrics": npu_metrics,
                "optimization_config": self.npu_optimization,
                "timestamp": datetime.now().isoformat(),
                "paired": self.pairing_status.get("paired", False),
            }

        @self.app.get("/stats")
        async def get_detailed_stats():
            """Get detailed worker statistics"""
            stats = await self.task_stats.get_all()
            cache_size = await self.embedding_cache.size()
            cache_hits = await self.task_stats.get("cache_hits")

            return {
                "worker_id": self.worker_id,
                "platform": "windows",
                "uptime_seconds": time.time() - self.start_time,
                "npu_status": await self.get_npu_status(),
                "task_stats": stats,
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
                    "embedding_cache_size": cache_size,
                    "cache_hits": cache_hits,
                    "cache_hit_rate": await self._calculate_cache_hit_rate(),
                },
            }

    def _register_device_routes(self):
        """Register /device-info route (Issue #640)."""

        @self.app.get("/device-info")
        async def device_info():
            """
            Get detailed device information including NPU/GPU/CPU status.

            Issue #640: Shows which device is being used for inference.
            Uses ONNX Runtime + OpenVINO EP for proper Intel NPU support.
            """
            info = {
                "worker_id": self.worker_id,
                "npu_available": self.npu_available,
                "real_inference_enabled": self._use_real_inference,
                "backend": "ONNX Runtime + OpenVINO EP",
                "device_priority": [
                    "OpenVINOExecutionProvider (NPU)",
                    "OpenVINOExecutionProvider (GPU)",
                    "DmlExecutionProvider",
                    "CPUExecutionProvider",
                ],
            }

            if self._model_manager is not None:
                try:
                    manager_info = self._model_manager.get_device_info()
                    info["model_manager"] = manager_info
                    info["selected_device"] = manager_info.get("selected_device", "UNKNOWN")
                    info["available_providers"] = manager_info.get("available_providers", [])
                    info["directml_available"] = manager_info.get("directml_available", False)
                except Exception as e:
                    logger.error("Error getting model manager device info: %s", e)
                    info["model_manager_error"] = "Failed to retrieve model manager info"
            else:
                info["model_manager"] = None
                info["selected_device"] = "MOCK (no model manager)"

            # Add loaded models with their device info
            info["loaded_models"] = {
                name: {
                    "device": model_info.get("device", "UNKNOWN"),
                    "real_inference": model_info.get("real_inference", False),
                    "optimized_for_npu": model_info.get("optimized_for_npu", False),
                    "backend": model_info.get("backend", "Unknown"),
                }
                for name, model_info in self.loaded_models.items()
            }

            return info

    def _register_inference_routes(self):
        """Register /inference, /embedding/generate, and /search/semantic routes."""

        @self.app.post("/inference", response_model=NPUTaskResponse)
        async def process_inference(request: NPUTaskRequest):
            """Process inference request"""
            return await self._handle_inference(request)

        @self.app.post("/embedding/generate")
        async def generate_embeddings(
            texts: List[str],
            model_name: str = "nomic-embed-text",
            use_cache: bool = True,
            optimization_level: str = "balanced",
        ):
            """Generate embeddings with NPU acceleration"""
            return await self._handle_embedding_generate(texts, model_name, use_cache, optimization_level)

        @self.app.post("/search/semantic")
        async def semantic_search(
            query_text: str,
            document_embeddings: List[List[float]],
            document_metadata: List[Dict[str, Any]],
            top_k: int = DEFAULT_SEMANTIC_SEARCH_TOP_K,
            similarity_threshold: float = 0.7,
        ):
            """Perform semantic search"""
            return await self._handle_semantic_search(
                query_text,
                document_embeddings,
                document_metadata,
                top_k,
                similarity_threshold,
            )

    async def _handle_inference(self, request: NPUTaskRequest) -> NPUTaskResponse:
        """
        Handle POST /inference — run a model inference task.

        Args:
            request: NPUTaskRequest with task_type, model_name, and input_data.

        Returns:
            NPUTaskResponse with result or error.
        """
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
                npu_utilization_percent=await self.get_npu_utilization(),
            )
        except Exception as e:
            logger.error(f"Inference failed for task {task_id}: {e}")
            return NPUTaskResponse(task_id=task_id, status="failed", error=str(e))

    async def _handle_embedding_generate(
        self,
        texts: List[str],
        model_name: str,
        use_cache: bool,
        optimization_level: str,
    ) -> Dict[str, Any]:
        """
        Handle POST /embedding/generate — generate embeddings with NPU acceleration.

        Issue #640: Returns real inference status alongside embeddings.
        """
        try:
            start_time = time.time()
            embeddings = await self.generate_npu_embeddings(texts, model_name, use_cache, optimization_level)
            processing_time = (time.time() - start_time) * 1000

            model_info = self.loaded_models.get(model_name, {})
            device = model_info.get("device", "NPU" if self.npu_available else "CPU")
            real_inference = model_info.get("real_inference", False)

            return {
                "embeddings": embeddings,
                "model_used": model_name,
                "processing_time_ms": processing_time,
                "texts_processed": len(texts),
                "device": device,
                "real_inference": real_inference,
                "cache_utilized": use_cache,
            }
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise HTTPException(status_code=500, detail="Embedding generation failed")

    async def _handle_semantic_search(
        self,
        query_text: str,
        document_embeddings: List[List[float]],
        document_metadata: List[Dict[str, Any]],
        top_k: int,
        similarity_threshold: float,
    ) -> Dict[str, Any]:
        """Handle POST /search/semantic — perform semantic similarity search."""
        try:
            start_time = time.time()
            results = await self.perform_semantic_search(
                query_text,
                document_embeddings,
                document_metadata,
                top_k,
                similarity_threshold,
            )
            processing_time = (time.time() - start_time) * 1000

            return {
                "search_results": results,
                "query": query_text,
                "documents_searched": len(document_embeddings),
                "results_returned": len(results),
                "processing_time_ms": processing_time,
                "device": "NPU" if self.npu_available else "CPU",
            }
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            raise HTTPException(status_code=500, detail="Semantic search failed")

    def _register_model_routes(self):
        """Register /model/optimize and /performance/benchmark routes."""

        @self.app.post("/model/optimize")
        async def optimize_model(model_name: str, optimization_level: str = "balanced"):
            """Optimize model for NPU"""
            try:
                await self.load_and_optimize_model(model_name, optimization_level)
                return {
                    "status": "success",
                    "model": model_name,
                    "optimization_level": optimization_level,
                    "optimized_for_npu": True,
                }
            except Exception as e:
                logger.error(f"Model optimization failed: {e}")
                raise HTTPException(status_code=500, detail="Model optimization failed")

        @self.app.get("/performance/benchmark")
        async def benchmark():
            """Run performance benchmark"""
            try:
                results = await self.run_benchmark()
                return {
                    "benchmark_results": results,
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"Benchmark failed: {e}")
                raise HTTPException(status_code=500, detail="Benchmark failed")
