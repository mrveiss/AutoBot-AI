# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for worker_node partial-forward handler (MVA-1098)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

# Ensure the workers package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from workers.worker_node import (
    _logits_to_token_ids,
    detect_capabilities,
    handle_partial_forward,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Layer:
    """Minimal callable layer that appends its index to a list."""

    def __init__(self, idx: int) -> None:
        self._idx = idx

    def __call__(self, hidden: Any) -> Any:
        if isinstance(hidden, dict):
            result = dict(hidden)
            result.setdefault("layers_run", []).append(self._idx)
            return result
        return hidden


class _MockModelLoader:
    """Mock model loader with a fixed set of layers."""

    def __init__(self, num_layers: int) -> None:
        self._layers = [_Layer(i) for i in range(num_layers)]

    def get_layers(self, model_id: str) -> List[_Layer]:
        return self._layers


# ---------------------------------------------------------------------------
# handle_partial_forward — layer-range slicing
# ---------------------------------------------------------------------------


class TestHandlePartialForward:
    def test_runs_only_specified_layers(self):
        loader = _MockModelLoader(num_layers=16)
        result = handle_partial_forward(
            model_id="test-model",
            layer_range=(4, 7),
            hidden_state_in={"layers_run": []},
            model_loader=loader,
        )
        assert result["hidden_state_out"]["layers_run"] == [4, 5, 6, 7]

    def test_single_layer_range(self):
        loader = _MockModelLoader(num_layers=4)
        result = handle_partial_forward(
            model_id="test-model",
            layer_range=(2, 2),
            hidden_state_in={"layers_run": []},
            model_loader=loader,
        )
        assert result["hidden_state_out"]["layers_run"] == [2]

    def test_full_range(self):
        loader = _MockModelLoader(num_layers=4)
        result = handle_partial_forward(
            model_id="test-model",
            layer_range=(0, 3),
            hidden_state_in={"layers_run": []},
            model_loader=loader,
        )
        assert result["hidden_state_out"]["layers_run"] == [0, 1, 2, 3]

    def test_invalid_range_raises(self):
        loader = _MockModelLoader(num_layers=4)
        with pytest.raises(ValueError, match="Invalid layer_range"):
            handle_partial_forward(
                model_id="test-model",
                layer_range=(3, 1),  # end < start
                hidden_state_in={},
                model_loader=loader,
            )

    def test_out_of_bounds_range_raises(self):
        loader = _MockModelLoader(num_layers=4)
        with pytest.raises(ValueError, match="exceeds model depth"):
            handle_partial_forward(
                model_id="test-model",
                layer_range=(0, 99),
                hidden_state_in={},
                model_loader=loader,
            )

    def test_hidden_state_passthrough_between_stages(self):
        """Verify output of one stage feeds directly into the next."""
        loader = _MockModelLoader(num_layers=8)
        stage1 = handle_partial_forward(
            model_id="test-model",
            layer_range=(0, 3),
            hidden_state_in={"layers_run": []},
            model_loader=loader,
        )
        stage2 = handle_partial_forward(
            model_id="test-model",
            layer_range=(4, 7),
            hidden_state_in=stage1["hidden_state_out"],
            model_loader=loader,
        )
        assert stage2["hidden_state_out"]["layers_run"] == [0, 1, 2, 3, 4, 5, 6, 7]


# ---------------------------------------------------------------------------
# handle_partial_forward — last worker produces token IDs
# ---------------------------------------------------------------------------


class TestHandlePartialForwardLastWorker:
    def _loader_with_logit_output(self, logits):
        """Loader whose last layer returns raw logits."""

        class _LogitLayer:
            def __call__(self, hidden):
                return logits

        class _Loader:
            def get_layers(self, model_id):
                return [_LogitLayer()]

        return _Loader()

    def test_last_worker_returns_token_ids_not_hidden_state(self):
        logits = [0.1, 0.9, 0.3]  # argmax → 1
        loader = self._loader_with_logit_output(logits)
        result = handle_partial_forward(
            model_id="test-model",
            layer_range=(0, 0),
            hidden_state_in={},
            model_loader=loader,
            is_last_worker=True,
        )
        assert "token_ids" in result
        assert "hidden_state_out" not in result
        assert result["token_ids"] == [1]

    def test_intermediate_worker_returns_hidden_state(self):
        loader = _MockModelLoader(num_layers=4)
        result = handle_partial_forward(
            model_id="test-model",
            layer_range=(0, 1),
            hidden_state_in={"layers_run": []},
            model_loader=loader,
            is_last_worker=False,
        )
        assert "hidden_state_out" in result
        assert "token_ids" not in result


# ---------------------------------------------------------------------------
# _logits_to_token_ids
# ---------------------------------------------------------------------------


class TestLogitsToTokenIds:
    def test_plain_list_1d(self):
        assert _logits_to_token_ids([0.1, 0.5, 0.9, 0.2]) == [2]

    def test_numpy_1d(self):
        np = pytest.importorskip("numpy")
        logits = np.array([0.1, 0.9, 0.3])
        assert _logits_to_token_ids(logits) == [1]

    def test_numpy_2d_batch(self):
        np = pytest.importorskip("numpy")
        logits = np.array([[0.1, 0.9, 0.3], [0.8, 0.1, 0.2]])
        ids = _logits_to_token_ids(logits)
        assert ids == [1, 0]

    def test_numpy_3d_seq(self):
        np = pytest.importorskip("numpy")
        # (batch=1, seq=2, vocab=3) — take last position
        logits = np.zeros((1, 2, 3))
        logits[0, -1, 2] = 1.0
        ids = _logits_to_token_ids(logits)
        assert ids == [2]


# ---------------------------------------------------------------------------
# detect_capabilities
# ---------------------------------------------------------------------------


class TestDetectCapabilities:
    def test_returns_required_keys(self):
        caps = detect_capabilities()
        assert "max_layers" in caps
        assert "vram_bytes_per_layer" in caps
        assert "device" in caps

    def test_values_are_positive(self):
        caps = detect_capabilities()
        assert caps["max_layers"] > 0
        assert caps["vram_bytes_per_layer"] > 0

    def test_model_registry_influences_per_layer_cost(self):
        registry = {
            "llama-7b": {"total_bytes": 1024, "num_layers": 32},
        }
        caps = detect_capabilities(model_registry=registry)
        assert caps["vram_bytes_per_layer"] == 1024 // 32

    def test_empty_registry_uses_fallback(self):
        from workers.worker_node import _VRAM_BYTES_PER_LAYER_FALLBACK

        caps = detect_capabilities(model_registry={})
        assert caps["vram_bytes_per_layer"] == _VRAM_BYTES_PER_LAYER_FALLBACK
