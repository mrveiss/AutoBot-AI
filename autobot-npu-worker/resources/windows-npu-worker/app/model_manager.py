# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The worker's model registry and inference sessions (#640, #15642).

Owns the loaded models: the ONNX Runtime sessions, the tokenizers, the
embedding call itself, and the process-wide manager singleton. Device
selection and ONNX conversion are mixed in from
``onnx_device_selection`` and ``model_conversion``.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from model_conversion import ModelConversionMixin
from onnx_device_selection import OpenVINODeviceSelectionMixin
from worker_settings import MODELS_DIR, SUPPORTED_MODELS

logger = logging.getLogger(__name__)


# =============================================================================
# ONNX Runtime Model Management (Issue #640 - OpenVINO Execution Provider)
# =============================================================================
#
# This uses ONNX Runtime with OpenVINO Execution Provider for Intel NPU support.
# DirectML doesn't properly expose Intel NPUs - OpenVINO EP has explicit
# NPU device support via device_type='NPU' option.
#
# Device priority: NPU → GPU → CPU (automatic fallback)
# Requires: Windows 11 24H2+ with Intel AI Boost drivers for NPU
# =============================================================================


class ONNXModelManager(OpenVINODeviceSelectionMixin, ModelConversionMixin):
    """
    Manages ONNX model downloading, conversion, and inference with OpenVINO EP.

    Issue #640: Uses OpenVINO Execution Provider for proper Intel NPU support.
    DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option.
    Uses HuggingFace for model downloading and exports to ONNX format for inference.

    Device priority: OpenVINOExecutionProvider (NPU→GPU→CPU) → CPUExecutionProvider
    """

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._tokenizers: Dict[str, Any] = {}
        self._sessions: Dict[str, Any] = {}  # ONNX Runtime InferenceSessions
        self._model_configs: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._selected_device: str | None = None
        self._available_providers: List[str] = []
        self._initialized = False
        self._openvino_device: str = "CPU"  # NPU, GPU, or CPU
        self._device_full_names: Dict[str, str] = {}  # Full device names from OpenVINO

    async def load_model(self, model_name: str) -> bool:
        """
        Load ONNX model and create inference session with DirectML.

        Returns True if model is ready for inference.
        """
        async with self._lock:
            if model_name in self._sessions:
                logger.debug(f"Model {model_name} already loaded")
                return True

            try:
                # Ensure model is downloaded and converted
                model_path = await self.ensure_model_downloaded(model_name)

                # Load in thread pool (blocking operations)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self._create_inference_session, model_name, model_path)
                return success

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                return False

    def _determine_model_type(self, model_name: str) -> str:
        """
        Determine model type from model name for device selection.

        Issue #165: Used to route embedding models to GPU, chat models to NPU.
        """
        model_name_lower = model_name.lower()
        if "embed" in model_name_lower or "minilm" in model_name_lower or "bge" in model_name_lower:
            return "embedding"
        elif "llama" in model_name_lower or "chat" in model_name_lower or "instruct" in model_name_lower:
            return "chat"
        return "default"

    def _create_inference_session(self, model_name: str, model_path: Path) -> bool:
        """Create ONNX Runtime inference session with workload-specific device selection"""
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            self._initialize_onnx_runtime()

            # Load tokenizer
            logger.info(f"Loading tokenizer for {model_name}...")
            tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
            self._tokenizers[model_name] = tokenizer

            # Issue #165: Determine model type for device selection
            model_type = self._determine_model_type(model_name)

            # Create ONNX Runtime session with workload-specific device
            onnx_model_path = model_path / "model.onnx"
            logger.info(f"Creating inference session for {onnx_model_path} (type: {model_type})...")

            providers = self._get_session_providers(model_type)
            logger.info(f"Using execution providers: {providers}")

            # Session options for optimization
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.enable_mem_pattern = True
            sess_options.enable_cpu_mem_arena = True

            # Create session with provider fallback
            session = ort.InferenceSession(str(onnx_model_path), sess_options=sess_options, providers=providers)

            # Log which provider was actually used
            actual_providers = session.get_providers()
            logger.info(f"Session created with providers: {actual_providers}")

            # Update selected device based on actual provider
            if "OpenVINOExecutionProvider" in actual_providers:
                # OpenVINO EP is being used - check which device it's targeting
                self._selected_device = self._openvino_device  # NPU, GPU, or CPU
            elif "DmlExecutionProvider" in actual_providers:
                self._selected_device = "DirectML"
            elif "CUDAExecutionProvider" in actual_providers:
                self._selected_device = "CUDA"
            else:
                self._selected_device = "CPU"

            self._sessions[model_name] = session
            self._model_configs[model_name] = SUPPORTED_MODELS.get(model_name, {})

            logger.info(f"Model {model_name} loaded successfully on {self._selected_device}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to create inference session for {model_name}: {e}",
                exc_info=True,
            )
            return False

    def generate_embedding(self, text: str, model_name: str) -> List[float]:
        """
        Generate embedding using ONNX Runtime inference.

        Issue #640: Real inference using DirectML for NPU/GPU acceleration.
        """
        if model_name not in self._sessions:
            raise RuntimeError(f"Model {model_name} not loaded. Call load_model() first.")

        tokenizer = self._tokenizers[model_name]
        session = self._sessions[model_name]
        model_config = self._model_configs.get(model_name, {})

        # Tokenize input with fixed max_length for NPU compatibility
        max_length = min(model_config.get("max_length", 512), 512)
        inputs = tokenizer(
            text,
            padding="max_length",
            max_length=max_length,
            truncation=True,
            return_tensors="np",
        )

        # Prepare inputs for ONNX Runtime
        input_ids = inputs["input_ids"].astype(np.int64)
        attention_mask = inputs["attention_mask"].astype(np.int64)

        # Run inference
        ort_inputs = {"input_ids": input_ids, "attention_mask": attention_mask}

        outputs = session.run(None, ort_inputs)

        # Extract embeddings (mean pooling over sequence)
        hidden_states = outputs[0]  # Shape: (batch, seq_len, hidden_dim)
        attention_mask_expanded = attention_mask[:, :, np.newaxis]

        # Mean pooling with attention mask
        sum_embeddings = np.sum(hidden_states * attention_mask_expanded, axis=1)
        sum_mask = np.clip(attention_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        embedding = (sum_embeddings / sum_mask).flatten()

        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.tolist()

    def get_device_info(self) -> Dict[str, Any]:
        """Get information about the selected device and available providers"""
        try:
            self._initialize_onnx_runtime()

            # Get the full device name for the selected device
            selected_full_name = self._device_full_names.get(self._openvino_device, self._selected_device or "Unknown")

            info = {
                "selected_device": self._selected_device or "Unknown",
                "selected_device_full_name": selected_full_name,
                "openvino_device": self._openvino_device,
                "available_providers": self._available_providers,
                "device_priority": [
                    "OpenVINOExecutionProvider (NPU)",
                    "OpenVINOExecutionProvider (GPU)",
                    "DmlExecutionProvider",
                    "CPUExecutionProvider",
                ],
                "is_npu": self._selected_device == "NPU" or self._openvino_device == "NPU",
                "is_gpu": self._selected_device in ["GPU", "DirectML", "CUDA"] or self._openvino_device == "GPU",
                "is_cpu": self._selected_device == "CPU" and self._openvino_device == "CPU",
                "backend": "ONNX Runtime + OpenVINO EP",
                "device_full_names": self._device_full_names,
            }

            # Check OpenVINO EP availability
            if "OpenVINOExecutionProvider" in self._available_providers:
                info["openvino_available"] = True
                info["device_name"] = selected_full_name

                # Try to get detailed device info
                try:
                    from openvino import Core

                    core = Core()
                    info["openvino_devices"] = core.available_devices
                except Exception:
                    info["openvino_devices"] = ["Unknown"]
            else:
                info["openvino_available"] = False
                info["device_name"] = self._selected_device

            # Check DirectML as fallback
            info["directml_available"] = "DmlExecutionProvider" in self._available_providers

            return info

        except Exception as e:
            return {"error": str(e), "selected_device": "UNKNOWN"}


# Alias for backwards compatibility
OpenVINOModelManager = ONNXModelManager


# Global model manager instance with thread-safe initialization (Issue #662)
_model_manager: OpenVINOModelManager | None = None
_model_manager_lock = threading.Lock()


def get_model_manager() -> OpenVINOModelManager:
    """Get or create the global model manager instance (thread-safe)."""
    global _model_manager
    if _model_manager is None:
        with _model_manager_lock:
            # Double-check after acquiring lock
            if _model_manager is None:
                _model_manager = OpenVINOModelManager()
    return _model_manager
