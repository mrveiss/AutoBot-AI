#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot NPU Worker - Windows Deployment Version
Optimized for Intel NPU/GPU hardware acceleration with ONNX Runtime + OpenVINO EP

Issue #640: Uses ONNX Runtime with OpenVINO Execution Provider for proper Intel NPU support.
DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option via device_type='NPU'.
Device priority: NPU → GPU → CPU (automatic fallback)

Issue #68: NPU worker settings with telemetry, bootstrap, and race condition fixes

#15642 decomposed this file. It is now the assembly point: the worker object
its mixins compose, the resources it holds, and the uvicorn entry point.
Settings and logging come from ``worker_settings`` (imported first, because
importing it is what configures logging); the behaviour is mixed in from
``worker_routes``, ``worker_pairing``, ``worker_startup``, ``worker_inference``
and ``worker_metrics``.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import asyncio
import logging
import os
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI
from model_manager import OpenVINOModelManager
from worker_identity import get_pairing_status, get_persistent_worker_id
from worker_inference import WorkerInferenceMixin
from worker_metrics import WorkerMetricsMixin
from worker_pairing import WorkerPairingMixin
from worker_routes import WorkerRoutesMixin
from worker_settings import (
    DEFAULT_EMBEDDING_CACHE_SIZE,
    DEFAULT_EMBEDDING_CACHE_TTL,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_NPU_BATCH_SIZE,
    DEFAULT_NPU_PRECISION,
    DEFAULT_NPU_STREAMS,
    DEFAULT_NPU_THREADS,
    DEFAULT_PORT,
    DEFAULT_WORKERS,
    config,
)
from worker_startup import WorkerStartupMixin
from worker_state import LRUCache, ThreadSafeStats

logger = logging.getLogger(__name__)


class WindowsNPUWorker(
    WorkerRoutesMixin,
    WorkerPairingMixin,
    WorkerStartupMixin,
    WorkerInferenceMixin,
    WorkerMetricsMixin,
):
    """
    Windows-optimized NPU Worker

    Issue #68 improvements:
    - Thread-safe stats counters (race condition fix)
    - LRU cache with size limits (memory growth fix)
    - Parallel initialization (efficiency improvement)
    - No hardcoded IPs (config from YAML/bootstrap)
    """

    def __init__(self):
        config.get("service", {})
        config.get("redis", {})
        npu_config = config.get("npu", {})
        cache_config = config.get("performance", {}).get("embedding_cache", {})

        # Issue #641: Worker ID is assigned by main host, not self-generated
        # If no ID exists, worker_id will be None until main host pairs with us
        self.worker_id = get_persistent_worker_id()
        self.pairing_status = get_pairing_status()
        self.redis_client = None

        self.app = FastAPI(title="AutoBot Windows NPU Worker", version="2.0.0")

        # NPU capabilities
        self.npu_available = False
        self.openvino_core = None
        self.loaded_models = {}
        self._models_lock = asyncio.Lock()  # Thread-safe model loading (TOCTOU fix)

        # Real OpenVINO model manager (Issue #640 - replaces mock inference)
        self._model_manager: OpenVINOModelManager | None = None
        self._use_real_inference = True  # Set to False to use mock inference for testing

        # Thread-safe LRU cache (Issue #68 - race condition + memory growth fix)
        cache_size = cache_config.get("max_size", DEFAULT_EMBEDDING_CACHE_SIZE)
        cache_ttl = cache_config.get("ttl", DEFAULT_EMBEDDING_CACHE_TTL)
        self.embedding_cache = LRUCache(max_size=cache_size, ttl=cache_ttl)

        # Thread-safe performance tracking (Issue #68 - race condition fix)
        self.task_stats = ThreadSafeStats()

        # NPU optimization from config (with constant defaults)
        self.npu_optimization = npu_config.get(
            "optimization",
            {
                "precision": DEFAULT_NPU_PRECISION,
                "batch_size": DEFAULT_NPU_BATCH_SIZE,
                "num_streams": DEFAULT_NPU_STREAMS,
                "num_threads": DEFAULT_NPU_THREADS,
            },
        )

        # Bootstrap config storage
        self._bootstrap_config: Dict[str, Any] | None = None

        self.setup_routes()

    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up NPU worker")

        # Clear thread-safe LRU cache
        await self.embedding_cache.clear()

        # Stop telemetry (Issue #68)
        if hasattr(self, "telemetry_client") and self.telemetry_client:
            try:
                await self.telemetry_client.stop()
            except Exception as e:
                logger.warning(f"Error during telemetry cleanup: {e}")

        if self.redis_client:
            try:
                from utils.redis_client import close_redis_client

                await close_redis_client()
            except Exception as e:
                logger.warning(f"Error during Redis cleanup: {e}")


def main():
    """Main entry point"""
    service_config = config.get("service", {})
    host = service_config.get("host", DEFAULT_HOST)
    port = service_config.get("port", DEFAULT_PORT)
    workers = service_config.get("workers", DEFAULT_WORKERS)

    logger.info(f"Starting AutoBot Windows NPU Worker on {host}:{port}")

    worker = WindowsNPUWorker()

    # TLS Configuration - Issue #725 Phase 5
    tls_config = config.get("tls", {})
    tls_enabled = (
        tls_config.get("enabled", False)
        or os.environ.get("NPU_WORKER_TLS_ENABLED", "false").lower() == "true"  # ssot-config-exempt: NPU worker
    )
    ssl_keyfile = None
    ssl_certfile = None

    if tls_enabled:
        cert_dir = tls_config.get(
            "cert_dir", os.environ.get("AUTOBOT_TLS_CERT_DIR", "certs")  # ssot-config-exempt: NPU worker
        )
        ssl_keyfile = os.path.join(cert_dir, "server-key.pem")
        ssl_certfile = os.path.join(cert_dir, "server-cert.pem")
        port = tls_config.get(
            "port", int(os.environ.get("NPU_WORKER_TLS_PORT", "8444"))  # ssot-config-exempt: NPU worker
        )
        logger.info(f"TLS enabled - using HTTPS on port {port}")

    uvicorn_config = {
        "app": worker.app,
        "host": host,
        "port": port,
        "workers": workers,
        "log_level": config.get("logging", {}).get("level", DEFAULT_LOG_LEVEL).lower(),
        "access_log": True,
    }

    if tls_enabled and ssl_keyfile and ssl_certfile:
        uvicorn_config["ssl_keyfile"] = ssl_keyfile
        uvicorn_config["ssl_certfile"] = ssl_certfile

    uvicorn.run(**uvicorn_config)


if __name__ == "__main__":
    main()
