# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hardware Detection - Detect and select optimal hardware acceleration backends.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import logging
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Check for PyTorch availability
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    logger.warning("PyTorch not available or CUDA libraries missing")
    TORCH_AVAILABLE = False


class HardwareDetector:
    """Detect and select optimal hardware acceleration backends."""

    def __init__(self, priority: Optional[List[str]] = None):
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

        # Check Intel Arc/NPU (placeholder for future OpenVINO integration)
        try:
            # This would check for Intel Arc graphics and NPU
            detected.add("intel_arc")
            detected.add("openvino")
        except Exception as e:
            logger.debug("Intel Arc/NPU detection unavailable: %s", e)

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

    def _try_backend_selection(
        self, priority: str, detected_hardware: Set[str]
    ) -> Optional[str]:
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

    def _select_openvino_npu(self, detected_hardware: Set[str]) -> Optional[str]:
        """Select OpenVINO NPU if available."""
        return "openvino_npu" if "openvino" in detected_hardware else None

    def _select_openvino_variant(self, detected_hardware: Set[str]) -> Optional[str]:
        """Select OpenVINO variant."""
        if "intel_arc" in detected_hardware:
            return "openvino_gpu"
        elif "openvino" in detected_hardware:
            return "openvino_cpu"
        return None

    def _select_cuda(self, detected_hardware: Set[str]) -> Optional[str]:
        """Select CUDA if available."""
        return "cuda" if "cuda" in detected_hardware else None

    def _select_onnxruntime(self, detected_hardware: Set[str]) -> Optional[str]:
        """Select ONNX Runtime."""
        if "cuda" in detected_hardware:
            return "onnxruntime_cuda"
        return "onnxruntime_cpu"

    def _select_cpu(self, detected_hardware: Set[str]) -> Optional[str]:
        """Select CPU backend if available."""
        return "cpu" if "cpu" in detected_hardware else None


__all__ = [
    "HardwareDetector",
    "TORCH_AVAILABLE",
]
