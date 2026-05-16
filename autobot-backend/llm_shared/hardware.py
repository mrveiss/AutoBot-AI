# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hardware Detection - Detect and select optimal hardware acceleration backends.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

from typing import List, Set

from autobot_shared.logging_manager import get_logger

from .optimization.model_inspector import ModelInfo, inspect_model

logger = get_logger(__name__)

# Check for PyTorch availability
try:
    import torch

    TORCH_AVAILABLE = True
except (ImportError, RuntimeError):
    logger.warning("PyTorch not available or CUDA libraries missing")
    TORCH_AVAILABLE = False


class HardwareDetector:
    """Detect and select optimal hardware acceleration backends."""

    def __init__(self, priority: List[str] | None = None):
        """
        Initialize hardware detector.

        Args:
            priority: List of hardware priorities in order of preference.
                     Default: ["openvino_npu", "openvino", "cuda", "cpu"]
        """
        self.priority = priority or [
            "openvino_npu",
            "openvino",
            "cuda",
            "cpu",
        ]

    def detect_hardware(self) -> Set[str]:
        """
        Detect available hardware acceleration.

        Returns:
            Set of available hardware types
        """
        detected = set()

        # Check CUDA
        if TORCH_AVAILABLE and torch.cuda.is_available():
            detected.add("cuda")

        # Check CPU (always available)
        detected.add("cpu")

        # Check Intel Arc/NPU via OpenVINO (Issue #1950 — real detection)
        try:
            import openvino as ov

            core = ov.Core()
            devices = core.available_devices
            if "NPU" in devices:
                detected.add("openvino_npu")
                detected.add("openvino")
            if any(d.startswith("GPU") for d in devices):
                detected.add("intel_arc")
                detected.add("openvino")
            elif "CPU" in devices and "openvino" not in detected:
                detected.add("openvino")
        except ImportError:
            logger.debug("OpenVINO not installed — Intel acceleration unavailable")
        except Exception as e:
            logger.debug("OpenVINO detection failed: %s", e)

        return detected

    def select_backend(self) -> str:
        """
        Select optimal backend based on hardware.

        Returns:
            Selected backend name
        """
        detected_hardware = self.detect_hardware()

        for priority in self.priority:
            selected = self._try_backend_selection(priority, detected_hardware)
            if selected:
                return selected

        return "cpu"

    def _try_backend_selection(self, priority: str, detected_hardware: Set[str]) -> str | None:
        """
        Try to select a specific backend.

        Args:
            priority: Backend priority to try
            detected_hardware: Set of detected hardware

        Returns:
            Selected backend name or None
        """
        selectors = {
            "openvino_npu": lambda: self._select_openvino_npu(detected_hardware),
            "openvino": lambda: self._select_openvino_variant(detected_hardware),
            "cuda": lambda: self._select_cuda(detected_hardware),
            "onnxruntime": lambda: self._select_onnxruntime(detected_hardware),
            "cpu": lambda: self._select_cpu(detected_hardware),
        }

        selector = selectors.get(priority)
        if selector:
            return selector()
        return None

    def _select_openvino_npu(self, detected_hardware: Set[str]) -> str | None:
        """Select OpenVINO NPU if available."""
        return "openvino_npu" if "openvino_npu" in detected_hardware else None

    def _select_openvino_variant(self, detected_hardware: Set[str]) -> str | None:
        """Select OpenVINO variant."""
        if "intel_arc" in detected_hardware:
            return "openvino_gpu"
        elif "openvino" in detected_hardware:
            return "openvino_cpu"
        return None

    def _select_cuda(self, detected_hardware: Set[str]) -> str | None:
        """Select CUDA if available."""
        return "cuda" if "cuda" in detected_hardware else None

    def _select_onnxruntime(self, detected_hardware: Set[str]) -> str | None:
        """Select ONNX Runtime."""
        if "cuda" in detected_hardware:
            return "onnxruntime_cuda"
        return "onnxruntime_cpu"

    def _select_cpu(self, detected_hardware: Set[str]) -> str | None:
        """Select CPU backend if available."""
        return "cpu" if "cpu" in detected_hardware else None

    def get_available_vram_gb(self) -> float:
        """
        Return free VRAM in gigabytes for the first CUDA device.

        Returns 0.0 when CUDA is unavailable or no free memory is reported.
        """
        if not TORCH_AVAILABLE:
            return 0.0
        try:
            import torch  # noqa: PLC0415

            if not torch.cuda.is_available():
                return 0.0
            free_bytes, _ = torch.cuda.mem_get_info(0)
            return free_bytes / (1024**3)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not query VRAM: %s", exc)
            return 0.0

    def select_backend_for_model(self, model_name: str) -> str:
        """
        Select optimal backend after verifying the model fits in available VRAM.

        Inspects the model architecture at zero memory cost using
        ``inspect_model()``.  When the estimated fp32 size exceeds free VRAM
        the method falls back to CPU rather than risking an OOM error.

        Args:
            model_name: HuggingFace model ID or local path.

        Returns:
            Selected backend name.
        """
        model_info: ModelInfo | None = inspect_model(model_name)
        preferred = self.select_backend()

        if model_info is None:
            logger.debug(
                "No model info for %s — using default backend %s",
                model_name,
                preferred,
            )
            return preferred

        if preferred in ("cuda", "openvino_gpu"):
            vram_gb = self.get_available_vram_gb()
            if model_info.estimated_size_gb > vram_gb:
                logger.warning(
                    "Model %s requires ~%.1f GB but only %.1f GB VRAM free — " "falling back to cpu",
                    model_name,
                    model_info.estimated_size_gb,
                    vram_gb,
                )
                return "cpu"

        logger.info(
            "Model %s (~%.1f GB) fits — routing to %s",
            model_name,
            model_info.estimated_size_gb,
            preferred,
        )
        return preferred


__all__ = [
    "HardwareDetector",
    "TORCH_AVAILABLE",
    "ModelInfo",
    "inspect_model",
]
