# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing System Coordinator

Main voice processing system that coordinates speech recognition,
natural language processing, and text-to-speech components.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from src.enhanced_memory_manager import EnhancedMemoryManager
from src.enhanced_memory_manager_async import TaskPriority
from src.task_execution_tracker import task_tracker

from .constants import HIGH_RISK_COMMAND_TYPES, HIGH_RISK_INTENTS, SCREEN_STATE_INTENTS
from .models import AudioInput, SpeechSynthesisRequest, VoiceCommandAnalysis
from .nlp_processor import NaturalLanguageProcessor
from .speech_recognition import SpeechRecognitionEngine
from .tts_engine import TextToSpeechEngine
from .types import VoiceCommand

logger = logging.getLogger(__name__)


class VoiceProcessingSystem:
    """Main voice processing system coordinator"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        """Initialize voice processing system with speech recognition and TTS engines."""
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.speech_recognition = SpeechRecognitionEngine()
        self.nlp_processor = NaturalLanguageProcessor()
        self.tts_engine = TextToSpeechEngine()

        # Processing history
        self.voice_command_history: List[VoiceCommandAnalysis] = []
        self.max_history = 20

        logger.info("Voice Processing System initialized")

    def _build_low_confidence_response(self, speech_result) -> Dict[str, Any]:
        """Issue #665: Extracted from process_voice_command to reduce function length.

        Build response dict when speech recognition fails or has low confidence.
        """
        return {
            "success": False,
            "error": "Speech recognition failed or low confidence",
            "speech_result": speech_result,
            "suggestions": [
                "Try speaking more clearly",
                "Reduce background noise",
                "Speak closer to microphone",
            ],
        }

    def _update_command_history(self, command_analysis: VoiceCommandAnalysis) -> None:
        """Issue #665: Extracted from process_voice_command to reduce function length.

        Update command history with new analysis, maintaining max history size.
        """
        self.voice_command_history.append(command_analysis)
        if len(self.voice_command_history) > self.max_history:
            self.voice_command_history = self.voice_command_history[-self.max_history :]

    def _build_task_outputs(
        self, speech_result, command_analysis: VoiceCommandAnalysis
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from process_voice_command to reduce function length.

        Build task context outputs dict from speech and command analysis results.
        """
        return {
            "transcription": speech_result.transcription,
            "command_type": command_analysis.command_type.value,
            "confidence": command_analysis.confidence,
            "requires_confirmation": command_analysis.requires_confirmation,
            "actions_count": len(command_analysis.suggested_actions),
        }

    async def process_voice_command(
        self, audio_input: AudioInput, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Complete voice command processing pipeline."""
        async with task_tracker.track_task(
            "Voice Command Processing",
            f"Processing voice command: {audio_input.audio_id}",
            agent_type="voice_processing_system",
            priority=TaskPriority.HIGH,
            inputs={
                "audio_id": audio_input.audio_id,
                "duration": audio_input.duration,
                "has_context": context is not None,
            },
        ) as task_context:
            try:
                # Step 1: Speech Recognition
                speech_result = await self.speech_recognition.transcribe_audio(
                    audio_input
                )

                if not speech_result.transcription or speech_result.confidence < 0.3:
                    return self._build_low_confidence_response(speech_result)

                # Step 2: Natural Language Processing
                command_analysis = await self.nlp_processor.analyze_voice_command(
                    speech_result.transcription, context
                )

                # Step 3: Generate response and actions
                response = await self._generate_command_response(
                    command_analysis, speech_result, context
                )

                # Step 4: Update history and set task outputs
                self._update_command_history(command_analysis)
                task_context.set_outputs(
                    self._build_task_outputs(speech_result, command_analysis)
                )

                logger.info(
                    "Voice command processed successfully: %s",
                    command_analysis.command_type.value,
                )
                return response

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Voice command processing failed: %s", e)
                raise

    def _build_base_response(
        self, command_analysis: VoiceCommandAnalysis, speech_result
    ) -> Dict[str, Any]:
        """Build base response structure for voice command.

        Constructs the core response dictionary with speech recognition
        and command analysis data. Issue #620.

        Args:
            command_analysis: Analyzed voice command
            speech_result: Speech recognition result

        Returns:
            Base response dictionary
        """
        return {
            "success": True,
            "command_id": command_analysis.command_id,
            "speech_recognition": {
                "transcription": speech_result.transcription,
                "confidence": speech_result.confidence,
                "audio_quality": speech_result.audio_quality.value,
            },
            "command_analysis": {
                "type": command_analysis.command_type.value,
                "intent": command_analysis.intent,
                "entities": command_analysis.entities,
                "parameters": command_analysis.parameters,
                "confidence": command_analysis.confidence,
            },
        }

    async def _add_conditional_response_parts(
        self, response: Dict[str, Any], command_analysis: VoiceCommandAnalysis
    ) -> None:
        """Add confirmation and context requirements to response.

        Appends confirmation_required and context_required sections
        when needed. Issue #620.

        Args:
            response: Response dictionary to modify in place
            command_analysis: Analyzed voice command
        """
        if command_analysis.requires_confirmation:
            response["confirmation_required"] = {
                "message": f"Confirm execution of: {command_analysis.intent}",
                "parameters": command_analysis.parameters,
                "risk_level": await self._assess_risk_level(command_analysis),
            }

        if command_analysis.context_needed:
            response["context_required"] = {
                "message": "Additional context needed for command execution",
                "required_info": await self._determine_required_context(
                    command_analysis
                ),
                "suggestions": [
                    "Take screenshot",
                    "Analyze current screen",
                    "Provide target element description",
                ],
            }

    async def _generate_command_response(
        self,
        command_analysis: VoiceCommandAnalysis,
        speech_result,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate comprehensive response to voice command.

        Issue #620: Refactored to use extracted helper methods.
        """
        # Issue #620: Use helper for base response
        response = self._build_base_response(command_analysis, speech_result)

        # Add execution plan
        response["execution_plan"] = {
            "suggested_actions": command_analysis.suggested_actions,
            "requires_confirmation": command_analysis.requires_confirmation,
            "context_needed": command_analysis.context_needed,
            "estimated_duration": await self._estimate_execution_duration(
                command_analysis
            ),
        }
        response["next_steps"] = await self._determine_next_steps(
            command_analysis, context
        )

        # Issue #620: Use helper for conditional parts
        await self._add_conditional_response_parts(response, command_analysis)

        return response

    async def _estimate_execution_duration(
        self, command_analysis: VoiceCommandAnalysis
    ) -> float:
        """Estimate how long command execution will take"""
        base_durations = {
            VoiceCommand.AUTOMATION: 2.0,
            VoiceCommand.NAVIGATION: 1.5,
            VoiceCommand.CONTROL: 1.0,
            VoiceCommand.QUERY: 0.5,
            VoiceCommand.SYSTEM: 3.0,
            VoiceCommand.TAKEOVER: 1.0,
        }

        base_duration = base_durations.get(command_analysis.command_type, 1.0)
        complexity_multiplier = len(command_analysis.suggested_actions) * 0.3

        return base_duration + complexity_multiplier

    async def _assess_risk_level(self, command_analysis: VoiceCommandAnalysis) -> str:
        """Assess risk level of command execution"""
        # Use module-level frozenset for O(1) lookup
        if command_analysis.command_type in HIGH_RISK_COMMAND_TYPES:
            return "high"

        # Use module-level frozenset for O(1) lookup
        intent_lower = command_analysis.intent.lower()
        if any(risk_intent in intent_lower for risk_intent in HIGH_RISK_INTENTS):
            return "high"

        if command_analysis.confidence < 0.7:
            return "medium"

        return "low"

    async def _determine_required_context(
        self, command_analysis: VoiceCommandAnalysis
    ) -> List[str]:
        """Determine what context information is needed"""
        required_context = []

        if command_analysis.command_type == VoiceCommand.AUTOMATION:
            if "target_element" not in command_analysis.parameters:
                required_context.append("target_element_identification")

            if command_analysis.intent in SCREEN_STATE_INTENTS:
                required_context.append("current_screen_state")

        if command_analysis.command_type == VoiceCommand.NAVIGATION:
            required_context.append("current_page_url")
            required_context.append("available_navigation_options")

        return required_context

    async def _determine_next_steps(
        self, command_analysis: VoiceCommandAnalysis, context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Determine immediate next steps for command execution"""
        next_steps = []

        if command_analysis.requires_confirmation:
            next_steps.append("await_user_confirmation")

        if command_analysis.context_needed and not context:
            next_steps.append("gather_required_context")

        if (
            not command_analysis.requires_confirmation
            and not command_analysis.context_needed
        ):
            next_steps.extend(command_analysis.suggested_actions[:3])  # First 3 actions

        next_steps.append("monitor_execution_progress")

        return next_steps

    async def synthesize_response(
        self, text: str, voice_settings: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """Generate spoken response"""

        synthesis_request = SpeechSynthesisRequest(
            text=text,
            voice_settings=voice_settings or {},
            output_format="wav",
            priority=TaskPriority.MEDIUM,
            metadata={"response_type": "voice_command_feedback"},
        )

        return await self.tts_engine.synthesize_speech(synthesis_request)

    def get_command_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent voice command history"""
        history = self.voice_command_history
        if limit:
            history = history[-limit:]

        return [
            {
                "command_id": cmd.command_id,
                "type": cmd.command_type.value,
                "intent": cmd.intent,
                "confidence": cmd.confidence,
                "timestamp": cmd.metadata.get("timestamp", 0) if cmd.metadata else 0,
            }
            for cmd in history
        ]

    def get_system_status(self) -> Dict[str, Any]:
        """Get voice processing system status"""
        return {
            "speech_recognition_available": (
                self.speech_recognition.recognizer is not None
            ),
            "tts_available": self.tts_engine.tts_engine is not None,
            "command_history_count": len(self.voice_command_history),
            "supported_commands": [cmd.value for cmd in VoiceCommand],
            "recent_activity": {
                "commands_processed": len(self.voice_command_history),
                "average_confidence": (
                    np.mean([cmd.confidence for cmd in self.voice_command_history])
                    if self.voice_command_history
                    else 0.0
                ),
                "most_common_command": (
                    max(
                        [cmd.command_type for cmd in self.voice_command_history],
                        key=[
                            cmd.command_type for cmd in self.voice_command_history
                        ].count,
                    ).value
                    if self.voice_command_history
                    else "none"
                ),
            },
        }


__all__ = [
    "VoiceProcessingSystem",
]
