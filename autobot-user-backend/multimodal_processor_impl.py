"""
Unified Multi-Modal AI Processor for AutoBot Phase 9
Consolidates vision, voice, and context processing with consistent interfaces
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from enhanced_memory_manager_async import (
    TaskPriority,
    get_async_enhanced_memory_manager,
)
from backend.utils.config_manager import get_config_section

logger = logging.getLogger(__name__)


class ModalityType(Enum):
    """Types of input modalities supported"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    COMBINED = "combined"


class ProcessingIntent(Enum):
    """Types of processing intents"""

    SCREEN_ANALYSIS = "screen_analysis"
    VOICE_COMMAND = "voice_command"
    VISUAL_QA = "visual_qa"
    AUTOMATION_TASK = "automation_task"
    CONTENT_GENERATION = "content_generation"
    DECISION_MAKING = "decision_making"


class ConfidenceLevel(Enum):
    """Confidence levels for processing results"""

    VERY_HIGH = 0.9
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    VERY_LOW = 0.2


@dataclass
class MultiModalInput:
    """Unified input data structure for all modalities"""

    input_id: str
    modality_type: ModalityType
    intent: ProcessingIntent
    data: Any  # Flexible data field for any input type
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProcessingResult:
    """Unified result structure for all processing types"""

    result_id: str
    input_id: str
    modality_type: ModalityType
    intent: ProcessingIntent
    success: bool
    confidence: float
    result_data: Any
    processing_time: float
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseModalProcessor:
    """Base class for modal-specific processors"""

    def __init__(self, processor_type: str):
        self.processor_type = processor_type
        self.logger = logging.getLogger(f"{__name__}.{processor_type}")
        self.memory_manager = get_async_enhanced_memory_manager()

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process input and return result"""
        raise NotImplementedError

    def calculate_confidence(self, processing_data: Any) -> float:
        """Calculate confidence score for processing result"""
        # Base implementation - override in subclasses
        return 0.5


class VisionProcessor(BaseModalProcessor):
    """Computer vision processing component"""

    def __init__(self):
        super().__init__("vision")
        self.config = get_config_section("multimodal.vision")
        self.confidence_threshold = self.config.get("confidence_threshold", 0.7)
        self.processing_timeout = self.config.get("processing_timeout", 30)
        self.enabled = self.config.get("enabled", True)

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process visual input (images, screenshots, video)"""
        start_time = time.time()

        try:
            if input_data.modality_type == ModalityType.IMAGE:
                result = await self._process_image(input_data)
            elif input_data.modality_type == ModalityType.VIDEO:
                result = await self._process_video(input_data)
            else:
                raise ValueError(f"Unsupported modality: {input_data.modality_type}")

            processing_time = time.time() - start_time
            confidence = self.calculate_confidence(result)

            return ProcessingResult(
                result_id=f"vision_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=True,
                confidence=confidence,
                result_data=result,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Vision processing failed: {e}")

            return ProcessingResult(
                result_id=f"vision_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    async def _process_image(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process single image"""
        # Placeholder for image processing logic
        return {
            "type": "image_analysis",
            "elements_detected": [],
            "text_detected": "",
            "confidence": 0.8,
        }

    async def _process_video(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process video input"""
        # Placeholder for video processing logic
        return {"type": "video_analysis", "frames_processed": 0, "confidence": 0.7}


class VoiceProcessor(BaseModalProcessor):
    """Voice processing component"""

    def __init__(self):
        super().__init__("voice")

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process audio input (voice commands, speech)"""
        start_time = time.time()

        try:
            if input_data.modality_type == ModalityType.AUDIO:
                result = await self._process_audio(input_data)
            else:
                raise ValueError(f"Unsupported modality: {input_data.modality_type}")

            processing_time = time.time() - start_time
            confidence = self.calculate_confidence(result)

            return ProcessingResult(
                result_id=f"voice_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=True,
                confidence=confidence,
                result_data=result,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Voice processing failed: {e}")

            return ProcessingResult(
                result_id=f"voice_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    async def _process_audio(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process audio input"""
        # Placeholder for audio processing logic
        return {
            "type": "voice_command",
            "transcribed_text": "",
            "command_type": "unknown",
            "confidence": 0.8,
        }


class ContextProcessor(BaseModalProcessor):
    """Context-aware decision processing component"""

    def __init__(self):
        super().__init__("context")

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process context and make decisions"""
        start_time = time.time()

        try:
            result = await self._process_context(input_data)
            processing_time = time.time() - start_time
            confidence = self.calculate_confidence(result)

            return ProcessingResult(
                result_id=f"context_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=True,
                confidence=confidence,
                result_data=result,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Context processing failed: {e}")

            return ProcessingResult(
                result_id=f"context_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    async def _process_context(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process contextual information"""
        # Placeholder for context processing logic
        return {
            "type": "context_decision",
            "decision": "continue",
            "reasoning": "Based on current context",
            "confidence": 0.9,
        }


class UnifiedMultiModalProcessor:
    """
    Main multi-modal processor that coordinates all modal-specific processors
    """

    def __init__(self):
        self.vision_processor = VisionProcessor()
        self.voice_processor = VoiceProcessor()
        self.context_processor = ContextProcessor()
        self.memory_manager = get_async_enhanced_memory_manager()
        self.logger = logging.getLogger(__name__)

        # Processing statistics
        self.stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "avg_processing_time": 0.0,
            "modality_counts": {modality.value: 0 for modality in ModalityType},
        }

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """
        Main processing method that routes input to appropriate processor
        """
        self.logger.info(
            "Processing %s input with intent %s",
            input_data.modality_type.value,
            input_data.intent.value,
        )

        try:
            # Route to appropriate processor based on modality
            if input_data.modality_type in [ModalityType.IMAGE, ModalityType.VIDEO]:
                result = await self.vision_processor.process(input_data)
            elif input_data.modality_type == ModalityType.AUDIO:
                result = await self.voice_processor.process(input_data)
            elif input_data.modality_type == ModalityType.TEXT:
                result = await self.context_processor.process(input_data)
            elif input_data.modality_type == ModalityType.COMBINED:
                result = await self._process_combined(input_data)
            else:
                raise ValueError(f"Unknown modality type: {input_data.modality_type}")

            # Update statistics
            self._update_stats(result)

            # Store result in memory
            await self._store_result(result)

            return result

        except Exception as e:
            self.logger.error(f"Multi-modal processing failed: {e}")
            return ProcessingResult(
                result_id=f"unified_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=0.0,
                error_message=str(e),
            )

    def _create_modality_input(
        self,
        input_data: MultiModalInput,
        modality_key: str,
        modality_type: ModalityType,
    ) -> Optional[MultiModalInput]:
        """Create a modality-specific input from combined input metadata. Issue #620."""
        if modality_key not in input_data.metadata:
            return None
        return MultiModalInput(
            input_id=f"{input_data.input_id}_{modality_key}",
            modality_type=modality_type,
            intent=input_data.intent,
            data=input_data.metadata[modality_key],
        )

    def _build_combined_tasks(self, input_data: MultiModalInput) -> List:
        """Build list of processing tasks for each modality in combined input. Issue #620."""
        tasks = []
        image_input = self._create_modality_input(
            input_data, "image", ModalityType.IMAGE
        )
        if image_input:
            tasks.append(self.vision_processor.process(image_input))
        audio_input = self._create_modality_input(
            input_data, "audio", ModalityType.AUDIO
        )
        if audio_input:
            tasks.append(self.voice_processor.process(audio_input))
        return tasks

    def _build_combined_result(
        self,
        input_data: MultiModalInput,
        processing_time: float,
        success: bool,
        combined_result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> ProcessingResult:
        """Build ProcessingResult for combined modality processing. Issue #620."""
        return ProcessingResult(
            result_id=f"combined_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=success,
            confidence=combined_result.get("confidence", 0.5)
            if combined_result
            else 0.0,
            result_data=combined_result,
            processing_time=processing_time,
            error_message=error_message,
        )

    async def _process_combined(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process combined multi-modal input. Issue #620."""
        start_time = time.time()
        try:
            tasks = self._build_combined_tasks(input_data)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            combined_result = self._combine_results(results)
            processing_time = time.time() - start_time
            return self._build_combined_result(
                input_data,
                processing_time,
                success=True,
                combined_result=combined_result,
            )
        except Exception as e:
            processing_time = time.time() - start_time
            return self._build_combined_result(
                input_data, processing_time, success=False, error_message=str(e)
            )

    def _combine_results(self, results: List[ProcessingResult]) -> Dict[str, Any]:
        """Combine results from multiple processors"""
        combined = {
            "results": [],
            "confidence": 0.0,
            "success_count": 0,
            "total_count": len(results),
        }

        confidence_sum = 0.0
        for result in results:
            if isinstance(result, ProcessingResult):
                combined["results"].append(
                    {
                        "modality": result.modality_type.value,
                        "success": result.success,
                        "confidence": result.confidence,
                        "data": result.result_data,
                    }
                )
                if result.success:
                    combined["success_count"] += 1
                    confidence_sum += result.confidence

        # Calculate average confidence
        if combined["success_count"] > 0:
            combined["confidence"] = confidence_sum / combined["success_count"]

        return combined

    def _update_stats(self, result: ProcessingResult):
        """Update processing statistics"""
        self.stats["total_processed"] += 1

        if result.success:
            self.stats["successful_processed"] += 1
        else:
            self.stats["failed_processed"] += 1

        # Update modality counts
        self.stats["modality_counts"][result.modality_type.value] += 1

        # Update average processing time
        total_time = (
            self.stats["avg_processing_time"] * (self.stats["total_processed"] - 1)
            + result.processing_time
        )
        self.stats["avg_processing_time"] = total_time / self.stats["total_processed"]

    async def _store_result(self, result: ProcessingResult):
        """Store processing result in memory"""
        try:
            task_data = {
                "result_id": result.result_id,
                "modality": result.modality_type.value,
                "intent": result.intent.value,
                "success": result.success,
                "confidence": result.confidence,
                "processing_time": result.processing_time,
            }

            await self.memory_manager.store_task(
                task_id=result.result_id,
                task_type="multimodal_processing",
                description=f"Multi-modal processing: {result.modality_type.value}",
                status="completed" if result.success else "failed",
                priority=TaskPriority.MEDIUM,
                subtasks=[],
                context=task_data,
                execution_details={"result_data": result.result_data},
            )

        except Exception as e:
            self.logger.warning(f"Failed to store processing result: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset processing statistics"""
        self.stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "avg_processing_time": 0.0,
            "modality_counts": {modality.value: 0 for modality in ModalityType},
        }


# Singleton instance for global access
unified_processor = UnifiedMultiModalProcessor()
