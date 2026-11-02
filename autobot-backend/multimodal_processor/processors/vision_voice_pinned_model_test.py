# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""VisionProcessor/VoiceProcessor model loading resolves a pinned revision (#13034).

``transformers`` isn't installed in this dev environment, and both modules
gate their model class names behind a module-level ``try/except ImportError``
evaluated once at import time -- injecting a fake ``transformers`` module and
reloading is what makes that guard resolve ``True`` here, not a patch on an
already-failed import (same technique as
``ai_hardware_accelerator_pinned_model_test.py``).
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def vision_module():
    fake_transformers = types.ModuleType("transformers")
    for name in ("CLIPModel", "CLIPProcessor", "Blip2Processor", "Blip2ForConditionalGeneration"):
        setattr(fake_transformers, name, MagicMock(name=name))

    saved = sys.modules.get("transformers")
    sys.modules["transformers"] = fake_transformers
    try:
        import multimodal_processor.processors.vision as vision

        importlib.reload(vision)
        assert vision.VISION_MODELS_AVAILABLE is True, "fakes did not satisfy the module's import guard"
        yield vision
    finally:
        if saved is None:
            sys.modules.pop("transformers", None)
        else:
            sys.modules["transformers"] = saved
        importlib.reload(vision)


@pytest.fixture
def voice_module():
    fake_transformers = types.ModuleType("transformers")
    for name in ("Wav2Vec2Processor", "Wav2Vec2ForCTC"):
        setattr(fake_transformers, name, MagicMock(name=name))
    fake_librosa = types.ModuleType("librosa")

    saved_transformers = sys.modules.get("transformers")
    saved_librosa = sys.modules.get("librosa")
    sys.modules["transformers"] = fake_transformers
    sys.modules["librosa"] = fake_librosa
    try:
        import multimodal_processor.processors.voice as voice

        importlib.reload(voice)
        assert voice.AUDIO_MODELS_AVAILABLE is True, "fakes did not satisfy the module's import guard"
        yield voice
    finally:
        if saved_transformers is None:
            sys.modules.pop("transformers", None)
        else:
            sys.modules["transformers"] = saved_transformers
        if saved_librosa is None:
            sys.modules.pop("librosa", None)
        else:
            sys.modules["librosa"] = saved_librosa
        importlib.reload(voice)


def _bare_instance(cls):
    obj = cls.__new__(cls)
    obj.logger = MagicMock()
    obj.device = "cpu"
    return obj


def test_vision_processor_pins_clip_and_blip2_revisions(vision_module):
    proc = _bare_instance(vision_module.VisionProcessor)

    with (
        patch(
            "autobot_shared.pinned_model_registry.get_pinned_revision",
            side_effect=lambda repo_id: {
                "openai/clip-vit-base-patch32": "1" * 40,
                "Salesforce/blip2-opt-2.7b": "2" * 40,
            }[repo_id],
        ) as mock_get,
        patch("autobot_shared.pinned_model_registry.verify_cached_model") as mock_verify,
    ):
        proc._load_models()

    vision_module.CLIPProcessor.from_pretrained.assert_called_once_with(
        "openai/clip-vit-base-patch32", revision="1" * 40, use_fast=True
    )
    assert vision_module.CLIPModel.from_pretrained.call_args.kwargs["revision"] == "1" * 40
    vision_module.Blip2Processor.from_pretrained.assert_called_once_with(
        "Salesforce/blip2-opt-2.7b", revision="2" * 40, use_fast=True
    )
    assert vision_module.Blip2ForConditionalGeneration.from_pretrained.call_args.kwargs["revision"] == "2" * 40
    assert mock_get.call_count == 2
    assert mock_verify.call_args_list == [
        (("openai/clip-vit-base-patch32",),),
        (("Salesforce/blip2-opt-2.7b",),),
    ]


