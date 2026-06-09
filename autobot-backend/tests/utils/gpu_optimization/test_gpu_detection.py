# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for GPU detection module. Issue #2243."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from utils.gpu_optimization.gpu_detection import (
    _check_amd_gpu,
    _check_apple_gpu,
    _check_intel_gpu,
    _check_nvidia_gpu,
    _check_sysfs_vendor,
    _detect_amd_capabilities,
    _detect_apple_capabilities,
    _detect_detailed_capabilities,
    _detect_nvidia_capabilities,
    _detect_vendor,
    _get_macos_system_memory_gb,
    _has_tensor_cores,
    _reset_detection_state,
    check_gpu_availability,
    detect_gpu_capabilities,
    get_gpu_capabilities_dict,
)
from utils.gpu_optimization.types import GPUCapabilities


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset cached vendor detection state before each test."""
    _reset_detection_state()
    yield
    _reset_detection_state()


# ---------------------------------------------------------------------------
# _check_nvidia_gpu
# ---------------------------------------------------------------------------
class TestCheckNvidiaGpu:
    """Tests for _check_nvidia_gpu subprocess wrapper."""

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_gpu_name_on_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4070\n",
        )
        assert _check_nvidia_gpu() == "NVIDIA GeForce RTX 4070"

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_none_on_nonzero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _check_nvidia_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_none_on_empty_stdout(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert _check_nvidia_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_none_when_nvidia_smi_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert _check_nvidia_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5)
        assert _check_nvidia_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_none_on_unexpected_exception(self, mock_run):
        mock_run.side_effect = OSError("unexpected")
        assert _check_nvidia_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_first_gpu_selected_with_multiple_gpus(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA A100\nNVIDIA A100\n",
        )
        assert _check_nvidia_gpu() == "NVIDIA A100"


# ---------------------------------------------------------------------------
# _check_amd_gpu
# ---------------------------------------------------------------------------
class TestCheckAmdGpu:
    """Tests for _check_amd_gpu detection."""

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_detected_via_rocm_smi(self, mock_run, _mock_sysfs):
        mock_run.return_value = MagicMock(returncode=0, stdout="GPU[0]")
        assert _check_amd_gpu() is True

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_rocm_smi_failure_falls_back_to_sysfs(self, mock_run, mock_sysfs):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _check_amd_gpu() is False
        mock_sysfs.assert_called_once_with("0x1002")

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=True)
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_sysfs_fallback_detects_amd(self, mock_run, _mock_sysfs):
        mock_run.side_effect = FileNotFoundError
        assert _check_amd_gpu() is True

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_rocm_smi_timeout(self, mock_run, _mock_sysfs):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rocm-smi", timeout=5)
        assert _check_amd_gpu() is False

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_rocm_smi_unexpected_error(self, mock_run, _mock_sysfs):
        mock_run.side_effect = OSError("unexpected")
        assert _check_amd_gpu() is False


# ---------------------------------------------------------------------------
# _check_intel_gpu
# ---------------------------------------------------------------------------
class TestCheckIntelGpu:
    """Tests for _check_intel_gpu detection."""

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=True)
    def test_detected_via_sysfs(self, mock_sysfs):
        assert _check_intel_gpu() is True
        mock_sysfs.assert_called_once_with("0x8086")

    @patch("utils.gpu_optimization.gpu_detection._check_sysfs_vendor", return_value=False)
    def test_not_detected(self, _mock_sysfs):
        assert _check_intel_gpu() is False


# ---------------------------------------------------------------------------
# _check_sysfs_vendor
# ---------------------------------------------------------------------------
class TestCheckSysfsVendor:
    """Tests for _check_sysfs_vendor sysfs traversal."""

    @patch("utils.gpu_optimization.gpu_detection.Path")
    def test_no_drm_path(self, mock_path_cls):
        mock_drm = MagicMock()
        mock_drm.exists.return_value = False
        mock_path_cls.return_value = mock_drm
        assert _check_sysfs_vendor("0x1002") is False

    @patch("utils.gpu_optimization.gpu_detection.Path")
    def test_matching_vendor(self, mock_path_cls):
        mock_drm = MagicMock()
        mock_drm.exists.return_value = True
        card = MagicMock()
        vendor_file = MagicMock()
        vendor_file.exists.return_value = True
        vendor_file.read_text.return_value = "0x1002\n"
        card.__truediv__ = lambda self, key: (
            MagicMock(__truediv__=lambda s, k: vendor_file) if key == "device" else vendor_file
        )
        mock_drm.iterdir.return_value = [card]
        mock_path_cls.return_value = mock_drm
        assert _check_sysfs_vendor("0x1002") is True

    @patch("utils.gpu_optimization.gpu_detection.Path")
    def test_no_matching_vendor(self, mock_path_cls):
        mock_drm = MagicMock()
        mock_drm.exists.return_value = True
        card = MagicMock()
        vendor_file = MagicMock()
        vendor_file.exists.return_value = True
        vendor_file.read_text.return_value = "0x10de\n"
        card.__truediv__ = lambda self, key: (
            MagicMock(__truediv__=lambda s, k: vendor_file) if key == "device" else vendor_file
        )
        mock_drm.iterdir.return_value = [card]
        mock_path_cls.return_value = mock_drm
        assert _check_sysfs_vendor("0x1002") is False

    @patch("utils.gpu_optimization.gpu_detection.Path")
    def test_exception_during_iteration(self, mock_path_cls):
        mock_drm = MagicMock()
        mock_drm.exists.return_value = True
        mock_drm.iterdir.side_effect = PermissionError("no access")
        mock_path_cls.return_value = mock_drm
        assert _check_sysfs_vendor("0x8086") is False


# ---------------------------------------------------------------------------
# _has_tensor_cores
# ---------------------------------------------------------------------------
class TestHasTensorCores:
    """Tests for tensor core detection based on GPU name."""

    @pytest.mark.parametrize(
        "name",
        [
            "NVIDIA GeForce RTX 4070",
            "NVIDIA RTX A6000",
            "NVIDIA A100-SXM4-80GB",
            "NVIDIA H100",
            "NVIDIA H200",
            "NVIDIA L40",
            "NVIDIA L4",
            "Tesla T4",
            "Tesla V100-SXM2-16GB",
            "NVIDIA A10G",
            "NVIDIA A30",
            "NVIDIA A40",
        ],
    )
    def test_gpu_with_tensor_cores(self, name):
        assert _has_tensor_cores(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "NVIDIA GeForce GTX 1080 Ti",
            "NVIDIA GeForce GTX 1660 SUPER",
            "Quadro P6000",
            "",
        ],
    )
    def test_gpu_without_tensor_cores(self, name):
        assert _has_tensor_cores(name) is False

    def test_case_insensitive(self):
        assert _has_tensor_cores("nvidia geforce rtx 4090") is True


# ---------------------------------------------------------------------------
# _detect_vendor (cached)
# ---------------------------------------------------------------------------
class TestDetectVendor:
    """Tests for _detect_vendor with LRU cache."""

    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch(
        "utils.gpu_optimization.gpu_detection._check_nvidia_gpu",
        return_value="RTX 4070",
    )
    def test_nvidia_detected(self, _nv, _amd, _intel):
        assert _detect_vendor() == "nvidia"

    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=True)
    @patch("utils.gpu_optimization.gpu_detection._check_nvidia_gpu", return_value=None)
    def test_amd_detected(self, _nv, _amd, _intel):
        assert _detect_vendor() == "amd"

    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=True)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_nvidia_gpu", return_value=None)
    def test_intel_detected(self, _nv, _amd, _intel):
        assert _detect_vendor() == "intel"

    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_nvidia_gpu", return_value=None)
    def test_no_gpu_detected(self, _nv, _amd, _intel):
        assert _detect_vendor() is None

    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch(
        "utils.gpu_optimization.gpu_detection._check_nvidia_gpu",
        return_value="RTX 4070",
    )
    def test_nvidia_priority_over_amd(self, _nv, _amd, _intel):
        """NVIDIA is checked first; if found, AMD/Intel are not queried."""
        assert _detect_vendor() == "nvidia"

    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch(
        "utils.gpu_optimization.gpu_detection._check_nvidia_gpu",
        return_value="RTX 4070",
    )
    def test_caching(self, mock_nv, _amd, _intel):
        """Second call should use cached result."""
        assert _detect_vendor() == "nvidia"
        assert _detect_vendor() == "nvidia"
        mock_nv.assert_called_once()

    @patch(
        "utils.gpu_optimization.gpu_detection._check_nvidia_gpu",
        return_value="RTX 4070",
    )
    def test_stashes_nvidia_name(self, _mock):
        """_detect_vendor stashes GPU name in module-level _nvidia_gpu_name."""
        import utils.gpu_optimization.gpu_detection as mod

        _detect_vendor()
        assert mod._nvidia_gpu_name == "RTX 4070"


# ---------------------------------------------------------------------------
# _reset_detection_state
# ---------------------------------------------------------------------------
class TestResetDetectionState:
    """Tests for _reset_detection_state."""

    @patch("utils.gpu_optimization.gpu_detection._check_nvidia_gpu", return_value="A100")
    def test_clears_cache_and_name(self, _mock):
        import utils.gpu_optimization.gpu_detection as mod

        _detect_vendor()
        assert mod._nvidia_gpu_name == "A100"

        _reset_detection_state()
        assert mod._nvidia_gpu_name is None
        # Cache is cleared, so next call re-runs detection
        assert _detect_vendor.cache_info().currsize == 0


# ---------------------------------------------------------------------------
# check_gpu_availability
# ---------------------------------------------------------------------------
class TestCheckGpuAvailability:
    """Tests for the public check_gpu_availability function."""

    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value="nvidia")
    def test_available_when_vendor_found(self, _mock):
        assert check_gpu_availability() is True

    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value=None)
    def test_not_available_when_no_vendor(self, _mock):
        assert check_gpu_availability() is False


# ---------------------------------------------------------------------------
# detect_gpu_capabilities
# ---------------------------------------------------------------------------
class TestDetectGpuCapabilities:
    """Tests for detect_gpu_capabilities."""

    def test_no_gpu_returns_defaults(self):
        caps = detect_gpu_capabilities(gpu_available=False)
        assert caps.vendor == "unknown"
        assert caps.name == ""
        assert caps.memory_gb == 0

    @patch("utils.gpu_optimization.gpu_detection._detect_nvidia_capabilities")
    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value="nvidia")
    def test_nvidia_path(self, _vendor, mock_detect):
        expected = GPUCapabilities(vendor="nvidia", name="RTX 4070")
        mock_detect.return_value = expected
        result = detect_gpu_capabilities(gpu_available=True)
        assert result.vendor == "nvidia"
        mock_detect.assert_called_once()

    @patch("utils.gpu_optimization.gpu_detection._detect_amd_capabilities")
    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value="amd")
    def test_amd_path(self, _vendor, mock_detect):
        expected = GPUCapabilities(vendor="amd", name="RX 7900")
        mock_detect.return_value = expected
        result = detect_gpu_capabilities(gpu_available=True)
        assert result.vendor == "amd"
        mock_detect.assert_called_once()

    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value="intel")
    def test_intel_path(self, _vendor):
        result = detect_gpu_capabilities(gpu_available=True)
        assert result.vendor == "intel"
        assert "Intel" in result.name

    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value=None)
    def test_no_vendor_with_gpu_available_true(self, _vendor):
        """Edge case: gpu_available=True but vendor detection fails."""
        result = detect_gpu_capabilities(gpu_available=True)
        assert result.vendor == "unknown"


# ---------------------------------------------------------------------------
# _detect_nvidia_capabilities
# ---------------------------------------------------------------------------
class TestDetectNvidiaCapabilities:
    """Tests for NVIDIA capability detection."""

    @patch("utils.gpu_optimization.gpu_detection._detect_detailed_capabilities")
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_full_detection(self, mock_run, mock_detailed):
        import utils.gpu_optimization.gpu_detection as mod

        mod._nvidia_gpu_name = "NVIDIA GeForce RTX 4070"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="8192, 12.4\n",
        )
        mock_detailed.side_effect = lambda c: c

        caps = GPUCapabilities()
        result = _detect_nvidia_capabilities(caps)

        assert result.vendor == "nvidia"
        assert result.name == "NVIDIA GeForce RTX 4070"
        assert result.memory_gb == 8.0
        assert result.cuda_version == "12.4"
        assert result.tensor_cores is True
        assert result.mixed_precision is True

    @patch("utils.gpu_optimization.gpu_detection._detect_detailed_capabilities")
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_nvidia_smi_failure(self, mock_run, mock_detailed):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        mock_detailed.side_effect = lambda c: c

        caps = GPUCapabilities()
        result = _detect_nvidia_capabilities(caps)
        assert result.vendor == "nvidia"
        assert result.memory_gb == 0

    @patch("utils.gpu_optimization.gpu_detection._detect_detailed_capabilities")
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_nvidia_smi_exception(self, mock_run, mock_detailed):
        mock_run.side_effect = Exception("boom")
        mock_detailed.side_effect = lambda c: c

        caps = GPUCapabilities()
        result = _detect_nvidia_capabilities(caps)
        assert result.vendor == "nvidia"
        assert result.memory_gb == 0

    @patch("utils.gpu_optimization.gpu_detection._detect_detailed_capabilities")
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_fallback_gpu_name_when_stash_is_none(self, mock_run, mock_detailed):
        import utils.gpu_optimization.gpu_detection as mod

        mod._nvidia_gpu_name = None
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="4096, 11.8\n",
        )
        mock_detailed.side_effect = lambda c: c

        caps = GPUCapabilities()
        result = _detect_nvidia_capabilities(caps)
        assert result.name == "NVIDIA GPU"

    @patch("utils.gpu_optimization.gpu_detection._detect_detailed_capabilities")
    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_malformed_csv_output(self, mock_run, mock_detailed):
        """Only one value in CSV line instead of two."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="8192\n",
        )
        mock_detailed.side_effect = lambda c: c

        caps = GPUCapabilities()
        result = _detect_nvidia_capabilities(caps)
        assert result.memory_gb == 0


