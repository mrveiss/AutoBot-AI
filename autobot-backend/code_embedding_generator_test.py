# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for CodeEmbeddingGenerator - Issue #3290.

Covers:
- OpenVINO model compiles on NPU when NPU is in available devices
- _compute_with_openvino returns actual compiled device label
- CPU fallback is used when OpenVINO conversion fails
- batch_generate uses single batched NPU inference when openvino_model is set
- get_stats exposes compiled_device and npu_utilization_reported fields
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from code_embedding_generator import CodeEmbeddingGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generator() -> CodeEmbeddingGenerator:
    """Build a CodeEmbeddingGenerator without touching real hardware."""
    with (
        patch("code_embedding_generator.WorkerNode"),
        patch("code_embedding_generator.get_embedding_cache", return_value=MagicMock()),
    ):
        gen = CodeEmbeddingGenerator()
    gen.embedding_cache = MagicMock()
    gen.embedding_cache.get = AsyncMock(return_value=None)
    gen.embedding_cache.put = AsyncMock()
    gen.embedding_cache.get_stats = MagicMock(return_value={"hits": 0})
    return gen


# ---------------------------------------------------------------------------
# Tests: _convert_to_openvino device selection
# ---------------------------------------------------------------------------


def test_convert_to_openvino_selects_npu_when_available():
    """_convert_to_openvino must compile on NPU when NPU is in available_devices."""
    import sys

    gen = _make_generator()
    gen.model = MagicMock()
    gen.model.train = MagicMock()
    gen.tokenizer = MagicMock()

    mock_core_instance = MagicMock()
    mock_core_instance.available_devices = ["CPU", "GPU", "NPU"]
    mock_compiled = MagicMock()
    mock_core_instance.compile_model.return_value = mock_compiled

    mock_ov_model = MagicMock()
    mock_core_cls = MagicMock(return_value=mock_core_instance)
    mock_convert = MagicMock(return_value=mock_ov_model)

    # Stub the openvino submodules so the local imports inside the method resolve
    mock_ov = MagicMock()
    mock_ov.convert_model = mock_convert
    mock_ov_runtime = MagicMock()
    mock_ov_runtime.Core = mock_core_cls

    with patch.dict(
        sys.modules,
        {"openvino": mock_ov, "openvino.runtime": mock_ov_runtime},
    ):
        gen._convert_to_openvino()

    assert gen._openvino_device == "npu"
    assert gen.openvino_model is mock_compiled
    mock_core_instance.compile_model.assert_called_once_with(mock_ov_model, "NPU")


def test_convert_to_openvino_falls_back_to_cpu_on_error():
    """When OpenVINO conversion raises, npu_available must be False and model None."""
    import sys

    gen = _make_generator()
    gen.model = MagicMock()
    gen.model.train = MagicMock()
    gen.npu_available = True

    mock_ov = MagicMock()
    mock_ov.convert_model = MagicMock(side_effect=RuntimeError("ov fail"))
    mock_ov_runtime = MagicMock()
    mock_ov_runtime.Core = MagicMock(side_effect=RuntimeError("ov fail"))

    with patch.dict(sys.modules, {"openvino": mock_ov, "openvino.runtime": mock_ov_runtime}):
        gen._convert_to_openvino()

    assert gen.openvino_model is None
    assert gen.npu_available is False
    assert gen._openvino_device == "cpu"


# ---------------------------------------------------------------------------
# Tests: _compute_with_openvino returns correct device
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_with_openvino_returns_compiled_device():
    """_compute_with_openvino must return _openvino_device as device label."""
    gen = _make_generator()
    gen._openvino_device = "npu"

    dummy_embedding = np.ones(768, dtype=np.float32)
    mock_model = MagicMock()
    # Simulate result[0] shape (1, seq_len, hidden_dim)
    mock_model.return_value = [np.ones((1, 512, 768), dtype=np.float32)]
    gen.openvino_model = mock_model

    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": np.zeros((1, 512), dtype=np.int64),
        "attention_mask": np.ones((1, 512), dtype=np.int64),
    }
    gen.tokenizer = mock_tokenizer

    embedding, device = await gen._compute_with_openvino("def foo(): pass")

    assert device == "npu"
    assert embedding.shape == (768,)


@pytest.mark.asyncio
async def test_compute_with_openvino_returns_gpu_device_label():
    """When compiled on GPU, device label must be 'gpu', not 'npu'."""
    gen = _make_generator()
    gen._openvino_device = "gpu"

    mock_model = MagicMock()
    mock_model.return_value = [np.ones((1, 512, 768), dtype=np.float32)]
    gen.openvino_model = mock_model

    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": np.zeros((1, 512), dtype=np.int64),
        "attention_mask": np.ones((1, 512), dtype=np.int64),
    }
    gen.tokenizer = mock_tokenizer

    _, device = await gen._compute_with_openvino("x = 1")
    assert device == "gpu"


# ---------------------------------------------------------------------------
# Tests: batch_generate NPU path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_generate_uses_single_batched_inference_on_npu():
    """batch_generate must call _batch_compute_with_openvino once per batch."""
    gen = _make_generator()
    gen.initialized = True
    gen.openvino_model = MagicMock()  # non-None triggers NPU batch path
    gen._openvino_device = "npu"

    fake_embedding = np.ones(768, dtype=np.float32)
    batched_pairs = [(fake_embedding, "npu"), (fake_embedding, "npu")]

    with patch.object(
        gen,
        "_batch_compute_with_openvino",
        new=AsyncMock(return_value=batched_pairs),
    ) as mock_batch:
        results = await gen.batch_generate(
            [("def foo(): pass", "python"), ("class Bar: pass", "python")],
            batch_size=8,
        )

    mock_batch.assert_called_once()
    assert len(results) == 2
    assert all(r.device_used == "npu" for r in results)


@pytest.mark.asyncio
async def test_batch_generate_falls_back_to_serial_without_openvino():
    """Without openvino_model, batch_generate must call generate_embedding per item."""
    gen = _make_generator()
    gen.initialized = True
    gen.openvino_model = None  # no OpenVINO → serial path

    dummy_result = MagicMock()
    dummy_result.device_used = "cpu"

    with patch.object(
        gen,
        "generate_embedding",
        new=AsyncMock(return_value=dummy_result),
    ) as mock_single:
        results = await gen.batch_generate(
            [("def foo(): pass", "python"), ("class Bar: pass", "python")],
            batch_size=8,
        )

    assert mock_single.call_count == 2
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Tests: get_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_reports_npu_utilization_when_on_npu():
    """get_stats must set npu_utilization_reported=True when compiled on NPU."""
    gen = _make_generator()
    gen.initialized = True
    gen.npu_available = True
    gen.gpu_available = False
    gen.openvino_model = MagicMock()
    gen._openvino_device = "npu"

    stats = await gen.get_stats()

    assert stats["compiled_device"] == "npu"
    assert stats["npu_utilization_reported"] is True


@pytest.mark.asyncio
async def test_get_stats_no_npu_utilization_on_cpu_fallback():
    """get_stats must set npu_utilization_reported=False when using CPU PyTorch."""
    gen = _make_generator()
    gen.initialized = True
    gen.npu_available = False
    gen.gpu_available = False
    gen.openvino_model = None
    gen._openvino_device = "cpu"

    stats = await gen.get_stats()

    assert stats["compiled_device"] == "pytorch"
    assert stats["npu_utilization_reported"] is False
