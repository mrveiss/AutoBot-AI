# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bringing the worker up, and loading models into it (#68, #640, #15642).

Everything that runs before the worker can serve a request: bootstrap
configuration from the main host, telemetry, Redis, NPU provider detection, and
the model loads — including the mock path a machine with no NPU falls back to.
The network banner printed at startup belongs to the same phase.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from model_manager import get_model_manager
from worker_settings import DEFAULT_NPU_PRECISION, DEFAULT_PORT, config

logger = logging.getLogger(__name__)


class WorkerStartupMixin:
    """Initialisation and model-loading for :class:`WindowsNPUWorker`."""

    async def initialize(self):
        """
        Initialize NPU worker with parallel initialization for efficiency.

        Issue #68: Uses asyncio.gather for parallel init where possible.
        Issue #641: Worker is now passive - does NOT self-register.
                   Waits for main host to pair via /pair endpoint.
        """
        self.start_time = time.time()

        # Issue #641: Log pairing status
        if self.worker_id:
            logger.info(f"Starting Windows NPU Worker (paired): {self.worker_id}")
        else:
            logger.info("Starting Windows NPU Worker (unpaired - waiting for main host)")

        logger.info(f"Port: {config.get('service', {}).get('port', DEFAULT_PORT)}")

        # Display network connection information
        self._display_network_info()

        # Issue #641: REMOVED bootstrap_config() call
        # Worker no longer self-registers. Main host controls registration via /pair endpoint.
        # If worker is already paired, we use the stored config.

        # Parallel initialization of independent components (Issue #68 - efficiency)
        # Redis and NPU initialization can run in parallel
        await asyncio.gather(
            self.initialize_redis(),
            self.initialize_npu(),
            return_exceptions=True,  # Don't fail if one component fails
        )

        # Load default models if configured (depends on NPU init)
        if config.get("models", {}).get("autoload_defaults", True):
            await self.load_default_models()

        # Issue #641: REMOVED auto-registration telemetry
        # Telemetry only runs AFTER worker is paired with main host
        if self.pairing_status.get("paired"):
            await self.initialize_telemetry()
        else:
            logger.info("Telemetry disabled - worker not yet paired with main host")
            self.telemetry_client = None

        pairing_msg = "paired" if self.pairing_status.get("paired") else "waiting for pairing"
        logger.info(f"Windows NPU Worker initialized - NPU: {self.npu_available}, Status: {pairing_msg}")

    async def bootstrap_config(self):
        """
        Fetch configuration from backend on startup (Issue #68).

        This allows the worker to get Redis credentials and other settings
        from the main backend instead of hardcoding them locally.

        Issue #640: Pass existing worker_id to prevent duplicate registrations.
        """
        try:
            from utils.config_bootstrap import fetch_bootstrap_config, get_worker_id

            backend_config = config.get("backend", {})
            service_config = config.get("service", {})

            # Issue #640: Pass our persistent worker_id to prevent duplicates
            # Issue #3084: Use AUTOBOT_BACKEND_HOST env var; fallback to localhost (no hardcoded IPs)
            default_backend_host = os.environ.get("AUTOBOT_BACKEND_HOST", "localhost")  # ssot-config-exempt: NPU worker
            bootstrap = await fetch_bootstrap_config(
                backend_host=backend_config.get("host") or default_backend_host,
                backend_port=backend_config.get("port", 8001),
                worker_port=service_config.get("port", 8082),
                platform="windows",
                worker_id=self.worker_id,  # Pass existing ID to reuse registration
            )

            if bootstrap:
                # Update worker_id if assigned by backend (only if different)
                assigned_id = get_worker_id()
                if assigned_id and assigned_id != self.worker_id:
                    self.worker_id = assigned_id
                    logger.info(f"Worker ID updated by backend: {self.worker_id}")

                # Store bootstrap config for use by other components
                self._bootstrap_config = bootstrap
                logger.info("Bootstrap config received from backend")
            else:
                logger.warning("Bootstrap failed - using local config (standalone mode)")
                self._bootstrap_config = None

        except Exception as e:
            logger.warning(f"Bootstrap error: {e} - using local config")
            self._bootstrap_config = None

    async def initialize_telemetry(self):
        """
        Initialize backend telemetry client (Issue #68).

        Sends heartbeats and metrics to the AutoBot backend for:
        - Auto-registration
        - Status updates
        - Prometheus/Grafana metrics
        """
        try:
            from utils.backend_telemetry import get_telemetry_client

            self.telemetry_client = await get_telemetry_client(config)

            if self.telemetry_client:
                # Update initial metrics
                self.telemetry_client.update_metrics(
                    npu_available=self.npu_available,
                    loaded_models=list(self.loaded_models.keys()),
                )

                # Start telemetry loop
                await self.telemetry_client.start()
                logger.info("Backend telemetry initialized")
            else:
                logger.info("Backend telemetry disabled")
                self.telemetry_client = None

        except Exception as e:
            logger.warning(f"Telemetry initialization failed: {e}")
            self.telemetry_client = None

    async def initialize_redis(self):
        """
        Initialize Redis connection using canonical get_redis_client() pattern

        Uses bootstrap config from backend if available, otherwise falls back
        to local config. This allows credentials to come from main host.
        """
        try:
            from utils.config_bootstrap import get_redis_config
            from utils.redis_client import get_redis_client

            # Use bootstrap Redis config if available
            redis_config = get_redis_config()
            if redis_config:
                # Merge bootstrap config with local config
                merged_config = dict(config)
                merged_config["redis"] = redis_config
                self.redis_client = await get_redis_client(merged_config)
            else:
                # Fallback to local config (likely won't have credentials)
                self.redis_client = await get_redis_client(config)

            if self.redis_client:
                logger.info("Connected to Redis with connection pooling")
            else:
                logger.info("Operating in standalone mode without Redis")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")
            self.redis_client = None

    def _detect_npu_provider(self, available_providers: list) -> None:
        """
        Detect NPU/GPU availability from ONNX Runtime providers and set npu_available.

        Issue #2346: Extracted from initialize_npu to keep that method within 65 lines.
        Checks OpenVINO EP (preferred for Intel NPU), DirectML, and CUDA in priority order.

        Args:
            available_providers: List of available ONNX Runtime execution provider names.
        """
        if "OpenVINOExecutionProvider" in available_providers:
            try:
                from openvino import Core

                core = Core()
                available_devices = core.available_devices
                logger.info(f"OpenVINO available devices: {available_devices}")

                if "NPU" in available_devices:
                    self.npu_available = True
                    logger.info("Intel NPU detected via OpenVINO - NPU acceleration enabled!")
                elif "GPU" in available_devices:
                    self.npu_available = True
                    logger.info("Intel GPU detected via OpenVINO - GPU acceleration enabled")
                else:
                    self.npu_available = False
                    logger.warning("OpenVINO EP available but no NPU/GPU detected")
            except ImportError:
                self.npu_available = True
                logger.info("OpenVINO EP available - will try NPU/GPU acceleration")
        elif "DmlExecutionProvider" in available_providers:
            self.npu_available = True
            logger.info("DirectML available (GPU only, Intel NPU not exposed via DirectML)")
        elif "CUDAExecutionProvider" in available_providers:
            self.npu_available = True
            logger.info("CUDA execution provider available - NVIDIA GPU acceleration enabled")
        else:
            self.npu_available = False
            logger.warning("No GPU/NPU acceleration available - using CPU only")

    async def initialize_npu(self):
        """
        Initialize NPU/GPU acceleration with ONNX Runtime OpenVINO EP.

        Issue #640: Uses OpenVINO Execution Provider for proper Intel NPU support.
        DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option.
        Device priority: NPU → GPU → CPU (automatic fallback)
        """
        try:
            import platform

            if platform.system() != "Windows":
                logger.warning("NPU worker optimized for Windows - OpenVINO NPU not available on this platform")
                self.npu_available = False
                return

            import onnxruntime as ort

            available_providers = ort.get_available_providers()
            logger.info(f"Available ONNX Runtime providers: {available_providers}")

            self._detect_npu_provider(available_providers)

            # Initialize model manager for real inference (Issue #640)
            if self._use_real_inference:
                try:
                    self._model_manager = get_model_manager()
                    device_info = self._model_manager.get_device_info()
                    logger.info(f"Model manager initialized: {device_info}")

                    if device_info.get("is_gpu") or device_info.get("is_npu"):
                        self.npu_available = True

                except Exception as e:
                    logger.error(f"Failed to initialize model manager: {e}")
                    logger.info("Falling back to mock inference")
                    self._use_real_inference = False

        except ImportError as e:
            logger.error(f"ONNX Runtime not installed: {e}")
            logger.error("Install with: pip install onnxruntime-openvino")
            self.npu_available = False
            self._use_real_inference = False
        except Exception as e:
            logger.error(f"NPU/GPU initialization failed: {e}")
            self.npu_available = False
            self._use_real_inference = False

    async def load_default_models(self):
        """Load default models"""
        models_config = config.get("models", {})

        for model_type in ["embedding", "chat"]:
            model_config = models_config.get(model_type, {})
            if model_config.get("preload", False):
                try:
                    await self.load_and_optimize_model(
                        model_config.get("name"),
                        model_config.get("optimization_level", "balanced"),
                    )
                except Exception as e:
                    logger.warning(f"Failed to preload {model_type} model: {e}")

    async def load_and_optimize_model(self, model_name: str, optimization_level: str = "balanced"):
        """
        Load and optimize model with thread-safe locking (Issue #68 - TOCTOU fix).

        Issue #640: Now uses ONNX Runtime + DirectML for stable NPU/GPU inference.
        Uses lock to prevent race condition where model loading starts
        after check but before load completes.
        """
        async with self._models_lock:
            # Double-check if model already loaded after acquiring lock
            if model_name in self.loaded_models:
                logger.debug(f"Model {model_name} already loaded")
                return

            start_time = time.time()

            try:
                # Issue #640: Use ONNX Runtime model manager for DirectML inference
                if self._use_real_inference and self._model_manager is not None:
                    logger.info(f"Loading {model_name} with ONNX Runtime (real inference)...")

                    # Load model via model manager (handles download + ONNX export)
                    success = await self._model_manager.load_model(model_name)

                    if success:
                        device_info = self._model_manager.get_device_info()
                        selected_device = device_info.get("selected_device", "CPU")

                        # Map DirectML to NPU/GPU for display
                        display_device = selected_device
                        if selected_device == "DirectML":
                            display_device = "NPU/GPU (DirectML)"

                        self.loaded_models[model_name] = {
                            "loaded_at": datetime.now().isoformat(),
                            "load_time": time.time() - start_time,
                            "device": display_device,
                            "size_mb": self.estimate_model_size(model_name),
                            "optimized_for_npu": device_info.get("is_npu", False) or device_info.get("is_gpu", False),
                            "optimization_level": optimization_level,
                            "precision": self.npu_optimization.get("precision", DEFAULT_NPU_PRECISION),
                            "real_inference": True,
                            "device_info": device_info,
                            "backend": device_info.get("backend", "ONNX Runtime"),
                        }
                        logger.info(f"Model {model_name} loaded for {display_device} (real inference)")
                    else:
                        logger.warning(f"Failed to load {model_name} with real inference, using mock")
                        await self._load_mock_model(model_name, optimization_level, start_time)

                else:
                    # Fallback to mock loading
                    await self._load_mock_model(model_name, optimization_level, start_time)

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                raise

    async def _load_mock_model(self, model_name: str, optimization_level: str, start_time: float):
        """Load mock model (fallback when real inference unavailable)."""
        if self.npu_available:
            logger.info(f"Loading {model_name} for NPU (mock)...")
            await asyncio.sleep(2)  # Simulate loading

            self.loaded_models[model_name] = {
                "loaded_at": datetime.now().isoformat(),
                "load_time": time.time() - start_time,
                "device": "NPU",
                "size_mb": self.estimate_model_size(model_name),
                "optimized_for_npu": True,
                "optimization_level": optimization_level,
                "precision": self.npu_optimization.get("precision", DEFAULT_NPU_PRECISION),
                "real_inference": False,
            }
            logger.info(f"Model {model_name} loaded for NPU (mock)")
        else:
            logger.info(f"Loading {model_name} for CPU (mock)...")
            await asyncio.sleep(1)

            self.loaded_models[model_name] = {
                "loaded_at": datetime.now().isoformat(),
                "load_time": time.time() - start_time,
                "device": "CPU",
                "size_mb": self.estimate_model_size(model_name),
                "optimized_for_npu": False,
                "real_inference": False,
            }

    def _display_network_info(self):
        """Display network connection information on startup"""
        try:
            # Import network info utilities
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from gui.utils.network_info import (
                format_connection_info_box,
                get_network_interfaces,
                get_platform_info,
            )

            port = config.get("service", {}).get("port", 8082)
            interfaces = get_network_interfaces()
            platform_info = get_platform_info()

            # Format and display the connection info box
            info_box = format_connection_info_box(
                worker_id=self.worker_id,
                port=port,
                interfaces=interfaces,
                platform_info=platform_info,
            )

            # Log the info box
            logger.info("\n%s\n", info_box)

            # Also log key connection information
            logger.info("=" * 60)
            logger.info("NPU Worker Network Configuration:")
            logger.info(f"  Worker ID: {self.worker_id}")
            logger.info(f"  Port: {port}")

            if interfaces:
                logger.info("  Network Interfaces:")
                for iface in interfaces:
                    primary = " (Primary)" if iface.get("is_primary") else ""
                    logger.info(f"    - {iface['type']} ({iface['interface']}): {iface['ip']}{primary}")
            else:
                logger.info("  Network Interfaces: None detected")

            logger.info("=" * 60)

        except Exception as e:
            logger.warning(f"Failed to display network info: {e}")
