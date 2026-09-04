# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the worker reports about itself (#15642).

NPU metrics, status, utilisation, temperature, power, memory, the model-size
estimate and the self-benchmark. Read-only reporting: nothing here changes
worker state, which is why it separates cleanly from the routes that serve it.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict

from worker_settings import (
    MODEL_SIZE_1B,
    MODEL_SIZE_3B,
    MODEL_SIZE_DEFAULT,
    MODEL_SIZE_EMBED,
    NPU_BASE_POWER_W,
    NPU_BASE_TEMP_C,
    NPU_POWER_RANGE_W,
    NPU_TEMP_RANGE_C,
)

logger = logging.getLogger(__name__)


class WorkerMetricsMixin:
    """Metrics, status and benchmark reporting for :class:`WindowsNPUWorker`."""

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
        """Get NPU utilization (async for thread-safe stats access)"""
        if self.loaded_models:
            base = min(len(self.loaded_models) * 20.0, 80.0)
            tasks_completed = await self.task_stats.get("tasks_completed")
            activity = min(tasks_completed * 2.0, 20.0)
            return min(base + activity, 100.0)
        return 0.0

    async def get_npu_temperature(self) -> float:
        """Get NPU temperature (simulated based on utilization)"""
        utilization = await self.get_npu_utilization()
        return NPU_BASE_TEMP_C + (utilization / 100.0) * NPU_TEMP_RANGE_C

    async def get_npu_power_usage(self) -> float:
        """Get NPU power usage (simulated based on utilization)"""
        utilization = await self.get_npu_utilization()
        return NPU_BASE_POWER_W + (utilization / 100.0) * NPU_POWER_RANGE_W

    async def get_npu_memory_usage(self) -> float:
        """Get NPU memory usage"""
        return sum(info.get("size_mb", 0) for info in self.loaded_models.values() if info.get("device") == "NPU")

    def estimate_model_size(self, model_name: str) -> int:
        """Estimate model size in MB using constants"""
        model_lower = model_name.lower()
        if "1b" in model_lower:
            return MODEL_SIZE_1B
        elif "3b" in model_lower:
            return MODEL_SIZE_3B
        elif "embed" in model_lower or "nomic" in model_lower:
            return MODEL_SIZE_EMBED
        else:
            return MODEL_SIZE_DEFAULT

    async def run_benchmark(self) -> Dict[str, Any]:
        """Run performance benchmark"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "worker_id": self.worker_id,
            "npu_available": self.npu_available,
            "benchmarks": {},
        }

        # Embedding benchmark
        test_texts = [
            "Test sentence for embedding generation.",
            "AutoBot is an AI platform.",
            "NPU acceleration improves performance.",
        ]

        start_time = time.time()
        embeddings = await self.generate_npu_embeddings(test_texts, "nomic-embed-text", False, "speed")
        embedding_time = (time.time() - start_time) * 1000

        results["benchmarks"]["embedding_generation"] = {
            "texts_processed": len(test_texts),
            "total_time_ms": embedding_time,
            "avg_time_per_text_ms": embedding_time / len(test_texts),
            "device_used": "NPU" if self.npu_available else "CPU",
        }

        # Search benchmark
        start_time = time.time()
        search_results = await self.perform_semantic_search(
            "test query", embeddings, [{"text": text} for text in test_texts], 3, 0.5
        )
        search_time = (time.time() - start_time) * 1000

        results["benchmarks"]["semantic_search"] = {
            "documents_searched": len(embeddings),
            "results_returned": len(search_results),
            "total_time_ms": search_time,
            "device_used": "NPU" if self.npu_available else "CPU",
        }

        return results