# ---------------------------------------------------------------------------
# _detect_amd_capabilities
# ---------------------------------------------------------------------------
class TestDetectAmdCapabilities:
    """Tests for AMD capability detection."""

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_full_detection(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "--showproductname" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="GPU[0]: AMD Radeon RX 7900 XTX\n",
                )
            if "--showmeminfo" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="VRAM Total Memory (B): 25165824000\nVRAM total: 24576\n",
                )
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = side_effect
        caps = GPUCapabilities(vendor="amd")
        result = _detect_amd_capabilities(caps)
        assert result.vendor == "amd"
        assert "Radeon" in result.name or "GPU" in result.name

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_rocm_smi_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        caps = GPUCapabilities(vendor="amd")
        result = _detect_amd_capabilities(caps)
        assert result.vendor == "amd"
        assert result.memory_gb == 0

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_rocm_smi_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rocm-smi", timeout=10)
        caps = GPUCapabilities(vendor="amd")
        result = _detect_amd_capabilities(caps)
        assert result.vendor == "amd"

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_memory_parsing_skips_small_values(self, mock_run):
        """Values <= 100 are not treated as memory in MB."""

        def side_effect(cmd, **kwargs):
            if "--showproductname" in cmd:
                return MagicMock(returncode=0, stdout="GPU[0]: test\n")
            if "--showmeminfo" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="VRAM total: 50\n",
                )
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = side_effect
        caps = GPUCapabilities(vendor="amd")
        result = _detect_amd_capabilities(caps)
        assert result.memory_gb == 0


