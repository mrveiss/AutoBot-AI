# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""VoiceProcessor must read a config section that exists (#13207).

``VoiceProcessor.__init__`` read ``multimodal.audio``, a section defined nowhere
under any path. ``get_config_section`` therefore returned ``{}`` on every boot
and every value fell through to a literal — including ``enabled``, which gates
model loading, so the configured section was unreachable in production and
changing it did nothing.

The second half of these tests pins the threshold/timeout decision: correcting
the key must NOT move a live value. ``multimodal.voice`` previously declared
0.8 / 15, which had never reached the processor; ``defaults.py`` was aligned to
the 0.7 / 30 that was actually in effect, so this fix is behaviour-preserving.
Retuning voice confidence is a separate, evidence-backed change.
"""

from unittest.mock import MagicMock, patch

import pytest

from config import get_config_section

VOICE_MODULE = "multimodal_processor.processors.voice"


class TestConfigSectionExists:
    """The section the processor names has to be the section that is defined."""

    def test_multimodal_voice_section_is_defined(self):
        section = get_config_section("multimodal.voice")

        assert section, "multimodal.voice must resolve to a populated section"
        assert set(section) >= {"enabled", "confidence_threshold", "processing_timeout"}

    def test_multimodal_audio_section_does_not_exist(self):
        """The old key resolved to {} — which is why the bug was silent."""
        assert get_config_section("multimodal.audio") == {}


class TestVoiceProcessorReadsTheRealSection:
    @pytest.fixture
    def processor_cls(self):
        import multimodal_processor.processors.voice as voice_module

        return voice_module

    def _build(self, voice_module, section):
        """Construct a VoiceProcessor with config and torch/model loading stubbed."""
        with (
            patch.object(voice_module, "get_config_section", return_value=section) as get_section,
            patch.object(voice_module, "_get_torch", return_value=MagicMock()),
            patch.object(voice_module.VoiceProcessor, "_load_models", lambda self: None),
        ):
            processor = voice_module.VoiceProcessor()
        return processor, get_section

    def test_processor_asks_for_multimodal_voice(self, processor_cls):
        _, get_section = self._build(processor_cls, {"enabled": False})

        get_section.assert_called_once_with("multimodal.voice")

    def test_configured_values_now_reach_the_processor(self, processor_cls):
        """The regression: a configured threshold used to have no effect at all."""
        section = {"enabled": True, "confidence_threshold": 0.42, "processing_timeout": 7}
        processor, _ = self._build(processor_cls, section)

        assert processor.confidence_threshold == 0.42
        assert processor.processing_timeout == 7
        assert processor.enabled is True

    def test_enabled_false_is_honoured(self, processor_cls):
        """`enabled` gates model loading — the live casualty of the dead key."""
        processor, _ = self._build(processor_cls, {"enabled": False})

        assert processor.enabled is False


class TestEffectiveBehaviourIsPreserved:
    """Fixing the key must not silently retune voice confidence or timeout."""

    def test_declared_defaults_match_the_values_that_were_in_effect(self):
        section = get_config_section("multimodal.voice")

        assert section["confidence_threshold"] == 0.7
        assert section["processing_timeout"] == 30

    def test_module_fallbacks_match_the_declared_defaults(self):
        import multimodal_processor.processors.voice as voice_module

        assert voice_module.VOICE_CONFIDENCE_THRESHOLD_DEFAULT == 0.7
        assert voice_module.VOICE_PROCESSING_TIMEOUT_DEFAULT == 30

    def test_processor_runs_on_the_prior_values_end_to_end(self):
        """Whole chain: real config section, real fallbacks, unchanged numbers."""
        import multimodal_processor.processors.voice as voice_module

        with (
            patch.object(voice_module, "_get_torch", return_value=MagicMock()),
            patch.object(voice_module.VoiceProcessor, "_load_models", lambda self: None),
        ):
            processor = voice_module.VoiceProcessor()

        assert processor.confidence_threshold == 0.7
        assert processor.processing_timeout == 30

    def test_fallbacks_apply_when_the_section_omits_them(self):
        import multimodal_processor.processors.voice as voice_module

        with (
            patch.object(voice_module, "get_config_section", return_value={"enabled": True}),
            patch.object(voice_module, "_get_torch", return_value=MagicMock()),
            patch.object(voice_module.VoiceProcessor, "_load_models", lambda self: None),
        ):
            processor = voice_module.VoiceProcessor()

        assert processor.confidence_threshold == voice_module.VOICE_CONFIDENCE_THRESHOLD_DEFAULT
        assert processor.processing_timeout == voice_module.VOICE_PROCESSING_TIMEOUT_DEFAULT
