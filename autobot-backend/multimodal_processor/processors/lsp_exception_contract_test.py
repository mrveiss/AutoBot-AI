# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#6755 LSP exception contract regression tests.

The cross-file analyzer (#6747) flagged ``VisionProcessor.process`` and
``VoiceProcessor.process`` as ``lsp_exception_contract_changed``: their parent
``BaseModalProcessor.process`` only declares ``NotImplementedError``, but the
subclasses raised ``ValueError`` for unsupported modalities. Liskov
substitution requires subclasses NOT to raise exceptions outside the parent's
declared contract — callers handling only the parent's exception types would
silently miss the ``ValueError`` and crash.

These tests **drive the failure path and assert the returned result**. They
used to read ``inspect.getsource(cls.process)`` and grep for the literals
``success=False`` and ``Unsupported modality``, which guaranteed nothing: the
grep passes when the literal sits in an unreachable branch, and fails on any
refactor that preserves behaviour — it broke the moment the failure result was
extracted into a helper (#13207). An exception-contract test has to observe
what the caller observes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from multimodal_processor.models import MultiModalInput, ProcessingResult
from multimodal_processor.types import ModalityType, ProcessingIntent

# Modalities that reach each processor's *unsupported-modality* branch.
# These differ, and the old source-grep test could never have noticed:
# VisionProcessor accepts VIDEO into its pipeline and fails further in with a
# "not yet implemented" message, so VIDEO is not "unsupported" for vision.
VISION_UNSUPPORTED = [ModalityType.TEXT, ModalityType.COMBINED]
VOICE_UNSUPPORTED = [ModalityType.TEXT, ModalityType.IMAGE, ModalityType.VIDEO, ModalityType.COMBINED]

# Every modality that is not the processor's own — whatever branch handles it,
# the LSP contract is the same: return a result, never raise.
VISION_NON_NATIVE = VISION_UNSUPPORTED + [ModalityType.VIDEO]
VOICE_NON_NATIVE = VOICE_UNSUPPORTED


def _input(modality: ModalityType) -> MultiModalInput:
    return MultiModalInput(
        input_id="lsp-contract",
        modality_type=modality,
        intent=ProcessingIntent.AUTOMATION_TASK,
        data=b"",
        metadata={},
    )


def _build(module, cls_name: str):
    """Construct a processor with torch and model loading stubbed out."""
    cls = getattr(module, cls_name)
    with (
        patch.object(module, "_get_torch", return_value=MagicMock()),
        patch.object(cls, "_load_models", lambda self: None),
    ):
        return cls()


@pytest.fixture
def vision_processor():
    import multimodal_processor.processors.vision as module

    return _build(module, "VisionProcessor")


@pytest.fixture
def voice_processor():
    import multimodal_processor.processors.voice as module

    processor = _build(module, "VoiceProcessor")
    # The unsupported-modality branch must be reachable regardless of whether
    # voice happens to be enabled by configuration.
    processor.enabled = True
    return processor


class TestUnsupportedModalityDegradesInsteadOfRaising:
    """The contract: return a failure result, never raise outside the parent's."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("modality", VISION_UNSUPPORTED)
    async def test_vision_returns_failure_result(self, vision_processor, modality):
        result = await vision_processor.process(_input(modality))

        assert isinstance(result, ProcessingResult)
        assert result.success is False
        assert "Unsupported modality" in result.error_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("modality", VOICE_UNSUPPORTED)
    async def test_voice_returns_failure_result(self, voice_processor, modality):
        result = await voice_processor.process(_input(modality))

        assert isinstance(result, ProcessingResult)
        assert result.success is False
        assert "Unsupported modality" in result.error_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("modality", VISION_NON_NATIVE)
    async def test_vision_does_not_raise(self, vision_processor, modality):
        """A ValueError here is exactly the #6755 defect."""
        try:
            await vision_processor.process(_input(modality))
        except Exception as exc:  # noqa: BLE001 - the assertion is "nothing escapes"
            pytest.fail(f"#6755 regression: VisionProcessor.process raised {type(exc).__name__}: {exc}")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("modality", VOICE_NON_NATIVE)
    async def test_voice_does_not_raise(self, voice_processor, modality):
        try:
            await voice_processor.process(_input(modality))
        except Exception as exc:  # noqa: BLE001 - the assertion is "nothing escapes"
            pytest.fail(f"#6755 regression: VoiceProcessor.process raised {type(exc).__name__}: {exc}")

    @pytest.mark.asyncio
    async def test_failure_result_carries_the_offending_modality(self, voice_processor):
        """The caller must be able to tell *what* was unsupported."""
        result = await voice_processor.process(_input(ModalityType.VIDEO))

        assert ModalityType.VIDEO.value in result.error_message.lower()
        assert result.confidence == 0.0
        assert result.result_data is None


class TestSupportedModalityStillReachesProcessing:
    """Guard the mirror: the failure branch must not swallow real work."""

    @pytest.mark.asyncio
    async def test_voice_audio_input_is_not_treated_as_unsupported(self, voice_processor):
        async def _ok(_input_data):
            return {"type": "voice_command", "transcribed_text": "hello", "confidence": 0.99}

        voice_processor._process_audio = _ok
        result = await voice_processor.process(_input(ModalityType.AUDIO))

        assert result.success is True
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_vision_video_fails_without_raising(self, vision_processor):
        """VIDEO is accepted then declared unimplemented — still no exception.

        A distinct branch from "unsupported modality", and one the source-grep
        test never exercised.
        """
        result = await vision_processor.process(_input(ModalityType.VIDEO))

        assert isinstance(result, ProcessingResult)
        assert result.success is False
        assert "Unsupported modality" not in result.error_message

    @pytest.mark.asyncio
    async def test_vision_image_input_is_not_treated_as_unsupported(self, vision_processor):
        async def _ok(_input_data):
            return {"type": "image_analysis", "confidence": 0.99}

        vision_processor._process_image = _ok
        result = await vision_processor.process(_input(ModalityType.IMAGE))

        assert "Unsupported modality" not in (result.error_message or "")


class TestParentContract:
    """If the parent starts declaring more, the subclass tests need revisiting."""

    @pytest.mark.asyncio
    async def test_base_process_raises_notimplementederror(self):
        from multimodal_processor.base import BaseModalProcessor

        with patch("multimodal_processor.base.get_memory_manager", return_value=MagicMock()):
            base = BaseModalProcessor("contract-probe")

        with pytest.raises(NotImplementedError):
            await base.process(_input(ModalityType.TEXT))

    @pytest.mark.asyncio
    async def test_subclass_failures_are_not_exceptions_of_any_kind(self, voice_processor, vision_processor):
        """The whole point of #6755: substitutability for a parent-typed caller."""
        for processor in (voice_processor, vision_processor):
            result = await processor.process(_input(ModalityType.TEXT))
            assert result.success is False