# ---------------------------------------------------------------------------
# _detect_detailed_capabilities (pynvml)
# ---------------------------------------------------------------------------
class TestDetectDetailedCapabilities:
    """Tests for pynvml-based detailed detection."""

    @patch.dict("sys.modules", {"pynvml": MagicMock()})
    def test_pynvml_available(self):
        import sys

        mock_pynvml = sys.modules["pynvml"]
        mock_pynvml.nvmlDeviceGetCudaComputeCapability.return_value = (8, 9)
        mock_pynvml.nvmlDeviceGetMultiProcessorCount.return_value = 46

        caps = GPUCapabilities(vendor="nvidia")
        result = _detect_detailed_capabilities(caps)
        assert result.compute_capability == "8.9"
        assert result.multiprocessor_count == 46

    def test_pynvml_not_installed(self):
        """ImportError is handled gracefully."""
        import builtins

        real_import = builtins.__import__

        def _block_pynvml(name, *args, **kwargs):
            if name == "pynvml":
                raise ImportError("mocked: pynvml not installed")
            return real_import(name, *args, **kwargs)

        with patch.dict("sys.modules", {"pynvml": None}), patch("builtins.__import__", side_effect=_block_pynvml):
            caps = GPUCapabilities(vendor="nvidia")
            result = _detect_detailed_capabilities(caps)
            assert result.compute_capability is None

    @patch.dict("sys.modules", {"pynvml": MagicMock()})
    def test_pynvml_runtime_error(self):
        import sys

        mock_pynvml = sys.modules["pynvml"]
        mock_pynvml.nvmlInit.side_effect = RuntimeError("driver not loaded")

        caps = GPUCapabilities(vendor="nvidia")
        result = _detect_detailed_capabilities(caps)
        assert result.compute_capability is None


