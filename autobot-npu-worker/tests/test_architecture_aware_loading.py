"""
End-to-end tests for architecture-aware model loading (GH#7352, MVA-1383).

Covers:
- load_model forwards architecture_family in the HTTP payload
- load_model omits architecture_family when not provided (backward compat)
- Worker dispatch: transformer family uses openvino_transformer backend
- Worker dispatch: ssm family uses openvino_ssm backend (NPU_SSM_ENABLED=true)
- Worker dispatch: ssm family raises UnsupportedArchitectureError when flag off
- Worker dispatch: unsupported families always raise UnsupportedArchitectureError
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the npu-worker packages are importable from test context
_npu_root = Path(__file__).parent.parent
_core_path = _npu_root / "core"
_workers_path = _npu_root / "workers"
for _p in (_npu_root, _core_path, _workers_path):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from openvino_dispatch import (  # noqa: E402
    ArchitectureFamily,
    InferenceEngine,
    UnsupportedArchitectureError,
    get_inference_config,
    get_inference_engine,
    is_npu_ssm_enabled,
)

# ---------------------------------------------------------------------------
# Unit tests: openvino_dispatch.get_inference_config
# ---------------------------------------------------------------------------


class TestGetInferenceConfig:
    """Tests for get_inference_config dispatch logic."""

    def test_transformer_family_accepted(self):
        cfg = get_inference_config("my-model", "transformer", device="CPU")
        assert cfg["architecture_family"] == "transformer"
        assert cfg["inference_backend"] == "openvino_transformer"
        assert cfg["model_id"] == "my-model"
        assert cfg["device"] == "CPU"

    def test_none_family_defaults_to_transformer(self):
        """Omitting architecture_family must fall back to transformer path."""
        cfg = get_inference_config("my-model", None)
        assert cfg["architecture_family"] == "transformer"
        assert cfg["inference_backend"] == "openvino_transformer"

    def test_unsupported_family_raises_structured_error(self):
        with pytest.raises(UnsupportedArchitectureError) as exc_info:
            get_inference_config("my-model", "state_space")
        err = exc_info.value
        assert err.family == "state_space"
        assert "state_space" in str(err)
        assert "transformer" in str(err)

    def test_unsupported_linear_attention_raises(self):
        with pytest.raises(UnsupportedArchitectureError) as exc_info:
            get_inference_config("my-model", "linear_attention")
        assert exc_info.value.family == "linear_attention"

    def test_unsupported_hybrid_raises(self):
        with pytest.raises(UnsupportedArchitectureError) as exc_info:
            get_inference_config("my-model", "hybrid")
        assert exc_info.value.family == "hybrid"

    def test_unknown_family_raises(self):
        with pytest.raises(UnsupportedArchitectureError):
            get_inference_config("my-model", "banana")

    def test_device_is_forwarded(self):
        cfg = get_inference_config("my-model", "transformer", device="NPU")
        assert cfg["device"] == "NPU"

    # -------------------------------------------------------------------
    # SSM family — feature flag gating (MVA-1383)
    # -------------------------------------------------------------------

    def test_ssm_family_raises_when_flag_disabled(self):
        """ssm must raise UnsupportedArchitectureError when NPU_SSM_ENABLED is off."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NPU_SSM_ENABLED", None)
            with pytest.raises(UnsupportedArchitectureError) as exc_info:
                get_inference_config("mamba-370m", "ssm")
            assert exc_info.value.family == "ssm"

    def test_ssm_family_accepted_when_flag_enabled(self):
        """ssm must resolve to openvino_ssm backend when NPU_SSM_ENABLED=true."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            cfg = get_inference_config("mamba-370m", "ssm", device="NPU")
        assert cfg["architecture_family"] == "ssm"
        assert cfg["inference_backend"] == "openvino_ssm"
        assert cfg["model_id"] == "mamba-370m"
        assert cfg["device"] == "NPU"

    def test_ssm_flag_accepts_numeric_one(self):
        """NPU_SSM_ENABLED=1 must also enable the SSM path."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "1"}):
            cfg = get_inference_config("mamba-130m", "ssm")
        assert cfg["inference_backend"] == "openvino_ssm"

    def test_ssm_flag_rejects_false_string(self):
        """NPU_SSM_ENABLED=false must keep the SSM path disabled."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "false"}):
            with pytest.raises(UnsupportedArchitectureError):
                get_inference_config("mamba-130m", "ssm")

    def test_transformer_unaffected_by_ssm_flag(self):
        """Enabling NPU_SSM_ENABLED must not change transformer dispatch."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            cfg = get_inference_config("llama-7b", "transformer")
        assert cfg["inference_backend"] == "openvino_transformer"


