# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Natural Language Processor

Handles voice command analysis, intent extraction, and entity recognition.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from enhanced_memory_manager_async import TaskPriority
from task_execution_tracker import task_tracker
from voice_processing.constants import (
    APP_PATTERNS_RE,
    AUTOMATION_INTENT_PATTERNS,
    CONTEXT_DEPENDENT_INTENTS,
    DIRECTION_RE,
    HIGH_RISK_INTENTS,
    NAVIGATION_INTENT_PATTERNS,
    NUMBER_RE,
    QUERY_INTENT_PATTERNS,
    QUOTED_TEXT_RE,
    URL_RE,
    match_intent_from_patterns,
)
from voice_processing.models import VoiceCommandAnalysis
from voice_processing.types import VoiceCommand

logger = logging.getLogger(__name__)


class NaturalLanguageProcessor:
    """Natural language processing for voice commands"""

    def __init__(self):
        """Initialize NLP processor with command patterns and classifiers."""
        self.command_patterns = self._load_command_patterns()
        self.entity_extractor = None
        self.intent_classifier = None

        logger.info("Natural Language Processor initialized")

    def _get_automation_patterns(self) -> Dict[str, Any]:
        """Issue #665: Extracted from _load_command_patterns to reduce function length."""
        return {
            "patterns": [
                r"(?i).*(click|press|tap)\s+(.+)",
                r"(?i).*(type|enter|input)\s+(.+)",
                r"(?i).*(open|start|launch)\s+(.+)",
                r"(?i).*(close|exit|quit)\s+(.+)",
                r"(?i).*(scroll|move)\s+(up|down|left|right)",
                r"(?i).*(fill|complete)\s+(.+form|.+field)",
            ],
            "examples": [
                "click the submit button",
                "type hello world",
                "open the settings menu",
                "scroll down",
            ],
        }

    def _get_navigation_patterns(self) -> Dict[str, Any]:
        """Issue #665: Extracted from _load_command_patterns to reduce function length."""
        return {
            "patterns": [
                r"(?i).*(go to|navigate to|visit)\s+(.+)",
                r"(?i).*(back|forward|home)",
                r"(?i).*(refresh|reload)\s*(page|screen)?",
                r"(?i).*(find|search for)\s+(.+)",
            ],
            "examples": [
                "go to the homepage",
                "go back",
                "search for documentation",
            ],
        }

    def _get_control_patterns(self) -> Dict[str, Any]:
        """Issue #665: Extracted from _load_command_patterns to reduce function length."""
        return {
            "patterns": [
                r"(?i).*(stop|pause|resume|continue)",
                r"(?i).*(cancel|abort)\s*(.+)?",
                r"(?i).*(save|export|download)\s+(.+)",
                r"(?i).*(show|display|hide)\s+(.+)",
            ],
            "examples": [
                "stop the current task",
                "save the document",
                "show the debug panel",
            ],
        }

    def _get_query_patterns(self) -> Dict[str, Any]:
        """Issue #665: Extracted from _load_command_patterns to reduce function length."""
        return {
            "patterns": [
                r"(?i).*(what|how|when|where|why)\s+(.+)",
                r"(?i).*(tell me|explain|describe)\s+(.+)",
                r"(?i).*(status|state)\s+of\s+(.+)",
                r"(?i).*(list|show me)\s+(.+)",
            ],
            "examples": [
                "what is the current status",
                "how do I configure this",
                "list all running processes",
            ],
        }

    def _get_system_patterns(self) -> Dict[str, Any]:
        """Issue #665: Extracted from _load_command_patterns to reduce function length."""
        return {
            "patterns": [
                r"(?i).*(shutdown|restart|reboot)",
                r"(?i).*(update|upgrade|install)\s+(.+)",
                r"(?i).*(settings|preferences|configuration)",
                r"(?i).*(help|assistance|support)",
            ],
            "examples": [
                "open system settings",
                "install new software",
                "show help documentation",
            ],
        }

    def _get_takeover_patterns(self) -> Dict[str, Any]:
        """Issue #665: Extracted from _load_command_patterns to reduce function length."""
        return {
            "patterns": [
                r"(?i).*(take over|take control|manual control)",
                r"(?i).*(emergency|urgent|critical)",
                r"(?i).*(human|manual)\s+(intervention|control)",
                r"(?i).*(stop autonomous|disable auto)",
            ],
            "examples": [
                "take manual control",
                "emergency takeover",
                "stop autonomous mode",
            ],
        }

    def _load_command_patterns(self) -> Dict[str, Any]:
        """Load command patterns and intents"""
        return {
            "automation": self._get_automation_patterns(),
            "navigation": self._get_navigation_patterns(),
            "control": self._get_control_patterns(),
            "query": self._get_query_patterns(),
            "system": self._get_system_patterns(),
            "takeover": self._get_takeover_patterns(),
        }

    def _build_analysis_result(
        self,
        command_type: VoiceCommand,
        intent: str,
        entities: Dict[str, Any],
        parameters: Dict[str, Any],
        confidence: float,
        suggested_actions: List[str],
        requires_confirmation: bool,
        context_needed: bool,
    ) -> VoiceCommandAnalysis:
        """Issue #665: Extracted from analyze_voice_command to reduce function length."""
        command_id = f"voice_cmd_{int(time.time())}"
        return VoiceCommandAnalysis(
            command_id=command_id,
            command_type=command_type,
            intent=intent,
            entities=entities,
            parameters=parameters,
            confidence=confidence,
            suggested_actions=suggested_actions,
            requires_confirmation=requires_confirmation,
            context_needed=context_needed,
        )

    def _log_analysis_outputs(
        self,
        task_context: Any,
        command_type: VoiceCommand,
        intent: str,
        confidence: float,
        entities: Dict[str, Any],
        suggested_actions: List[str],
    ) -> None:
        """Issue #665: Extracted from analyze_voice_command to reduce function length."""
        task_context.set_outputs(
            {
                "command_type": command_type.value,
                "intent": intent,
                "confidence": confidence,
                "entities_count": len(entities),
                "actions_count": len(suggested_actions),
            }
        )
        logger.info(
            f"Voice command analyzed: {command_type.value} - {intent} "
            f"(confidence: {confidence:.2f})"
        )

    async def analyze_voice_command(
        self, transcription: str, context: Optional[Dict[str, Any]] = None
    ) -> VoiceCommandAnalysis:
        """Analyze voice command for intent and parameters"""

        async with task_tracker.track_task(
            "Voice Command Analysis",
            f"Analyzing command: {transcription[:50]}...",
            agent_type="voice_processing",
            priority=TaskPriority.HIGH,
            inputs={"transcription": transcription, "has_context": context is not None},
        ) as task_context:
            try:
                # Step 1: Classify command type first (required for subsequent steps)
                command_type, classification_confidence = await self._classify_command_type(transcription)

                # Step 2: Extract intent and entities in parallel
                intent, entities = await asyncio.gather(
                    self._extract_intent(transcription, command_type),
                    self._extract_entities(transcription, command_type),
                )

                # Step 3: Extract parameters (depends on entities from step 2)
                parameters = await self._extract_parameters(transcription, command_type, entities)

                # Step 4: Run final checks in parallel
                requires_confirmation, context_needed, suggested_actions = await asyncio.gather(
                    self._requires_confirmation(command_type, intent, parameters),
                    self._needs_context(command_type, intent, parameters, context),
                    self._generate_suggested_actions(command_type, intent, entities, parameters),
                )

                # Build result and log outputs
                confidence = classification_confidence * 0.8
                analysis = self._build_analysis_result(
                    command_type, intent, entities, parameters, confidence,
                    suggested_actions, requires_confirmation, context_needed,
                )
                self._log_analysis_outputs(
                    task_context, command_type, intent, confidence, entities, suggested_actions
                )
                return analysis

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Voice command analysis failed: %s", e)
                raise

    async def _classify_command_type(
        self, transcription: str
    ) -> Tuple[VoiceCommand, float]:
        """Classify the type of voice command"""
        max_confidence = 0.0
        best_command = VoiceCommand.UNKNOWN

        # Issue #317: Pre-count matches per command using dict accumulator (O(n^2) -> O(n))
        # Build match counts in single pass through patterns
        match_counts: Dict[str, int] = {}
        pattern_counts: Dict[str, int] = {}

        for command_name, command_data in self.command_patterns.items():
            patterns = command_data["patterns"]
            pattern_counts[command_name] = len(patterns)
            match_counts[command_name] = sum(
                1 for pattern in patterns if re.search(pattern, transcription)
            )

        # Find best command based on confidence
        for command_name, count in match_counts.items():
            if count > 0:
                confidence = count / pattern_counts[command_name]
                if confidence > max_confidence:
                    max_confidence = confidence
                    best_command = VoiceCommand(command_name.upper())

        return best_command, max_confidence

    async def _extract_intent(
        self, transcription: str, command_type: VoiceCommand
    ) -> str:
        """Extract specific intent from transcription (Issue #315 - refactored)."""
        # Use dispatch tables to reduce nesting
        if command_type == VoiceCommand.AUTOMATION:
            return match_intent_from_patterns(
                transcription, AUTOMATION_INTENT_PATTERNS, "automation_action"
            )

        if command_type == VoiceCommand.NAVIGATION:
            return match_intent_from_patterns(
                transcription, NAVIGATION_INTENT_PATTERNS, "navigation_action"
            )

        if command_type == VoiceCommand.QUERY:
            return match_intent_from_patterns(
                transcription, QUERY_INTENT_PATTERNS, "information_query"
            )

        if command_type == VoiceCommand.TAKEOVER:
            return "request_manual_control"

        return "unknown_intent"

    async def _extract_entities(
        self, transcription: str, command_type: VoiceCommand
    ) -> Dict[str, Any]:
        """Extract entities and parameters from transcription"""
        entities = {}

        # Extract common entities using pre-compiled patterns (Issue #380)
        # Numbers
        numbers = NUMBER_RE.findall(transcription)
        if numbers:
            entities["numbers"] = [int(n) for n in numbers]

        # Applications/programs using pre-compiled patterns
        for pattern in APP_PATTERNS_RE:
            matches = pattern.findall(transcription)
            if matches:
                entities.setdefault("applications", []).extend(matches)

        # Directions using pre-compiled pattern
        directions = DIRECTION_RE.findall(transcription)
        if directions:
            entities["directions"] = directions

        # Text content (quoted text) using pre-compiled pattern
        quoted_text = QUOTED_TEXT_RE.findall(transcription)
        if quoted_text:
            entities["quoted_text"] = quoted_text

        # URLs using pre-compiled pattern
        urls = URL_RE.findall(transcription)
        if urls:
            entities["urls"] = urls

        return entities

    async def _extract_parameters(
        self, transcription: str, command_type: VoiceCommand, entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract command parameters"""
        parameters = {}

        # Add entities as parameters
        parameters.update(entities)

        # Command-specific parameters
        if command_type == VoiceCommand.AUTOMATION:
            if "directions" in entities:
                parameters["direction"] = entities["directions"][0]
            if "numbers" in entities and len(entities["numbers"]) > 0:
                parameters["count"] = entities["numbers"][0]

        elif command_type == VoiceCommand.NAVIGATION:
            if "urls" in entities:
                parameters["target_url"] = entities["urls"][0]
            if "applications" in entities:
                parameters["target_app"] = entities["applications"][0]

        # Add transcription for reference
        parameters["original_transcription"] = transcription

        return parameters

    async def _requires_confirmation(
        self, command_type: VoiceCommand, intent: str, parameters: Dict[str, Any]
    ) -> bool:
        """Determine if command requires user confirmation"""

        # Issue #380: Use module-level frozenset for O(1) lookup
        if intent.lower() in HIGH_RISK_INTENTS:
            return True

        if command_type == VoiceCommand.TAKEOVER:
            return True

        if command_type == VoiceCommand.SYSTEM:
            return True

        return False

    async def _needs_context(
        self,
        command_type: VoiceCommand,
        intent: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> bool:
        """Determine if command needs additional context"""

        # Issue #380: Use module-level frozenset for O(1) lookup
        if intent in CONTEXT_DEPENDENT_INTENTS and not context:
            return True

        # Check if parameters are incomplete
        if command_type == VoiceCommand.AUTOMATION:
            if intent == "click_element" and "target_element" not in parameters:
                return True

        return False

    async def _generate_suggested_actions(
        self,
        command_type: VoiceCommand,
        intent: str,
        entities: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> List[str]:
        """Generate suggested actions based on command analysis"""
        actions = []

        if command_type == VoiceCommand.AUTOMATION:
            if intent == "click_element":
                actions.extend(
                    ["identify_target_element", "perform_click", "verify_click_result"]
                )
            elif intent == "type_text":
                actions.extend(
                    ["find_input_field", "focus_field", "type_text", "verify_input"]
                )
            elif intent == "scroll_page":
                actions.extend(
                    [
                        "determine_scroll_direction",
                        "perform_scroll",
                        "check_scroll_result",
                    ]
                )

        elif command_type == VoiceCommand.NAVIGATION:
            if intent == "navigate_to":
                actions.extend(
                    ["validate_target", "perform_navigation", "verify_navigation"]
                )

        elif command_type == VoiceCommand.QUERY:
            actions.extend(["gather_information", "format_response", "provide_answer"])

        elif command_type == VoiceCommand.TAKEOVER:
            actions.extend(
                [
                    "initiate_takeover_request",
                    "notify_human_operator",
                    "pause_autonomous_operations",
                ]
            )

        # Add generic actions
        actions.extend(["log_command", "update_context"])

        return actions
