# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for hardware detection. Issue #1950."""

from unittest.mock import patch

from llm_shared.hardware import HardwareDetector


class TestHardwareDetector:
    """Test that hardware detection uses real checks, not placeholders."""

    @patch("llm_shared.hardware.TORCH_AVAILABLE", False)
    def test_no_torch_no_cuda(self):
        detector = HardwareDetector()
        detected = detector.detect_hardware()
        assert "cuda" not in detected
        assert "cpu" in detected

    @patch("llm_shared.hardware.TORCH_AVAILABLE", False)
    @patch.dict("sys.modules", {"openvino": None})
    def test_no_false_positive_openvino_without_library(self):
        """No openvino_npu/intel_arc when openvino not installed."""
        detector = HardwareDetector()
        detected = detector.detect_hardware()
        assert "openvino_npu" not in detected
        assert "intel_arc" not in detected

    @patch("llm_shared.hardware.TORCH_AVAILABLE", True)
    @patch("llm_shared.hardware.torch")
    def test_cuda_detected_when_available(self, mock_torch):
        mock_torch.cuda.is_available.return_value = True
        detector = HardwareDetector()
        detected = detector.detect_hardware()
        assert "cuda" in detected

    def test_always_has_cpu(self):
        detector = HardwareDetector()
        result = detector.detect_hardware()
        assert isinstance(result, set)
        assert "cpu" in result

    def test_select_backend_returns_string(self):
        detector = HardwareDetector()
        result = detector.select_backend()
        assert isinstance(result, str)
        assert result != ""
