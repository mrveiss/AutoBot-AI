# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which OpenVINO device runs a given workload (#640, #165, #15642).

Everything about picking an execution provider: what the ONNX Runtime install
actually offers, which OpenVINO devices the machine exposes, the per-workload
override that lets embeddings run on a discrete GPU while chat runs on the NPU,
and the provider list handed to a session. Split out of ``ONNXModelManager``,
which mixes it in.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import logging
from typing import List

from worker_settings import DEFAULT_NPU_THREADS, get_device_priority, get_parallel_device_config

logger = logging.getLogger(__name__)


class OpenVINODeviceSelectionMixin:
    """Device discovery and provider selection for :class:`ONNXModelManager`."""

    def _initialize_onnx_runtime(self):
        """Lazy initialize ONNX Runtime and detect available providers"""
        if self._initialized:
            return

        try:
            import onnxruntime as ort

            self._available_providers = ort.get_available_providers()
            logger.info(f"Available ONNX Runtime providers: {self._available_providers}")

            # Check for OpenVINO Execution Provider (preferred for Intel NPU)
            if "OpenVINOExecutionProvider" in self._available_providers:
                # Try to detect NPU availability via OpenVINO
                self._detect_openvino_devices()
            elif "DmlExecutionProvider" in self._available_providers:
                self._selected_device = "DirectML"  # GPU via DirectML (fallback)
                self._openvino_device = "GPU"
                logger.info("DirectML available (GPU only, no NPU support)")
            elif "CUDAExecutionProvider" in self._available_providers:
                self._selected_device = "CUDA"
                self._openvino_device = "GPU"
                logger.info("CUDA execution provider available (NVIDIA GPU)")
            else:
                self._selected_device = "CPU"
                self._openvino_device = "CPU"
                logger.info("Using CPU execution provider (no GPU/NPU acceleration)")

            self._initialized = True

        except ImportError as e:
            logger.error(f"ONNX Runtime not installed: {e}")
            logger.error("Install with: pip install onnxruntime-openvino")
            raise

    def _detect_openvino_devices(self):
        """
        Detect available OpenVINO devices and select based on config priority.

        Issue #165: Enhanced to support specific GPU devices (GPU.0, GPU.1)
        to allow preferring NVIDIA dGPU (GPU.1) over Intel NPU for faster embeddings.
        The NVIDIA RTX 4070 (GPU.1) is ~10-100x faster than Intel NPU for embeddings.
        """
        try:
            # Try to import OpenVINO to check available devices
            from openvino import Core

            core = Core()
            available_devices = core.available_devices
            logger.info(f"OpenVINO available devices: {available_devices}")

            # Get full device names for each device
            for device in available_devices:
                try:
                    full_name = core.get_property(device, "FULL_DEVICE_NAME")
                    self._device_full_names[device] = full_name
                    logger.info(f"Device {device}: {full_name}")
                except Exception as e:
                    logger.debug(f"Could not get full name for {device}: {e}")
                    self._device_full_names[device] = device

            # Issue #165: Use config-based device priority
            # This allows preferring GPU.1 (NVIDIA) over NPU for faster embeddings
            device_priority = get_device_priority()
            logger.info(f"Device priority from config: {device_priority}")

            selected = False
            for preferred_device in device_priority:
                if preferred_device in available_devices:
                    self._selected_device = preferred_device
                    self._openvino_device = preferred_device
                    device_name = self._device_full_names.get(preferred_device, preferred_device)
                    logger.info(f"Selected device: {preferred_device} ({device_name})")
                    selected = True
                    break

            if not selected:
                # Fallback to CPU if no preferred device available
                self._selected_device = "CPU"
                self._openvino_device = "CPU"
                cpu_name = self._device_full_names.get("CPU", "CPU")
                logger.info(f"Fallback to CPU: {cpu_name}")

        except ImportError:
            # OpenVINO not installed separately, use EP defaults
            logger.info("OpenVINO EP available, will auto-detect device")
            self._selected_device = "OpenVINO"
            self._openvino_device = "NPU"  # Try NPU first
        except Exception as e:
            logger.warning(f"OpenVINO device detection failed: {e}")
            self._selected_device = "OpenVINO"
            self._openvino_device = "CPU"

    def _get_device_for_model_type(self, model_type: str = "default") -> str:
        """
        Get the device to use for a specific model type.

        Issue #165: Enables parallel device usage - different devices for different workloads.
        GPU.1 (NVIDIA RTX 4070) for embeddings, NPU for chat inference.

        Args:
            model_type: "embedding", "chat", or "default"

        Returns:
            Device string (e.g., "GPU.1", "NPU", "CPU")
        """
        parallel_config = get_parallel_device_config()

        if not parallel_config.get("enabled", False):
            # Parallel mode disabled, use default device
            return self._openvino_device

        # Get available devices
        try:
            from openvino import Core

            available_devices = Core().available_devices
        except Exception:
            available_devices = ["CPU"]

        # Select device based on model type
        if model_type == "embedding":
            preferred = parallel_config.get("embedding_device")
        elif model_type == "chat":
            preferred = parallel_config.get("chat_device")
        else:
            preferred = None

        # Check if preferred device is available
        if preferred and preferred in available_devices:
            logger.info(f"Using {preferred} for {model_type} workload (parallel mode)")
            return preferred

        # Fallback to default device
        fallback = parallel_config.get("fallback_device", "CPU")
        if fallback in available_devices:
            return fallback

        return self._openvino_device

    def _get_session_providers(self, model_type: str = "default") -> List[tuple]:
        """
        Get ordered list of execution providers with options for session creation.

        Issue #165: Added model_type parameter for workload-specific device selection.

        Args:
            model_type: "embedding", "chat", or "default" for device selection
        """
        self._initialize_onnx_runtime()

        # Get the appropriate device for this model type
        target_device = self._get_device_for_model_type(model_type)

        providers = []

        # OpenVINO Execution Provider with workload-specific device
        if "OpenVINOExecutionProvider" in self._available_providers:
            # OpenVINO EP provider options
            # device_type can be: NPU, GPU, CPU, GPU.0, GPU.1, etc.
            openvino_options = {
                "device_type": target_device,
                "precision": "FP16",  # FP16 for better performance
                "enable_opencl_throttling": True,
                "num_of_threads": DEFAULT_NPU_THREADS,
            }
            providers.append(("OpenVINOExecutionProvider", openvino_options))
            logger.info(f"Using OpenVINO EP with device_type='{target_device}' for {model_type}")

        # DirectML as fallback for GPU (doesn't support NPU properly)
        if "DmlExecutionProvider" in self._available_providers:
            providers.append("DmlExecutionProvider")

        # CUDA for NVIDIA GPUs
        if "CUDAExecutionProvider" in self._available_providers:
            providers.append("CUDAExecutionProvider")

        # CPU as final fallback (always available)
        providers.append("CPUExecutionProvider")

        return providers
