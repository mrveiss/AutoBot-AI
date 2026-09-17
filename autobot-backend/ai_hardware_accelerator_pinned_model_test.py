# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CLIP/Wav2Vec2 model loading resolves and verifies a pinned revision (#13034).

``transformers``/``librosa`` aren't installed in this dev environment (heavy
ML deps this test doesn't otherwise need), and ``ai_hardware_accelerator.py``
gates its ``CLIPModel``/``CLIPProcessor``/``Wav2Vec2*`` names behind a
module-level ``try/except ImportError`` evaluated once at import time --
injecting fakes into ``sys.modules`` and reloading the module is what makes
that guard resolve ``True`` here, not a patch on an already-failed import.
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def aha_module():
    """ai_hardware_accelerator, reloaded with transformers/librosa faked in."""
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.CLIPModel = MagicMock(name="CLIPModel")  # type: ignore[attr-defined]
    fake_transformers.CLIPProcessor = MagicMock(name="CLIPProcessor")  # type: ignore[attr-defined]
    fake_transformers.Wav2Vec2Model = MagicMock(name="Wav2Vec2Model")  # type: ignore[attr-defined]
    fake_transformers.Wav2Vec2Processor = MagicMock(name="Wav2Vec2Processor")  # type: ignore[attr-defined]
    fake_librosa = types.ModuleType("librosa")

    saved_transformers = sys.modules.get("transformers")
    saved_librosa = sys.modules.get("librosa")
    sys.modules["transformers"] = fake_transformers
    sys.modules["librosa"] = fake_librosa
    try:
        import ai_hardware_accelerator as aha

        importlib.reload(aha)
        assert aha.MULTIMODAL_MODELS_AVAILABLE is True, "fakes did not satisfy the module's import guard"
        yield aha
    finally:
        if saved_transformers is None:
            sys.modules.pop("transformers", None)
        else:
            sys.modules["transformers"] = saved_transformers
        if saved_librosa is None:
            sys.modules.pop("librosa", None)
        else:
            sys.modules["librosa"] = saved_librosa
        importlib.reload(aha)  # restore the module to its real (deps-missing) state for other tests


def test_initialize_clip_model_passes_the_pinned_revision(aha_module):
    accel = aha_module.AIHardwareAccelerator.__new__(aha_module.AIHardwareAccelerator)

    with (
        patch.object(aha_module, "_get_torch", return_value=MagicMock(cuda=MagicMock(is_available=lambda: False))),
        patch(
            "autobot_shared.pinned_model_registry.get_pinned_revision", return_value="deadbeef" * 5
        ) as mock_get,
        patch("autobot_shared.pinned_model_registry.verify_cached_model") as mock_verify,
    ):
        accel._initialize_clip_model(device="cpu")

    mock_get.assert_called_once_with("openai/clip-vit-base-patch32")
    aha_module.CLIPProcessor.from_pretrained.assert_called_once_with(
        "openai/clip-vit-base-patch32", revision="deadbeef" * 5
    )
    assert aha_module.CLIPModel.from_pretrained.call_args.args == ("openai/clip-vit-base-patch32",)
    assert aha_module.CLIPModel.from_pretrained.call_args.kwargs["revision"] == "deadbeef" * 5
    mock_verify.assert_called_once_with("openai/clip-vit-base-patch32")


def test_initialize_wav2vec_model_passes_the_pinned_revision(aha_module):
    accel = aha_module.AIHardwareAccelerator.__new__(aha_module.AIHardwareAccelerator)

    with (
        patch.object(aha_module, "_get_torch", return_value=MagicMock(cuda=MagicMock(is_available=lambda: False))),
        patch(
            "autobot_shared.pinned_model_registry.get_pinned_revision", return_value="cafebabe" * 5
        ) as mock_get,
        patch("autobot_shared.pinned_model_registry.verify_cached_model") as mock_verify,
    ):
        accel._initialize_wav2vec_model(device="cpu")

    mock_get.assert_called_once_with("facebook/wav2vec2-base-960h")
    aha_module.Wav2Vec2Processor.from_pretrained.assert_called_once_with(
        "facebook/wav2vec2-base-960h", revision="cafebabe" * 5
    )
    assert aha_module.Wav2Vec2Model.from_pretrained.call_args.args == ("facebook/wav2vec2-base-960h",)
    assert aha_module.Wav2Vec2Model.from_pretrained.call_args.kwargs["revision"] == "cafebabe" * 5
    mock_verify.assert_called_once_with("facebook/wav2vec2-base-960h")
