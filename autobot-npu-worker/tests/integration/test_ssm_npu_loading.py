# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration test: SSM model loading on NPU worker with OpenVINO SSM kernel (MVA-1383).

Verifies:
- NPUWorkerClient.load_model sends architecture_family=ssm for Mamba checkpoints
- get_inference_engine selects openvino_ssm backend when NPU_SSM_ENABLED=true
- handle_partial_forward invokes the SSM engine for a Mamba model layer range
- SSM kernel path is NOT activated when NPU_SSM_ENABLED is unset (default off)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_npu_root = Path(__file__).parent.parent.parent
_core_path = _npu_root / "core"
_workers_path = _npu_root / "workers"
for _p in (_npu_root, _core_path, _workers_path):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from workers.openvino_dispatch import (  # noqa: E402
    InferenceEngine,
    UnsupportedArchitectureError,
    get_inference_engine,
)
from workers.worker_node import handle_partial_forward  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MambaLayer:
    """Minimal SSM-like layer: accumulates a running state vector."""

    def __init__(self, idx: int) -> None:
        self._idx = idx

    def __call__(self, hidden: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(hidden)
        result.setdefault("ssm_layers_run", []).append(self._idx)
        result["state"] = result.get("state", 0) + self._idx
        return result


class _MambaModelLoader:
    def __init__(self, num_layers: int = 4) -> None:
        self._layers = [_MambaLayer(i) for i in range(num_layers)]

    def get_layers(self, model_id: str) -> List[_MambaLayer]:
        return self._layers


# ---------------------------------------------------------------------------
# Integration: handle_partial_forward with SSM model
# ---------------------------------------------------------------------------


class TestSSMPartialForward:
    """Verify handle_partial_forward routes Mamba layers through the SSM engine."""

    def test_ssm_kernel_invoked_when_flag_enabled(self):
        """SSM engine must be selected and all layers run for architecture_family=ssm."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            loader = _MambaModelLoader(num_layers=4)
            result = handle_partial_forward(
                model_id="mamba-370m",
                layer_range=(0, 3),
                hidden_state_in={"state": 0},
                model_loader=loader,
                architecture_family="ssm",
                device="CPU",
            )

        assert "hidden_state_out" in result
        out = result["hidden_state_out"]
        assert out["ssm_layers_run"] == [0, 1, 2, 3]
        assert out["state"] == 0 + 1 + 2 + 3  # 6

    def test_ssm_kernel_gated_when_flag_disabled(self):
        """handle_partial_forward must raise for ssm when flag is off."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NPU_SSM_ENABLED", None)
            loader = _MambaModelLoader(num_layers=4)
            with pytest.raises(UnsupportedArchitectureError) as exc_info:
                handle_partial_forward(
                    model_id="mamba-370m",
                    layer_range=(0, 3),
                    hidden_state_in={"state": 0},
                    model_loader=loader,
                    architecture_family="ssm",
                    device="CPU",
                )
            assert exc_info.value.family == "ssm"

    def test_ssm_last_worker_produces_token_ids(self):
        """When is_last_worker=True, the SSM path must still run argmax for token IDs."""
        import numpy as np

        class _LogitLayer:
            def __call__(self, hidden: Any) -> Any:
                return np.array([0.1, 0.9, 0.2, 0.05])

        class _LogitLoader:
            def get_layers(self, model_id: str):
                return [_LogitLayer()]

        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            result = handle_partial_forward(
                model_id="mamba-130m",
                layer_range=(0, 0),
                hidden_state_in=None,
                model_loader=_LogitLoader(),
                is_last_worker=True,
                architecture_family="ssm",
                device="CPU",
            )

        assert "token_ids" in result
        assert result["token_ids"] == [1]  # argmax of [0.1, 0.9, 0.2, 0.05]

    def test_transformer_unaffected_when_ssm_flag_on(self):
        """Enabling NPU_SSM_ENABLED must not change transformer model dispatch."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            loader = _MambaModelLoader(num_layers=4)
            result = handle_partial_forward(
                model_id="llama-7b",
                layer_range=(0, 2),
                hidden_state_in={"state": 0},
                model_loader=loader,
                architecture_family="transformer",
                device="CPU",
            )
        assert "hidden_state_out" in result


# ---------------------------------------------------------------------------
# Integration: NPUWorkerClient load_model for Mamba checkpoint
# ---------------------------------------------------------------------------


class TestMambaCheckpointLoading:
    """Verify the client sends the correct payload when loading a Mamba checkpoint."""

    def _make_client(self):
        from npu_integration import NPUWorkerClient

        return NPUWorkerClient(npu_endpoint="http://npu-worker:8001", use_auth=False)

    def _mock_response(self, data: Dict[str, Any]) -> MagicMock:
        response = AsyncMock()
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=None)
        response.json = AsyncMock(return_value=data)
        return response

    @pytest.mark.asyncio
    async def test_mamba_checkpoint_load_sends_ssm_family(self):
        """Loading a Mamba model must send architecture_family=ssm in the HTTP payload."""
        client = self._make_client()
        captured: List[Dict[str, Any]] = []

        async def fake_post(url, json=None, **kwargs):
            captured.append({"url": url, "json": json})
            return self._mock_response({"success": True, "model_id": "mamba-370m"})

        mock_http = MagicMock()
        mock_http.post = fake_post
        client._http_client = mock_http

        result = await client.load_model(
            model_id="mamba-370m",
            device="NPU",
            architecture_family="ssm",
        )

        assert result["success"] is True
        payload = captured[0]["json"]
        assert payload["architecture_family"] == "ssm"
        assert payload["model_id"] == "mamba-370m"
        assert payload["device"] == "NPU"

    @pytest.mark.asyncio
    async def test_ssm_engine_selected_for_mamba_model(self):
        """get_inference_engine must return openvino_ssm for a Mamba model with flag on."""
        with patch.dict(os.environ, {"NPU_SSM_ENABLED": "true"}):
            engine = get_inference_engine("mamba-370m", "ssm", device="NPU")

        assert isinstance(engine, InferenceEngine)
        assert engine.inference_backend == "openvino_ssm"
        assert engine.architecture_family == "ssm"
        assert engine.device == "NPU"
        assert engine.model_id == "mamba-370m"
