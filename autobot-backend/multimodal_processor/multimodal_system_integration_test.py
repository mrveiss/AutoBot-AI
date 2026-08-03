# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for the unified multi-modal AI system
Tests component integration, processing workflows, and system reliability
"""

import time
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
import torch

from computer_vision.types import ScreenState
from computer_vision_system import ComputerVisionSystem
from config.manager import ConfigManager as ConfigManager
from memory.enums import MemoryCategory
from multimodal_processor import (
    ContextProcessor,
    ModalityType,
    MultiModalInput,
    MultiModalProcessor,
    ProcessingIntent,
    ProcessingResult,
    VisionProcessor,
    VoiceProcessor,
)
from multimodal_processor.processors import vision, voice


class TestUnifiedMultiModalSystem:
    """Test unified multi-modal AI system integration"""

    @pytest.fixture
    def mock_config(self):
        """Build a real ConfigManager carrying test-specific multimodal overrides.

        #13199: ``set()`` writes a *literal flat key* into the config dict, while the
        section readers (``get_config_section`` -> ``get_nested``) do dot-path
        traversal — so flat writes were invisible to the reader the processors use.
        ``set_nested()`` is the matching writer and overlays these values on top of
        the ``multimodal`` defaults from config/defaults.py.
        """
        config = ConfigManager()
        # #13199: get_nested() refreshes from disk once CACHE_DURATION (30s) elapses,
        # and _reload_config() replaces _config wholesale — which would silently drop
        # every override below. VisionProcessor.__init__ imports torch before it reads
        # the config, so that window is reachable on a cold runner. Pin the cache so
        # the overrides survive to the assertion that depends on them.
        config.CACHE_DURATION = float("inf")
        config.set_nested("multimodal.vision.enabled", True)
        config.set_nested("multimodal.vision.confidence_threshold", 0.8)
        config.set_nested("multimodal.vision.processing_timeout", 30)
        config.set_nested("multimodal.voice.enabled", True)
        config.set_nested("multimodal.voice.confidence_threshold", 0.7)
        config.set_nested("multimodal.context.enabled", True)
        return config

    @pytest.fixture
    def processor(self, mock_config):
        """Create unified processor with mocked config.

        ``torch.cuda.is_available()`` is pinned False: autobot-backend/
        conftest.py substitutes a bare ``MagicMock`` for torch when the real
        package is absent, so the CUDA branch of
        ``MultiModalProcessor.__init__`` would otherwise run against Mock
        device properties. Neither CI nor the dev box has a GPU, so False is
        the truthful answer.
        """
        with (
            patch(
                "multimodal_processor.processors.vision.get_config_section",
                lambda section: mock_config.get_config_section(section),
            ),
            patch.object(torch.cuda, "is_available", return_value=False),
        ):
            return MultiModalProcessor()

    @pytest.mark.asyncio
    async def test_image_processing_workflow(self, processor):
        """Test complete image processing workflow"""
        # Create image input
        image_input = MultiModalInput(
            input_id="test_image_001",
            modality_type=ModalityType.IMAGE,
            intent=ProcessingIntent.SCREEN_ANALYSIS,
            data=b"fake_image_data",
            metadata={"source": "test", "format": "png"},
        )

        # Mock vision processor to return test results
        with patch.object(processor.vision_processor, "process", new_callable=AsyncMock) as mock_process:
            mock_result = Mock()
            mock_result.result_id = "vision_test_image_001"
            mock_result.input_id = "test_image_001"
            mock_result.modality_type = ModalityType.IMAGE
            mock_result.intent = ProcessingIntent.SCREEN_ANALYSIS
            mock_result.success = True
            mock_result.confidence = 0.85
            mock_result.processing_time = 1.2
            mock_result.result_data = {
                "detected_elements": ["button", "text"],
                "confidence": 0.85,
            }
            mock_result.error_message = None
            mock_result.metadata = {}
            mock_process.return_value = mock_result

            # Process the input
            result = await processor.process(image_input)

            # Verify processing
            assert result.success is True
            assert result.confidence == 0.85
            assert result.modality_type == ModalityType.IMAGE
            assert result.processing_time == 1.2
            assert "detected_elements" in result.result_data

            # Verify vision processor was called
            mock_process.assert_called_once_with(image_input)

    @pytest.mark.asyncio
    async def test_audio_processing_workflow(self, processor):
        """Test complete audio processing workflow"""
        # Create audio input
        audio_input = MultiModalInput(
            input_id="test_audio_001",
            modality_type=ModalityType.AUDIO,
            intent=ProcessingIntent.VOICE_COMMAND,
            data=b"fake_audio_data",
            metadata={"format": "wav", "duration": 3.5},
        )

        # Mock voice processor
        with patch.object(processor.voice_processor, "process", new_callable=AsyncMock) as mock_process:
            mock_result = Mock()
            mock_result.result_id = "voice_test_audio_001"
            mock_result.input_id = "test_audio_001"
            mock_result.modality_type = ModalityType.AUDIO
            mock_result.intent = ProcessingIntent.VOICE_COMMAND
            mock_result.success = True
            mock_result.confidence = 0.9
            mock_result.processing_time = 0.8
            mock_result.result_data = {
                "transcription": "test command",
                "intent": "automation",
            }
            mock_result.error_message = None
            mock_result.metadata = {}
            mock_process.return_value = mock_result

            # Process the input
            result = await processor.process(audio_input)

            # Verify processing
            assert result.success is True
            assert result.confidence == 0.9
            assert result.modality_type == ModalityType.AUDIO
            assert "transcription" in result.result_data

            mock_process.assert_called_once_with(audio_input)

    @pytest.mark.asyncio
    async def test_combined_modality_processing(self, processor):
        """Test processing of combined multi-modal input"""
        # Create combined input
        combined_input = MultiModalInput(
            input_id="test_combined_001",
            modality_type=ModalityType.COMBINED,
            intent=ProcessingIntent.AUTOMATION_TASK,
            data=None,
            metadata={"image": b"fake_image_data", "audio": b"fake_audio_data"},
        )

        # Real ProcessingResult instances: _simple_combination
        # (processor.py:485) deliberately skips anything that is not a
        # ProcessingResult, because asyncio.gather(return_exceptions=True)
        # can hand it raw exceptions. Mocks are silently dropped by that
        # guard, so they can never exercise the combination logic.
        vision_result = ProcessingResult(
            result_id="vision_test_combined_001_image",
            input_id="test_combined_001_image",
            modality_type=ModalityType.IMAGE,
            intent=ProcessingIntent.AUTOMATION_TASK,
            success=True,
            confidence=0.8,
            result_data={"elements": ["button"]},
            processing_time=0.1,
        )
        voice_result = ProcessingResult(
            result_id="voice_test_combined_001_audio",
            input_id="test_combined_001_audio",
            modality_type=ModalityType.AUDIO,
            intent=ProcessingIntent.AUTOMATION_TASK,
            success=True,
            confidence=0.9,
            result_data={"command": "click button"},
            processing_time=0.1,
        )

        with (
            patch.object(
                processor.vision_processor,
                "process",
                new_callable=AsyncMock,
                return_value=vision_result,
            ),
            patch.object(
                processor.voice_processor,
                "process",
                new_callable=AsyncMock,
                return_value=voice_result,
            ),
        ):
            # Process combined input
            result = await processor.process(combined_input)

            # Verify combined processing
            assert result.success is True
            assert result.modality_type == ModalityType.COMBINED
            assert "results" in result.result_data
            assert len(result.result_data["results"]) == 2
            assert result.result_data["success_count"] == 2
            # Average of 0.8 and 0.9 — binary float sum is not exactly 0.85.
            assert result.result_data["confidence"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_processing_error_handling(self, processor):
        """Test error handling in processing workflow"""
        # Create input that will cause an error
        error_input = MultiModalInput(
            input_id="test_error_001",
            modality_type=ModalityType.IMAGE,
            intent=ProcessingIntent.VISUAL_QA,
            data=None,  # Invalid data
        )

        # Mock processor to raise exception
        with patch.object(
            processor.vision_processor,
            "process",
            side_effect=Exception("Processing failed"),
        ):
            # Process should handle error gracefully
            result = await processor.process(error_input)

            # Verify error handling. `_create_error_result` (processor.py:132)
            # stores the bare `str(error)`, matching every sibling processor;
            # "Multi-modal processing failed: %s" is only the log line.
            assert result.success is False
            assert result.error_message == "Processing failed"
            assert result.result_id == "unified_test_error_001"
            assert result.result_data is None
            assert result.confidence == 0.0

    def test_statistics_tracking(self, processor):
        """Test that processing statistics are tracked correctly"""
        # Initial stats should be empty
        initial_stats = processor.get_stats()
        assert initial_stats["total_processed"] == 0
        assert initial_stats["successful_processed"] == 0
        assert initial_stats["failed_processed"] == 0

        # Simulate processing results
        success_result = Mock(success=True, modality_type=ModalityType.IMAGE, processing_time=1.5)
        error_result = Mock(success=False, modality_type=ModalityType.AUDIO, processing_time=0.5)

        # Update stats
        processor._update_stats(success_result)
        processor._update_stats(error_result)

        # Check updated stats
        stats = processor.get_stats()
        assert stats["total_processed"] == 2
        assert stats["successful_processed"] == 1
        assert stats["failed_processed"] == 1
        assert stats["avg_processing_time"] == 1.0  # Average of 1.5 and 0.5
        assert stats["modality_counts"]["image"] == 1
        assert stats["modality_counts"]["audio"] == 1

    def test_stats_reset(self, processor):
        """Test statistics reset functionality"""
        # Add some stats
        mock_result = Mock(success=True, modality_type=ModalityType.TEXT, processing_time=2.0)
        processor._update_stats(mock_result)

        # Verify stats exist
        stats = processor.get_stats()
        assert stats["total_processed"] == 1

        # Reset stats
        processor.reset_stats()

        # Verify stats are reset
        stats = processor.get_stats()
        assert stats["total_processed"] == 0
        assert stats["successful_processed"] == 0
        assert stats["avg_processing_time"] == 0.0

    @pytest.mark.asyncio
    async def test_memory_storage_integration(self, processor):
        """Test integration with memory manager for result storage"""
        # Create test input
        test_input = MultiModalInput(
            input_id="test_memory_001",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="test decision context",
        )

        # Issue #10626 replaced the non-existent MemoryManager.store_task()
        # with store_memory(); patch what production actually calls.
        with (
            patch.object(processor.context_processor, "process", new_callable=AsyncMock) as mock_process,
            patch.object(processor.memory_manager, "store_memory", new_callable=AsyncMock) as mock_store,
        ):
            mock_result = ProcessingResult(
                result_id="context_test_memory_001",
                input_id="test_memory_001",
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                success=True,
                confidence=0.95,
                result_data={
                    "decision": "proceed",
                    "reasoning": "context supports action",
                },
                processing_time=0.3,
            )
            mock_process.return_value = mock_result

            # Process input
            await processor.process(test_input)

            # Verify result storage was attempted
            mock_store.assert_called_once()
            call_args = mock_store.call_args[1]
            assert call_args["category"] is MemoryCategory.EXECUTION
            metadata = call_args["metadata"]
            assert metadata["result_id"] == "context_test_memory_001"
            assert metadata["task_type"] == "multimodal_processing"
            assert metadata["status"] == "completed"
            assert metadata["modality"] == ModalityType.TEXT.value

    def test_vision_processor_configuration(self, mock_config):
        """Test vision processor uses configuration correctly"""
        with patch(
            "multimodal_processor.processors.vision.get_config_section",
            lambda section: mock_config.get_config_section(section),
        ):
            vision_proc = VisionProcessor()

            # Verify configuration is loaded
            assert vision_proc.confidence_threshold == 0.8
            assert vision_proc.processing_timeout == 30
            assert vision_proc.enabled is True

    @pytest.mark.asyncio
    async def test_vision_processor_image_processing(self, mock_config):
        """Test vision processor image processing"""
        with patch(
            "multimodal_processor.processors.vision.get_config_section",
            lambda section: mock_config.get_config_section(section),
        ):
            vision_proc = VisionProcessor()

            # Create image input
            image_input = MultiModalInput(
                input_id="vision_test_001",
                modality_type=ModalityType.IMAGE,
                intent=ProcessingIntent.SCREEN_ANALYSIS,
                data=b"fake_image_data",
            )

            result = await vision_proc.process(image_input)

            # Envelope contract holds on both branches (#6755: never raise).
            assert result.result_id == "vision_vision_test_001"
            assert result.input_id == "vision_test_001"
            assert result.modality_type == ModalityType.IMAGE
            assert isinstance(result.processing_time, float)
            assert result.processing_time > 0

            if vision.VISION_MODELS_AVAILABLE and vision_proc.clip_model and vision_proc.blip_model:
                assert result.success is True
                assert result.error_message is None
            else:
                # Issue #466 removed the placeholder fallback: the guard in
                # vision._process_image raises RuntimeError, and process()
                # must degrade it to a failure envelope.
                assert result.success is False
                assert result.result_data is None
                assert "Vision processing unavailable" in result.error_message

    @pytest.mark.asyncio
    async def test_voice_processor_audio_processing(self):
        """Voice processing returns a well-formed envelope, models or not.

        Same #466/#6755 contract as the vision case: the model guard in
        voice._validate_audio_models_available raises RuntimeError and
        process() must convert it into a failure ProcessingResult.
        """
        voice_proc = VoiceProcessor()

        # Create audio input
        audio_input = MultiModalInput(
            input_id="voice_test_001",
            modality_type=ModalityType.AUDIO,
            intent=ProcessingIntent.VOICE_COMMAND,
            data=b"fake_audio_data",
        )

        result = await voice_proc.process(audio_input)

        assert result.result_id == "voice_voice_test_001"
        assert result.input_id == "voice_test_001"
        assert result.modality_type == ModalityType.AUDIO
        assert isinstance(result.processing_time, float)

        if voice.AUDIO_MODELS_AVAILABLE and voice_proc.whisper_model and voice_proc.wav2vec_model:
            assert result.success is True
            assert result.error_message is None
        else:
            assert result.success is False
            assert result.result_data is None
            assert "Voice processing unavailable" in result.error_message

    @pytest.mark.asyncio
    async def test_context_processor_decision_making(self):
        """Context decision making is unimplemented and must say so (#466).

        ``ContextProcessor._process_context`` deliberately raises
        NotImplementedError instead of returning placeholder decisions.
        ``process()`` must surface that as a failure envelope rather than
        propagating the exception to callers.
        """
        context_proc = ContextProcessor()

        # Create context input
        context_input = MultiModalInput(
            input_id="context_test_001",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="Make a decision based on this context",
        )

        result = await context_proc.process(context_input)

        assert result.result_id == "context_context_test_001"
        assert result.input_id == "context_test_001"
        assert result.modality_type == ModalityType.TEXT
        assert isinstance(result.processing_time, float)
        assert result.success is False
        assert result.result_data is None
        assert "Context processing not yet implemented" in result.error_message

    def test_processor_confidence_calculation(self):
        """Test confidence calculation in base processor"""
        from multimodal_processor import BaseModalProcessor

        base_proc = BaseModalProcessor("test")

        # Test default confidence calculation
        confidence = base_proc.calculate_confidence({"test": "data"})
        assert confidence == 0.5  # Default implementation

    @pytest.mark.asyncio
    async def test_computer_vision_system_integration(self):
        """Test integration with computer vision system"""
        cv_system = ComputerVisionSystem()

        # Stub the analyzer with a real ScreenState: ComputerVisionSystem
        # calls screen_state.get_analysis_summary() / get_element_collection()
        # (computer_vision/system.py:39-57), which a bare Mock cannot satisfy —
        # it would hand back un-subscriptable Mock objects.
        with patch.object(cv_system.screen_analyzer, "analyze_current_screen", new_callable=AsyncMock) as mock_analyze:
            screen_state = ScreenState(
                timestamp=time.time(),
                screenshot=np.zeros((2, 2, 3), dtype=np.uint8),
                ui_elements=[],
                text_regions=[],
                dominant_colors=[],
                layout_structure={},
                automation_opportunities=[],
                context_analysis={"application_type": "test"},
                confidence_score=0.8,
            )
            mock_analyze.return_value = screen_state

            # Analyze screen
            result = await cv_system.analyze_and_understand_screen()

            # Verify integration
            assert isinstance(result, dict)
            assert "screen_analysis" in result
            assert "ui_elements" in result
            assert result["screen_analysis"]["confidence_score"] == 0.8

    def test_multimodal_backward_compatibility(self):
        """Test MultiModalProcessor import + singleton API (Issue #10666: consolidated)."""
        from multimodal_processor import MultiModalProcessor, processor

        # MultiModalProcessor is the canonical class (Issue #10666 prefix strip)
        assert MultiModalProcessor is not None

        # processor singleton is the lazy proxy
        assert processor is not None

        # MultiModalProcessor (the real class) has the expected API
        assert hasattr(MultiModalProcessor, "get_stats")
        assert hasattr(MultiModalProcessor, "reset_stats")
        assert hasattr(MultiModalProcessor, "process")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