# ---------------------------------------------------------------------------
# get_gpu_capabilities_dict
# ---------------------------------------------------------------------------
class TestGetGpuCapabilitiesDict:
    """Tests for the legacy dict interface."""

    @patch("utils.gpu_optimization.gpu_detection.detect_gpu_capabilities")
    def test_returns_dict(self, mock_detect):
        mock_detect.return_value = GPUCapabilities(
            vendor="nvidia",
            name="RTX 4070",
            memory_gb=8.0,
        )
        result = get_gpu_capabilities_dict(gpu_available=True)
        assert isinstance(result, dict)
        assert result["vendor"] == "nvidia"
        assert result["name"] == "RTX 4070"
        assert result["memory_gb"] == 8.0

    @patch("utils.gpu_optimization.gpu_detection.detect_gpu_capabilities")
    def test_no_gpu_returns_defaults(self, mock_detect):
        mock_detect.return_value = GPUCapabilities()
        result = get_gpu_capabilities_dict(gpu_available=False)
        assert result["vendor"] == "unknown"
        assert result["memory_gb"] == 0


# ---------------------------------------------------------------------------
# _check_apple_gpu (Issue #2014)
# ---------------------------------------------------------------------------
class TestCheckAppleGpu:
    """Tests for Apple Silicon GPU detection via system_profiler."""

    @patch("utils.gpu_optimization.gpu_detection.platform.system", return_value="Linux")
    def test_returns_none_on_non_macos(self, _mock):
        assert _check_apple_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    @patch("utils.gpu_optimization.gpu_detection.platform.system", return_value="Darwin")
    def test_detects_apple_m2(self, _mock_sys, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"SPDisplaysDataType": [{"sppci_vendor": "Apple",'
            '"sppci_model": "Apple M2 Pro",'
            '"sppci_cores": "19",'
            '"spdisplays_metal": "spdisplays_metal_supported"}]}',
        )
        result = _check_apple_gpu()
        assert result is not None
        assert result["name"] == "Apple M2 Pro"
        assert result["gpu_cores"] == 19
        assert result["metal_supported"] is True

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    @patch("utils.gpu_optimization.gpu_detection.platform.system", return_value="Darwin")
    def test_returns_none_for_non_apple_gpu_on_mac(self, _mock_sys, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"SPDisplaysDataType": [{"sppci_vendor": "NVIDIA",' '"sppci_model": "GeForce GTX 1080"}]}',
        )
        assert _check_apple_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    @patch("utils.gpu_optimization.gpu_detection.platform.system", return_value="Darwin")
    def test_returns_none_when_system_profiler_fails(self, _mock_sys, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _check_apple_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    @patch("utils.gpu_optimization.gpu_detection.platform.system", return_value="Darwin")
    def test_returns_none_on_timeout(self, _mock_sys, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="system_profiler", timeout=10)
        assert _check_apple_gpu() is None

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    @patch("utils.gpu_optimization.gpu_detection.platform.system", return_value="Darwin")
    def test_handles_missing_cores_field(self, _mock_sys, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"SPDisplaysDataType": [{"sppci_vendor": "Apple",'
            '"sppci_model": "Apple M1",'
            '"spdisplays_metal": "spdisplays_metal_supported"}]}',
        )
        result = _check_apple_gpu()
        assert result is not None
        assert result["gpu_cores"] == 0


# ---------------------------------------------------------------------------
# _detect_apple_capabilities (Issue #2014)
# ---------------------------------------------------------------------------
class TestDetectAppleCapabilities:
    """Tests for Apple Silicon capability population."""

    @patch(
        "utils.gpu_optimization.gpu_detection._get_macos_system_memory_gb",
        return_value=32.0,
    )
    def test_populates_from_stashed_info(self, _mock_mem):
        import utils.gpu_optimization.gpu_detection as mod

        mod._apple_gpu_info = {
            "name": "Apple M2 Max",
            "gpu_cores": 38,
            "metal_supported": True,
        }
        caps = GPUCapabilities()
        result = _detect_apple_capabilities(caps)
        assert result.vendor == "apple"
        assert result.name == "Apple M2 Max"
        assert result.metal_supported is True
        assert result.unified_memory is True
        assert result.mixed_precision is True
        assert result.multiprocessor_count == 38
        assert result.memory_gb == 32.0

    @patch(
        "utils.gpu_optimization.gpu_detection._get_macos_system_memory_gb",
        return_value=0.0,
    )
    def test_fallback_when_no_stashed_info(self, _mock_mem):
        import utils.gpu_optimization.gpu_detection as mod

        mod._apple_gpu_info = None
        caps = GPUCapabilities()
        result = _detect_apple_capabilities(caps)
        assert result.vendor == "apple"
        assert result.name == "Apple GPU"


# ---------------------------------------------------------------------------
# _get_macos_system_memory_gb (Issue #2014)
# ---------------------------------------------------------------------------
class TestGetMacosSystemMemoryGb:
    """Tests for macOS system memory detection."""

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_memory_in_gb(self, mock_run):
        # 16 GB in bytes
        mock_run.return_value = MagicMock(returncode=0, stdout="17179869184\n")
        assert _get_macos_system_memory_gb() == 16.0

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_zero_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _get_macos_system_memory_gb() == 0.0

    @patch("utils.gpu_optimization.gpu_detection.subprocess.run")
    def test_returns_zero_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sysctl", timeout=5)
        assert _get_macos_system_memory_gb() == 0.0


# ---------------------------------------------------------------------------
# detect_gpu_capabilities — Apple path (Issue #2014)
# ---------------------------------------------------------------------------
class TestDetectGpuCapabilitiesApple:
    """Tests for Apple path in detect_gpu_capabilities."""

    @patch("utils.gpu_optimization.gpu_detection._detect_apple_capabilities")
    @patch("utils.gpu_optimization.gpu_detection._detect_vendor", return_value="apple")
    def test_apple_path(self, _vendor, mock_detect):
        expected = GPUCapabilities(vendor="apple", name="Apple M3 Pro")
        mock_detect.return_value = expected
        result = detect_gpu_capabilities(gpu_available=True)
        assert result.vendor == "apple"
        mock_detect.assert_called_once()


# ---------------------------------------------------------------------------
# _detect_vendor — Apple (Issue #2014)
# ---------------------------------------------------------------------------
class TestDetectVendorApple:
    """Tests for Apple vendor detection in _detect_vendor."""

    @patch("utils.gpu_optimization.gpu_detection._check_apple_gpu")
    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_nvidia_gpu", return_value=None)
    def test_apple_detected(self, _nv, _amd, _intel, mock_apple):
        mock_apple.return_value = {
            "name": "Apple M2",
            "gpu_cores": 10,
            "metal_supported": True,
        }
        assert _detect_vendor() == "apple"

    @patch("utils.gpu_optimization.gpu_detection._check_apple_gpu", return_value=None)
    @patch("utils.gpu_optimization.gpu_detection._check_intel_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_amd_gpu", return_value=False)
    @patch("utils.gpu_optimization.gpu_detection._check_nvidia_gpu", return_value=None)
    def test_no_apple_no_gpu(self, _nv, _amd, _intel, _apple):
        assert _detect_vendor() is None