def test_voice_processor_pins_the_wav2vec_revision_and_loads_no_whisper(voice_module):
    """Whisper is the one pinned pipeline's job now (#17778); only Wav2Vec2 loads here."""
    proc = _bare_instance(voice_module.VoiceProcessor)

    with (
        patch(
            "autobot_shared.pinned_model_registry.get_pinned_revision",
            side_effect=lambda repo_id: {"facebook/wav2vec2-base-960h": "4" * 40}[repo_id],
        ) as mock_get,
        patch("autobot_shared.pinned_model_registry.verify_cached_model") as mock_verify,
    ):
        proc._load_models()

    voice_module.Wav2Vec2Processor.from_pretrained.assert_called_once_with(
        "facebook/wav2vec2-base-960h", revision="4" * 40, use_fast=True
    )
    assert voice_module.Wav2Vec2ForCTC.from_pretrained.call_args.kwargs["revision"] == "4" * 40
    assert mock_get.call_count == 1
    assert mock_verify.call_args_list == [(("facebook/wav2vec2-base-960h",),)]
    assert not hasattr(voice_module, "WhisperForConditionalGeneration"), "a second in-process Whisper crept back"


# ---------------------------------------------------------------------------
# #17124 -- fail-open regression: a failed integrity check must never leave
# a tampered model assigned and reachable.
# ---------------------------------------------------------------------------


def test_vision_processor_clip_failure_leaves_both_clip_attrs_none(vision_module):
    from autobot_shared.pinned_model_registry import ModelIntegrityError

    proc = _bare_instance(vision_module.VisionProcessor)
    proc.clip_model = None
    proc.clip_processor = None
    proc.blip_model = None
    proc.blip_processor = None

    with (
        patch("autobot_shared.pinned_model_registry.get_pinned_revision", return_value="1" * 40),
        patch(
            "autobot_shared.pinned_model_registry.verify_cached_model", side_effect=ModelIntegrityError("tampered clip")
        ),
    ):
        proc._load_models()  # must not raise -- caught and logged internally

    assert proc.clip_model is None, "a tampered CLIP model must never be assigned"
    assert proc.clip_processor is None
    assert proc.blip_model is None, "BLIP-2 is never reached when CLIP's own verify fails"
    assert proc.blip_processor is None


def test_vision_processor_blip2_failure_leaves_blip2_none_but_keeps_verified_clip(vision_module):
    from autobot_shared.pinned_model_registry import ModelIntegrityError

    proc = _bare_instance(vision_module.VisionProcessor)
    proc.clip_model = None
    proc.clip_processor = None
    proc.blip_model = None
    proc.blip_processor = None

    with (
        patch("autobot_shared.pinned_model_registry.get_pinned_revision", return_value="1" * 40),
        patch(
            "autobot_shared.pinned_model_registry.verify_cached_model",
            side_effect=[None, ModelIntegrityError("tampered blip2")],
        ),
    ):
        proc._load_models()  # must not raise

    assert proc.clip_model is not None, "CLIP already passed its own verify and must stay usable"
    assert proc.clip_processor is not None
    assert proc.blip_model is None, "a tampered BLIP-2 model must never be assigned"
    assert proc.blip_processor is None


def test_voice_processor_wav2vec_failure_leaves_both_wav2vec_attrs_none(voice_module):
    from autobot_shared.pinned_model_registry import ModelIntegrityError

    proc = _bare_instance(voice_module.VoiceProcessor)
    proc.wav2vec_model = None
    proc.wav2vec_processor = None

    with (
        patch("autobot_shared.pinned_model_registry.get_pinned_revision", return_value="4" * 40),
        patch(
            "autobot_shared.pinned_model_registry.verify_cached_model",
            side_effect=ModelIntegrityError("tampered wav2vec"),
        ),
    ):
        proc._load_models()  # must not raise

    assert proc.wav2vec_model is None, "a tampered Wav2Vec2 model must never be assigned"
    assert proc.wav2vec_processor is None