# ---------------------------------------------------------------------------
# Unit tests: is_npu_ssm_enabled helper
# ---------------------------------------------------------------------------


class TestIsNpuSsmEnabled:
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NPU_SSM_ENABLED", None)
            assert is_npu_ssm_enabled() is False

    def test_enabled_by_true(self):
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            assert is_npu_ssm_enabled() is True

    def test_enabled_by_1(self):
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "1"}):
            assert is_npu_ssm_enabled() is True

    def test_enabled_by_yes(self):
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "yes"}):
            assert is_npu_ssm_enabled() is True

    def test_disabled_by_false(self):
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "false"}):
            assert is_npu_ssm_enabled() is False

    def test_disabled_by_0(self):
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "0"}):
            assert is_npu_ssm_enabled() is False


# ---------------------------------------------------------------------------
# Integration-style tests: NPUWorkerClient.load_model HTTP payload
# ---------------------------------------------------------------------------


class TestNPUWorkerClientLoadModel:
    """
    Tests for NPUWorkerClient.load_model to verify the HTTP payload
    carries architecture_family when supplied (GH#7352).
    """

    def _make_client(self):
        # Import here so path manipulation above has already happened.
        from npu_integration import NPUWorkerClient

        client = NPUWorkerClient(npu_endpoint="http://test-worker:8001", use_auth=False)
        return client

    def _mock_response(self, data: Dict[str, Any]) -> MagicMock:
        response = AsyncMock()
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=None)
        response.json = AsyncMock(return_value=data)
        return response

    @pytest.mark.asyncio
    async def test_load_model_with_transformer_family_forwards_field(self):
        """architecture_family=transformer must appear in the POST payload."""
        client = self._make_client()
        expected_response = {"success": True, "model_id": "bert-base"}
        captured_calls = []

        async def fake_post(url, json=None, **kwargs):
            captured_calls.append({"url": url, "json": json})
            return self._mock_response(expected_response)

        mock_http = MagicMock()
        mock_http.post = fake_post
        client._http_client = mock_http

        result = await client.load_model(
            model_id="bert-base",
            device="CPU",
            architecture_family="transformer",
        )

        assert result == expected_response
        assert len(captured_calls) == 1
        payload = captured_calls[0]["json"]
        assert payload["architecture_family"] == "transformer"
        assert payload["model_id"] == "bert-base"
        assert payload["device"] == "CPU"

    @pytest.mark.asyncio
    async def test_load_model_without_family_omits_field(self):
        """Omitting architecture_family must not inject the field (backward compat)."""
        client = self._make_client()
        captured_calls = []

        async def fake_post(url, json=None, **kwargs):
            captured_calls.append({"url": url, "json": json})
            return self._mock_response({"success": True})

        mock_http = MagicMock()
        mock_http.post = fake_post
        client._http_client = mock_http

        await client.load_model(model_id="gpt2", device="CPU")

        payload = captured_calls[0]["json"]
        assert "architecture_family" not in payload

    @pytest.mark.asyncio
    async def test_load_model_ssm_family_forwards_field(self):
        """architecture_family=ssm must be forwarded in the POST payload (MVA-1383)."""
        client = self._make_client()
        expected_response = {"success": True, "model_id": "mamba-370m"}
        captured_calls = []

        async def fake_post(url, json=None, **kwargs):
            captured_calls.append({"url": url, "json": json})
            return self._mock_response(expected_response)

        mock_http = MagicMock()
        mock_http.post = fake_post
        client._http_client = mock_http

        result = await client.load_model(
            model_id="mamba-370m",
            device="NPU",
            architecture_family="ssm",
        )

        assert result == expected_response
        payload = captured_calls[0]["json"]
        assert payload["architecture_family"] == "ssm"
        assert payload["model_id"] == "mamba-370m"
        assert payload["device"] == "NPU"

    @pytest.mark.asyncio
    async def test_load_model_unsupported_family_returns_clean_error(self):
        """
        Worker-side: when the HTTP response signals an unsupported architecture,
        the client should propagate it without masking.

        This simulates what happens when the worker side calls get_inference_config
        and returns a structured 422 body. The client does not interpret the payload
        itself; it returns the raw JSON — the caller decides how to handle it.
        """
        client = self._make_client()
        worker_error_response = {
            "success": False,
            "error": "architecture_family 'ssm' is not supported on this OpenVINO worker.",
            "error_code": "unsupported_architecture",
        }

        async def fake_post(url, json=None, **kwargs):
            return self._mock_response(worker_error_response)

        mock_http = MagicMock()
        mock_http.post = fake_post
        client._http_client = mock_http

        result = await client.load_model(
            model_id="mamba-370m",
            device="NPU",
            architecture_family="ssm",
        )

        assert result["success"] is False
        assert "ssm" in result["error"]
        assert result.get("error_code") == "unsupported_architecture"


