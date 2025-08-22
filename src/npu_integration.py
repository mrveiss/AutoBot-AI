#!/usr/bin/env python3
"""
NPU Worker Integration
Provides high-performance processing using NPU worker for heavy computational tasks
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict

import aiohttp

from .utils.service_registry import get_service_url

logger = logging.getLogger(__name__)


@dataclass
class NPUInferenceRequest:
    model_id: str
    input_text: str
    max_tokens: int = 100
    temperature: float = 0.7
    top_p: float = 0.9


class NPUWorkerClient:
    """Client for communicating with NPU inference worker"""

    def __init__(self, npu_endpoint: str = None):
        self.npu_endpoint = npu_endpoint or get_service_url("npu-worker")
        self.session = None
        self.available = False
        self._check_availability_task = None

    async def _create_session(self):
        """Create aiohttp session if not exists"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def check_health(self) -> Dict[str, Any]:
        """Check NPU worker health and capabilities"""
        try:
            await self._create_session()
            async with self.session.get(f"{self.npu_endpoint}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    self.available = True
                    return health_data
                else:
                    self.available = False
                    return {"status": "unhealthy", "error": f"HTTP {response.status}"}
        except Exception as e:
            self.available = False
            logger.warning(f"NPU worker health check failed: {e}")
            return {"status": "unavailable", "error": str(e)}

    async def get_available_models(self) -> Dict[str, Any]:
        """Get list of available models on NPU worker"""
        try:
            await self._create_session()
            async with self.session.get(f"{self.npu_endpoint}/models") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"loaded_models": {}, "error": f"HTTP {response.status}"}
        except Exception as e:
            logger.error(f"Failed to get NPU models: {e}")
            return {"loaded_models": {}, "error": str(e)}

    async def load_model(self, model_id: str, device: str = "CPU") -> Dict[str, Any]:
        """Load a model on the NPU worker"""
        try:
            await self._create_session()
            payload = {"model_id": model_id, "device": device}
            async with self.session.post(
                f"{self.npu_endpoint}/models/load", json=payload
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return {"success": False, "error": str(e)}

    async def run_inference(
        self,
        model_id: str,
        input_text: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        """Run inference on NPU worker"""
        try:
            await self._create_session()
            payload = {
                "model_id": model_id,
                "input_text": input_text,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }

            async with self.session.post(
                f"{self.npu_endpoint}/inference", json=payload
            ) as response:
                result = await response.json()
                if response.status == 200:
                    return result
                else:
                    return {
                        "error": result.get("detail", "Unknown error"),
                        "success": False,
                    }
        except Exception as e:
            logger.error(f"NPU inference failed: {e}")
            return {"error": str(e), "success": False}

    async def offload_heavy_processing(
        self, task_type: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Offload heavy processing tasks to NPU worker

        Supported task types:
        - text_analysis: Analyze large text chunks
        - embedding_batch: Generate embeddings for multiple texts
        - knowledge_processing: Process knowledge base operations
        """
        try:
            # Check if NPU worker is available
            await self.check_health()
            if not self.available:
                return {
                    "success": False,
                    "error": "NPU worker not available",
                    "fallback": True,
                }

            # For now, use standard inference endpoint with task-specific prompts
            if task_type == "text_analysis":
                prompt = (
                    "Analyze the following text and extract key insights:\n\n"
                    f"{data.get('text', '')}"
                )
                return await self.run_inference(
                    model_id=data.get("model_id", "default"),
                    input_text=prompt,
                    max_tokens=data.get("max_tokens", 200),
                )

            elif task_type == "knowledge_processing":
                prompt = (
                    "Process and summarize this knowledge data:\n\n"
                    f"{json.dumps(data.get('knowledge_data', {}))}"
                )
                return await self.run_inference(
                    model_id=data.get("model_id", "default"),
                    input_text=prompt,
                    max_tokens=data.get("max_tokens", 150),
                )

            else:
                return {
                    "success": False,
                    "error": f"Unsupported task type: {task_type}",
                }

        except Exception as e:
            logger.error(f"Heavy processing offload failed: {e}")
            return {"success": False, "error": str(e), "fallback": True}

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None


class NPUTaskQueue:
    """Queue for managing NPU processing tasks"""

    def __init__(self, npu_client: NPUWorkerClient, max_concurrent: int = 3):
        self.npu_client = npu_client
        self.max_concurrent = max_concurrent
        self.queue = asyncio.Queue()
        self.workers = []
        self.running = False

    async def start_workers(self):
        """Start background worker tasks"""
        self.running = True
        for i in range(self.max_concurrent):
            worker = asyncio.create_task(self._worker(f"npu_worker_{i}"))
            self.workers.append(worker)
        logger.info(f"Started {self.max_concurrent} NPU workers")

    async def stop_workers(self):
        """Stop background worker tasks"""
        self.running = False
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        logger.info("Stopped NPU workers")

    async def _worker(self, worker_id: str):
        """Background worker that processes NPU tasks"""
        logger.info(f"NPU worker {worker_id} started")
        while self.running:
            try:
                # Wait for task with timeout to allow graceful shutdown
                task_data = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                logger.debug(
                    f"Worker {worker_id} processing task: {task_data['task_type']}"
                )

                # Process the task
                result = await self.npu_client.offload_heavy_processing(
                    task_data["task_type"], task_data["data"]
                )

                # Set result in the future
                if not task_data["future"].done():
                    task_data["future"].set_result(result)

                # Mark task as done
                self.queue.task_done()

            except asyncio.TimeoutError:
                continue  # No task available, continue loop
            except Exception as e:
                logger.error(f"NPU worker {worker_id} error: {e}")
                if "future" in locals() and not task_data["future"].done():
                    task_data["future"].set_exception(e)

    async def submit_task(self, task_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a task to the NPU queue"""
        if not self.running:
            await self.start_workers()

        future = asyncio.Future()
        task_data = {"task_type": task_type, "data": data, "future": future}

        await self.queue.put(task_data)

        try:
            # Wait for result with timeout
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            return {"success": False, "error": "NPU task timeout", "fallback": True}


# Global NPU client instance
_npu_client = None
_npu_queue = None


async def get_npu_client() -> NPUWorkerClient:
    """Get or create global NPU client instance"""
    global _npu_client
    if _npu_client is None:
        _npu_client = NPUWorkerClient()
        await _npu_client.check_health()
    return _npu_client


async def get_npu_queue() -> NPUTaskQueue:
    """Get or create global NPU task queue"""
    global _npu_queue
    if _npu_queue is None:
        client = await get_npu_client()
        _npu_queue = NPUTaskQueue(client)
    return _npu_queue


async def process_with_npu_fallback(
    task_type: str, data: Dict[str, Any], fallback_func: callable
) -> Dict[str, Any]:
    """
    Try to process with NPU worker, fall back to local processing if unavailable
    """
    try:
        queue = await get_npu_queue()
        result = await queue.submit_task(task_type, data)

        if result.get("fallback") or not result.get("success"):
            logger.info(f"NPU processing failed, using fallback for {task_type}")
            return await fallback_func()

        return result
    except Exception as e:
        logger.warning(f"NPU processing error for {task_type}: {e}")
        return await fallback_func()
