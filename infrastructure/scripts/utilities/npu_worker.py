#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Windows Native NPU Worker for AutoBot
Processes lightweight AI tasks using Intel NPU hardware acceleration
"""

import asyncio
import json
import logging
import os

# Import centralized Redis client
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from src.utils.redis_client import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NPUTaskRequest(BaseModel):
    """NPU task request model."""

    task_type: str
    model_name: str
    input_data: Dict[str, Any]
    priority: int = 1
    timeout_seconds: int = 30


class NPUTaskResponse(BaseModel):
    """NPU task response model."""

    task_id: str
    status: str  # 'completed', 'failed', 'processing'
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None
    npu_utilization_percent: Optional[float] = None


class NPUWorker:
    """Windows NPU Worker for AutoBot integration."""

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        """Initialize NPU worker with Redis connection and FastAPI routes setup."""
        self.worker_id = f"npu_worker_{uuid.uuid4().hex[:8]}"
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None
        self.app = FastAPI(title="AutoBot NPU Worker", version="1.0.0")
        self.npu_available = False
        self.loaded_models = {}
        self.task_stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "average_response_time_ms": 0,
            "npu_utilization_percent": 0,
        }

        # Setup FastAPI routes
        self.setup_routes()

    def setup_routes(self):
        """Setup FastAPI routes for health, stats, inference, and model management."""

        @self.app.on_event("startup")
        async def startup():
            """Initialize NPU worker on application startup."""
            await self.initialize()

        @self.app.on_event("shutdown")
        async def shutdown():
            """Cleanup NPU worker resources on application shutdown."""
            await self.cleanup()

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {
                "status": "healthy",
                "worker_id": self.worker_id,
                "npu_available": self.npu_available,
                "loaded_models": list(self.loaded_models.keys()),
                "stats": self.task_stats,
                "timestamp": datetime.now().isoformat(),
            }

        @self.app.get("/stats")
        async def get_stats():
            """Get detailed worker statistics."""
            return {
                "worker_id": self.worker_id,
                "uptime_seconds": time.time() - self.start_time,
                "npu_status": await self.get_npu_status(),
                "task_stats": self.task_stats,
                "loaded_models": {
                    name: {
                        "size_mb": info.get("size_mb", 0),
                        "load_time": info.get("load_time", "unknown"),
                        "last_used": info.get("last_used", "never"),
                    }
                    for name, info in self.loaded_models.items()
                },
            }

        @self.app.post("/inference", response_model=NPUTaskResponse)
        async def process_inference(request: NPUTaskRequest):
            """Process direct inference request."""
            task_id = str(uuid.uuid4())

            try:
                start_time = time.time()
                result = await self.process_task(task_id, request.dict())
                end_time = time.time()

                processing_time = (end_time - start_time) * 1000

                return NPUTaskResponse(
                    task_id=task_id,
                    status="completed",
                    result=result,
                    processing_time_ms=processing_time,
                    npu_utilization_percent=await self.get_npu_utilization(),
                )

            except Exception as e:
                logger.error("Inference failed for task %s: %s", task_id, e)
                return NPUTaskResponse(task_id=task_id, status="failed", error=str(e))

        @self.app.post("/model/load")
        async def load_model(model_name: str):
            """Load a specific model into NPU memory."""
            try:
                await self.load_model(model_name)
                return {"status": "success", "model": model_name, "loaded": True}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/models")
        async def list_models():
            """List available and loaded models."""
            return {
                "loaded_models": list(self.loaded_models.keys()),
                "available_models": await self.get_available_models(),
            }

    async def initialize(self):
        """Initialize NPU worker."""
        self.start_time = time.time()
        logger.info("🚀 Starting NPU Worker %s", self.worker_id)

        # Initialize Redis connection using centralized client
        try:
            self.redis_client = await get_redis_client("main")
            if self.redis_client:
                logger.info("✅ Connected to Redis via centralized client")
            else:
                logger.warning(
                    "⚠️ Redis client not available, continuing without Redis"
                )
        except Exception as e:
            logger.error("❌ Redis connection failed: %s", e)
            self.redis_client = None

        # Initialize NPU
        await self.initialize_npu()

        # Start task processing loop
        if self.redis_client:
            asyncio.create_task(self.task_processing_loop())

        logger.info("🎯 NPU Worker initialized - NPU Available: %s", self.npu_available)

    async def initialize_npu(self):
        """Initialize Intel NPU hardware."""
        try:
            # Check if we're on Windows
            import platform

            if platform.system() != "Windows":
                logger.warning(
                    "⚠️ NPU worker optimized for Windows - running in fallback mode"
                )
                self.npu_available = False
                return

            # Try to initialize OpenVINO with NPU
            try:
                from openvino.runtime import Core

                core = Core()
                devices = core.available_devices
                npu_devices = [d for d in devices if "NPU" in d]

                if npu_devices:
                    self.npu_available = True
                    self.openvino_core = core
                    logger.info("✅ NPU initialized - Devices: %s", npu_devices)

                    # Load default models
                    await self.load_default_models()
                else:
                    logger.warning("⚠️ No NPU devices found - using CPU fallback")
                    self.npu_available = False

            except ImportError:
                logger.error(
                    "❌ OpenVINO not installed - install with: pip install openvino"
                )
                self.npu_available = False
            except Exception as e:
                logger.error("❌ NPU initialization failed: %s", e)
                self.npu_available = False

        except Exception as e:
            logger.error("❌ NPU setup error: %s", e)
            self.npu_available = False

    async def load_default_models(self):
        """Load default models optimized for NPU."""
        default_models = [
            "llama3.2:1b-instruct-q4_K_M",  # Fast chat
            "nomic-embed-text",  # Embeddings
        ]

        for model_name in default_models:
            try:
                await self.load_model(model_name)
            except Exception as e:
                logger.warning("⚠️ Failed to load default model %s: %s", model_name, e)

    async def load_model(self, model_name: str):
        """Load model for NPU inference."""
        try:
            start_time = time.time()

            if self.npu_available:
                # Load with OpenVINO NPU optimization
                logger.info("📥 Loading %s for NPU...", model_name)

                # This would be the actual model loading logic
                # For now, simulate the loading process
                await asyncio.sleep(1)  # Simulate loading time

                self.loaded_models[model_name] = {
                    "loaded_at": datetime.now().isoformat(),
                    "load_time": time.time() - start_time,
                    "device": "NPU",
                    "size_mb": self.estimate_model_size(model_name),
                }

                logger.info(
                    f"✅ Model {model_name} loaded on NPU ({time.time() - start_time:.2f}s)"
                )
            else:
                # CPU fallback
                logger.info("📥 Loading %s for CPU fallback...", model_name)
                await asyncio.sleep(0.5)  # Faster CPU loading simulation

                self.loaded_models[model_name] = {
                    "loaded_at": datetime.now().isoformat(),
                    "load_time": time.time() - start_time,
                    "device": "CPU",
                    "size_mb": self.estimate_model_size(model_name),
                }

        except Exception as e:
            logger.error("❌ Failed to load model %s: %s", model_name, e)
            raise

    def estimate_model_size(self, model_name: str) -> int:
        """Estimate model size in MB."""
        if "1b" in model_name.lower():
            return 800
        elif "3b" in model_name.lower():
            return 2000
        elif "embed" in model_name.lower():
            return 300
        else:
            return 1000

    async def task_processing_loop(self):
        """Main task processing loop from Redis queue."""
        logger.info("🔄 Starting task processing loop")

        while True:
            try:
                # Check for pending NPU tasks
                task_data = await self.redis_client.blpop(
                    "npu_tasks_pending", timeout=5
                )

                if task_data:
                    _, task_json = task_data
                    task = json.loads(task_json)
                    await self.handle_queued_task(task)

            except Exception as e:
                logger.error("❌ Task processing error: %s", e)
                await asyncio.sleep(1)

    async def handle_queued_task(self, task: Dict[str, Any]):
        """Handle a task from the Redis queue."""
        task_id = task.get("task_id")

        try:
            logger.info("🔄 Processing task %s", task_id)

            # Move task to processing queue
            await self.redis_client.lpush("npu_tasks_processing", json.dumps(task))

            # Process the task
            start_time = time.time()
            result = await self.process_task(task_id, task)
            end_time = time.time()

            # Create response
            response = {
                "task_id": task_id,
                "status": "completed",
                "result": result,
                "processing_time_ms": (end_time - start_time) * 1000,
                "worker_id": self.worker_id,
                "completed_at": datetime.now().isoformat(),
            }

            # Move to completed queue
            await self.redis_client.lpush("npu_tasks_completed", json.dumps(response))
            await self.redis_client.lrem("npu_tasks_processing", 1, json.dumps(task))

            # Update stats
            self.task_stats["tasks_completed"] += 1

            logger.info(
                f"✅ Task {task_id} completed in {(end_time - start_time)*1000:.2f}ms"
            )

        except Exception as e:
            logger.error("❌ Task %s failed: %s", task_id, e)

            # Move to failed queue
            error_response = {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
                "worker_id": self.worker_id,
                "failed_at": datetime.now().isoformat(),
            }

            await self.redis_client.lpush(
                "npu_tasks_failed", json.dumps(error_response)
            )
            await self.redis_client.lrem("npu_tasks_processing", 1, json.dumps(task))

            self.task_stats["tasks_failed"] += 1

    async def process_task(
        self, task_id: str, task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a specific task."""
        task_type = task_data.get("task_type")
        model_name = task_data.get("model_name")
        input_data = task_data.get("input_data", {})

        # Ensure model is loaded
        if model_name not in self.loaded_models:
            await self.load_model(model_name)

        # Update model last used time
        self.loaded_models[model_name]["last_used"] = datetime.now().isoformat()

        # Process based on task type
        if task_type == "chat_inference":
            return await self.process_chat_task(input_data, model_name)
        elif task_type == "embedding_generation":
            return await self.process_embedding_task(input_data, model_name)
        elif task_type == "text_classification":
            return await self.process_classification_task(input_data, model_name)
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

    async def process_chat_task(
        self, input_data: Dict[str, Any], model_name: str
    ) -> Dict[str, Any]:
        """Process chat inference task."""
        message = input_data.get("message", "")

        # Simulate NPU inference (replace with actual inference)
        await asyncio.sleep(0.1)  # NPU would be much faster

        return {
            "response": f"NPU processed: {message[:50]}..."
            if len(message) > 50
            else f"NPU processed: {message}",
            "model_used": model_name,
            "device": "NPU" if self.npu_available else "CPU",
            "confidence": 0.95,
        }

    async def process_embedding_task(
        self, input_data: Dict[str, Any], model_name: str
    ) -> Dict[str, Any]:
        """Process embedding generation task."""
        text = input_data.get("text", "")

        # Simulate embedding generation (replace with actual)
        await asyncio.sleep(0.05)  # Very fast on NPU

        # Generate dummy embedding vector
        import random

        embedding = [random.random() for _ in range(768)]

        return {
            "embedding": embedding,
            "model_used": model_name,
            "device": "NPU" if self.npu_available else "CPU",
            "text_length": len(text),
        }

    async def process_classification_task(
        self, input_data: Dict[str, Any], model_name: str
    ) -> Dict[str, Any]:
        """Process text classification task."""
        input_data.get("text", "")

        await asyncio.sleep(0.05)

        return {
            "classification": "positive",
            "confidence": 0.89,
            "model_used": model_name,
            "device": "NPU" if self.npu_available else "CPU",
        }

    async def get_npu_status(self) -> Dict[str, Any]:
        """Get current NPU status."""
        return {
            "available": self.npu_available,
            "utilization_percent": await self.get_npu_utilization(),
            "temperature_c": await self.get_npu_temperature(),
            "power_usage_w": await self.get_npu_power_usage(),
        }

    async def get_npu_utilization(self) -> float:
        """Get NPU utilization percentage."""
        # This would query actual NPU utilization
        # For now, simulate based on loaded models
        if self.loaded_models:
            return min(len(self.loaded_models) * 25.0, 100.0)
        return 0.0

    async def get_npu_temperature(self) -> float:
        """Get NPU temperature."""
        # Simulate NPU temperature (would be real sensor data)
        return 45.0 + (await self.get_npu_utilization()) * 0.3

    async def get_npu_power_usage(self) -> float:
        """Get NPU power usage in watts."""
        # Simulate NPU power usage (would be real power data)
        base_power = 2.0  # Idle power
        active_power = (
            await self.get_npu_utilization() / 100.0
        ) * 8.0  # Max 8W under load
        return base_power + active_power

    async def get_available_models(self) -> List[str]:
        """Get list of available models for NPU."""
        return [
            "llama3.2:1b-instruct-q4_K_M",
            "llama3.2:3b-instruct-q4_K_M",
            "nomic-embed-text",
            "text-classification-model",
        ]

    async def cleanup(self):
        """Cleanup resources."""
        logger.info("🧹 Cleaning up NPU worker resources")
        # Note: Centralized Redis client handles its own cleanup
        # No need to manually close the connection


def main():
    """Main function to run NPU worker with CLI argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot NPU Worker")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=8080, type=int, help="Port to bind to")
    parser.add_argument("--redis-host", default="localhost", help="Redis host")
    parser.add_argument("--redis-port", default=6379, type=int, help="Redis port")
    args = parser.parse_args()

    # Create NPU worker
    worker = NPUWorker(redis_host=args.redis_host, redis_port=args.redis_port)

    # Run the server
    logger.info("🚀 Starting NPU Worker on %s:%s", args.host, args.port)
    uvicorn.run(worker.app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