# ---------------------------------------------------------------------------
# Unit tests: openvino_dispatch.get_inference_engine (GH#8690)
# ---------------------------------------------------------------------------


class TestGetInferenceEngine:
    """Tests for get_inference_engine — the InferenceEngine factory (GH#8690)."""

    def test_returns_inference_engine_instance(self):
        engine = get_inference_engine("m", "transformer")
        assert isinstance(engine, InferenceEngine)

    def test_fields_match_get_inference_config(self):
        cfg = get_inference_config("bert", "transformer", device="NPU")
        engine = get_inference_engine("bert", "transformer", device="NPU")
        assert engine.model_id == cfg["model_id"]
        assert engine.device == cfg["device"]
        assert engine.architecture_family == cfg["architecture_family"]
        assert engine.inference_backend == cfg["inference_backend"]

    def test_none_family_defaults_to_transformer(self):
        engine = get_inference_engine("m", None)
        assert engine.architecture_family == "transformer"
        assert engine.inference_backend == "openvino_transformer"

    def test_unsupported_family_raises(self):
        with pytest.raises(UnsupportedArchitectureError):
            get_inference_engine("m", "state_space")

    def test_ssm_raises_when_flag_disabled(self):
        """SSM path must be gated by NPU_SSM_ENABLED (MVA-1383)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NPU_SSM_ENABLED", None)
            with pytest.raises(UnsupportedArchitectureError) as exc_info:
                get_inference_engine("mamba-370m", "ssm")
            assert exc_info.value.family == "ssm"

    def test_ssm_engine_accepted_when_flag_enabled(self):
        """ssm must yield openvino_ssm backend when NPU_SSM_ENABLED=true (MVA-1383)."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            engine = get_inference_engine("mamba-370m", "ssm", device="NPU")
        assert isinstance(engine, InferenceEngine)
        assert engine.architecture_family == "ssm"
        assert engine.inference_backend == "openvino_ssm"
        assert engine.device == "NPU"

    def test_ssm_engine_invokes_run_layer(self):
        """SSM engine must invoke run_layer for each layer when forward() called."""
        invoked_layers = []

        def spy_run_layer(layer, hidden):
            invoked_layers.append(layer)
            return layer(hidden)

        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            engine = get_inference_engine("mamba-370m", "ssm", run_layer=spy_run_layer)

        layers = [lambda x: x + 1, lambda x: x * 2]  # noqa: E731
        result = engine.forward(layers, 0)
        assert result == 2  # (0 + 1) * 2
        assert len(invoked_layers) == 2

    def test_custom_run_layer_is_used(self):
        calls = []

        def spy_layer(layer, hidden):
            calls.append((layer, hidden))
            return hidden + 10

        engine = get_inference_engine("m", "transformer", run_layer=spy_layer)
        layers = [object(), object()]
        result = engine.forward(layers, 0)
        assert result == 20
        assert len(calls) == 2

    def test_default_run_layer_calls_layer_directly(self):
        engine = get_inference_engine("m", "transformer")
        layer = lambda x: x * 3  # noqa: E731
        result = engine.run_layer(layer, 4)
        assert result == 12

    def test_forward_chains_layers(self):
        engine = get_inference_engine("m", "transformer")
        layers = [lambda x: x + 1, lambda x: x * 2, lambda x: x - 5]  # noqa: E731
        result = engine.forward(layers, 3)
        assert result == (3 + 1) * 2 - 5  # 3
