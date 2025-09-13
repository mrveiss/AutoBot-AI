"""
Integration tests for the unified multi-modal AI system
Tests component integration, processing workflows, and system reliability
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

from src.unified_multimodal_processor import (
    UnifiedMultiModalProcessor, 
    MultiModalInput, 
    ModalityType, 
    ProcessingIntent,
    VisionProcessor,
    VoiceProcessor,
    ContextProcessor
)
from src.computer_vision_system import ComputerVisionSystem
from src.utils.config_manager import ConfigManager


class TestUnifiedMultiModalSystem:
    """Test unified multi-modal AI system integration"""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock configuration for testing"""
        config = ConfigManager()
        config.set("multimodal.vision.enabled", True)
        config.set("multimodal.vision.confidence_threshold", 0.8)
        config.set("multimodal.vision.processing_timeout", 30)
        config.set("multimodal.voice.enabled", True)
        config.set("multimodal.voice.confidence_threshold", 0.7)
        config.set("multimodal.context.enabled", True)
        return config
    
    @pytest.fixture
    def unified_processor(self, mock_config):
        """Create unified processor with mocked config"""
        with patch('src.unified_multimodal_processor.get_config_section', 
                   lambda section: mock_config.get_section(section)):
            return UnifiedMultiModalProcessor()
    
    @pytest.mark.asyncio
    async def test_image_processing_workflow(self, unified_processor):
        """Test complete image processing workflow"""
        # Create image input
        image_input = MultiModalInput(
            input_id="test_image_001",
            modality_type=ModalityType.IMAGE,
            intent=ProcessingIntent.SCREEN_ANALYSIS,
            data=b"fake_image_data",
            metadata={"source": "test", "format": "png"}
        )
        
        # Mock vision processor to return test results
        with patch.object(unified_processor.vision_processor, 'process', 
                         new_callable=AsyncMock) as mock_process:
            mock_result = Mock()
            mock_result.result_id = "vision_test_image_001"
            mock_result.input_id = "test_image_001"
            mock_result.modality_type = ModalityType.IMAGE
            mock_result.intent = ProcessingIntent.SCREEN_ANALYSIS
            mock_result.success = True
            mock_result.confidence = 0.85
            mock_result.processing_time = 1.2
            mock_result.result_data = {"detected_elements": ["button", "text"], "confidence": 0.85}
            mock_result.error_message = None
            mock_result.metadata = {}
            mock_process.return_value = mock_result
            
            # Process the input
            result = await unified_processor.process(image_input)
            
            # Verify processing
            assert result.success is True
            assert result.confidence == 0.85
            assert result.modality_type == ModalityType.IMAGE
            assert result.processing_time == 1.2
            assert "detected_elements" in result.result_data
            
            # Verify vision processor was called
            mock_process.assert_called_once_with(image_input)
    
    @pytest.mark.asyncio
    async def test_audio_processing_workflow(self, unified_processor):
        """Test complete audio processing workflow"""
        # Create audio input
        audio_input = MultiModalInput(
            input_id="test_audio_001",
            modality_type=ModalityType.AUDIO,
            intent=ProcessingIntent.VOICE_COMMAND,
            data=b"fake_audio_data",
            metadata={"format": "wav", "duration": 3.5}
        )
        
        # Mock voice processor
        with patch.object(unified_processor.voice_processor, 'process',
                         new_callable=AsyncMock) as mock_process:
            mock_result = Mock()
            mock_result.result_id = "voice_test_audio_001"
            mock_result.input_id = "test_audio_001"
            mock_result.modality_type = ModalityType.AUDIO
            mock_result.intent = ProcessingIntent.VOICE_COMMAND
            mock_result.success = True
            mock_result.confidence = 0.9
            mock_result.processing_time = 0.8
            mock_result.result_data = {"transcription": "test command", "intent": "automation"}
            mock_result.error_message = None
            mock_result.metadata = {}
            mock_process.return_value = mock_result
            
            # Process the input
            result = await unified_processor.process(audio_input)
            
            # Verify processing
            assert result.success is True
            assert result.confidence == 0.9
            assert result.modality_type == ModalityType.AUDIO
            assert "transcription" in result.result_data
            
            mock_process.assert_called_once_with(audio_input)
    
    @pytest.mark.asyncio
    async def test_combined_modality_processing(self, unified_processor):
        """Test processing of combined multi-modal input"""
        # Create combined input
        combined_input = MultiModalInput(
            input_id="test_combined_001",
            modality_type=ModalityType.COMBINED,
            intent=ProcessingIntent.AUTOMATION_TASK,
            data=None,
            metadata={
                "image": b"fake_image_data",
                "audio": b"fake_audio_data"
            }
        )
        
        # Mock both processors
        vision_result = Mock(
            success=True, confidence=0.8, result_data={"elements": ["button"]},
            modality_type=ModalityType.IMAGE
        )
        voice_result = Mock(
            success=True, confidence=0.9, result_data={"command": "click button"},
            modality_type=ModalityType.AUDIO
        )
        
        with patch.object(unified_processor.vision_processor, 'process',
                         new_callable=AsyncMock, return_value=vision_result), \
             patch.object(unified_processor.voice_processor, 'process',
                         new_callable=AsyncMock, return_value=voice_result):
            
            # Process combined input
            result = await unified_processor.process(combined_input)
            
            # Verify combined processing
            assert result.success is True
            assert result.modality_type == ModalityType.COMBINED
            assert "results" in result.result_data
            assert len(result.result_data["results"]) == 2
            assert result.result_data["success_count"] == 2
            assert result.result_data["confidence"] == 0.85  # Average of 0.8 and 0.9
    
    @pytest.mark.asyncio
    async def test_processing_error_handling(self, unified_processor):
        """Test error handling in processing workflow"""
        # Create input that will cause an error
        error_input = MultiModalInput(
            input_id="test_error_001",
            modality_type=ModalityType.IMAGE,
            intent=ProcessingIntent.VISUAL_QA,
            data=None  # Invalid data
        )
        
        # Mock processor to raise exception
        with patch.object(unified_processor.vision_processor, 'process',
                         side_effect=Exception("Processing failed")):
            
            # Process should handle error gracefully
            result = await unified_processor.process(error_input)
            
            # Verify error handling
            assert result.success is False
            assert result.error_message == "Multi-modal processing failed: Processing failed"
            assert result.confidence == 0.0
    
    def test_statistics_tracking(self, unified_processor):
        """Test that processing statistics are tracked correctly"""
        # Initial stats should be empty
        initial_stats = unified_processor.get_stats()
        assert initial_stats["total_processed"] == 0
        assert initial_stats["successful_processed"] == 0
        assert initial_stats["failed_processed"] == 0
        
        # Simulate processing results
        success_result = Mock(
            success=True,
            modality_type=ModalityType.IMAGE,
            processing_time=1.5
        )
        error_result = Mock(
            success=False,
            modality_type=ModalityType.AUDIO,
            processing_time=0.5
        )
        
        # Update stats
        unified_processor._update_stats(success_result)
        unified_processor._update_stats(error_result)
        
        # Check updated stats
        stats = unified_processor.get_stats()
        assert stats["total_processed"] == 2
        assert stats["successful_processed"] == 1
        assert stats["failed_processed"] == 1
        assert stats["avg_processing_time"] == 1.0  # Average of 1.5 and 0.5
        assert stats["modality_counts"]["image"] == 1
        assert stats["modality_counts"]["audio"] == 1
    
    def test_stats_reset(self, unified_processor):
        """Test statistics reset functionality"""
        # Add some stats
        mock_result = Mock(
            success=True,
            modality_type=ModalityType.TEXT,
            processing_time=2.0
        )
        unified_processor._update_stats(mock_result)
        
        # Verify stats exist
        stats = unified_processor.get_stats()
        assert stats["total_processed"] == 1
        
        # Reset stats
        unified_processor.reset_stats()
        
        # Verify stats are reset
        stats = unified_processor.get_stats()
        assert stats["total_processed"] == 0
        assert stats["successful_processed"] == 0
        assert stats["avg_processing_time"] == 0.0
    
    @pytest.mark.asyncio
    async def test_memory_storage_integration(self, unified_processor):
        """Test integration with memory manager for result storage"""
        # Create test input
        test_input = MultiModalInput(
            input_id="test_memory_001",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="test decision context"
        )
        
        # Mock context processor and memory manager
        with patch.object(unified_processor.context_processor, 'process',
                         new_callable=AsyncMock) as mock_process, \
             patch.object(unified_processor.memory_manager, 'store_task',
                         new_callable=AsyncMock) as mock_store:
            
            mock_result = Mock(
                result_id="context_test_memory_001",
                success=True,
                confidence=0.95,
                processing_time=0.3,
                result_data={"decision": "proceed", "reasoning": "context supports action"},
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING
            )
            mock_process.return_value = mock_result
            
            # Process input
            result = await unified_processor.process(test_input)
            
            # Verify result storage was attempted
            mock_store.assert_called_once()
            call_args = mock_store.call_args[1]
            assert call_args["task_id"] == "context_test_memory_001"
            assert call_args["task_type"] == "multimodal_processing"
            assert call_args["status"] == "completed"
    
    def test_vision_processor_configuration(self, mock_config):
        """Test vision processor uses configuration correctly"""
        with patch('src.unified_multimodal_processor.get_config_section',
                   lambda section: mock_config.get_section(section)):
            vision_proc = VisionProcessor()
            
            # Verify configuration is loaded
            assert vision_proc.confidence_threshold == 0.8
            assert vision_proc.processing_timeout == 30
            assert vision_proc.enabled is True
    
    @pytest.mark.asyncio
    async def test_vision_processor_image_processing(self, mock_config):
        """Test vision processor image processing"""
        with patch('src.unified_multimodal_processor.get_config_section',
                   lambda section: mock_config.get_section(section)):
            vision_proc = VisionProcessor()
            
            # Create image input
            image_input = MultiModalInput(
                input_id="vision_test_001",
                modality_type=ModalityType.IMAGE,
                intent=ProcessingIntent.SCREEN_ANALYSIS,
                data=b"fake_image_data"
            )
            
            # Process image (will use placeholder logic)
            result = await vision_proc.process(image_input)
            
            # Verify basic processing structure
            assert result.success is True
            assert result.result_id == "vision_vision_test_001"
            assert result.modality_type == ModalityType.IMAGE
            assert isinstance(result.processing_time, float)
            assert result.processing_time > 0
    
    @pytest.mark.asyncio
    async def test_voice_processor_audio_processing(self):
        """Test voice processor audio processing"""
        voice_proc = VoiceProcessor()
        
        # Create audio input
        audio_input = MultiModalInput(
            input_id="voice_test_001",
            modality_type=ModalityType.AUDIO,
            intent=ProcessingIntent.VOICE_COMMAND,
            data=b"fake_audio_data"
        )
        
        # Process audio (will use placeholder logic)
        result = await voice_proc.process(audio_input)
        
        # Verify basic processing structure
        assert result.success is True
        assert result.result_id == "voice_voice_test_001"
        assert result.modality_type == ModalityType.AUDIO
        assert isinstance(result.processing_time, float)
    
    @pytest.mark.asyncio
    async def test_context_processor_decision_making(self):
        """Test context processor decision making"""
        context_proc = ContextProcessor()
        
        # Create context input
        context_input = MultiModalInput(
            input_id="context_test_001",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="Make a decision based on this context"
        )
        
        # Process context (will use placeholder logic)
        result = await context_proc.process(context_input)
        
        # Verify basic processing structure
        assert result.success is True
        assert result.result_id == "context_context_test_001"
        assert result.modality_type == ModalityType.TEXT
        assert isinstance(result.processing_time, float)
    
    def test_processor_confidence_calculation(self):
        """Test confidence calculation in base processor"""
        from src.unified_multimodal_processor import BaseModalProcessor
        
        base_proc = BaseModalProcessor("test")
        
        # Test default confidence calculation
        confidence = base_proc.calculate_confidence({"test": "data"})
        assert confidence == 0.5  # Default implementation
    
    @pytest.mark.asyncio
    async def test_computer_vision_system_integration(self):
        """Test integration with computer vision system"""
        cv_system = ComputerVisionSystem()
        
        # Mock the screen analyzer and its dependencies
        with patch.object(cv_system.screen_analyzer, 'analyze_current_screen',
                         new_callable=AsyncMock) as mock_analyze:
            
            mock_screen_state = Mock(
                timestamp=time.time(),
                ui_elements=[],
                confidence_score=0.8,
                context_analysis={"application_type": "test"},
                automation_opportunities=[]
            )
            mock_analyze.return_value = mock_screen_state
            
            # Analyze screen
            result = await cv_system.analyze_and_understand_screen()
            
            # Verify integration
            assert isinstance(result, dict)
            assert "screen_analysis" in result
            assert "ui_elements" in result
            assert result["screen_analysis"]["confidence_score"] == 0.8
    
    def test_multimodal_backward_compatibility(self):
        """Test backward compatibility layer"""
        from src.multimodal_processor import MultiModalProcessor, multimodal_processor
        
        # Test compatibility wrapper
        compat_processor = MultiModalProcessor()
        
        # Verify it wraps the unified processor
        assert hasattr(compat_processor, '_unified')
        assert hasattr(compat_processor, 'get_stats')
        assert hasattr(compat_processor, 'reset_stats')
        
        # Test global instance
        assert multimodal_processor is not None
        assert isinstance(multimodal_processor, MultiModalProcessor)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])