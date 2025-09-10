"""
Voice Processing System for AutoBot
Advanced voice command recognition, natural language processing, and speech synthesis
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from src.enhanced_memory_manager import EnhancedMemoryManager
from src.enhanced_memory_manager_async import TaskPriority
from src.task_execution_tracker import task_tracker

logger = logging.getLogger(__name__)


class VoiceCommand(Enum):
    """Types of voice commands supported"""

    AUTOMATION = "automation"
    NAVIGATION = "navigation"
    CONTROL = "control"
    QUERY = "query"
    SYSTEM = "system"
    TAKEOVER = "takeover"
    UNKNOWN = "unknown"


class SpeechQuality(Enum):
    """Speech quality levels"""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNUSABLE = "unusable"


@dataclass
class AudioInput:
    """Audio input data structure"""

    audio_id: str
    audio_data: Union[bytes, np.ndarray]
    sample_rate: int
    duration: float
    format: str  # 'wav', 'mp3', 'raw', etc.
    channels: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class SpeechRecognitionResult:
    """Result of speech recognition processing"""

    audio_id: str
    transcription: str
    confidence: float
    language: str
    alternative_transcriptions: List[Dict[str, Any]]
    speech_segments: List[Dict[str, Any]]
    audio_quality: SpeechQuality
    noise_level: float
    processing_time: float
    metadata: Dict[str, Any]


@dataclass
class VoiceCommandAnalysis:
    """Analysis of voice command intent and parameters"""

    command_id: str
    command_type: VoiceCommand
    intent: str
    entities: Dict[str, Any]
    parameters: Dict[str, Any]
    confidence: float
    suggested_actions: List[str]
    requires_confirmation: bool
    context_needed: bool


@dataclass
class SpeechSynthesisRequest:
    """Request for text-to-speech synthesis"""

    text: str
    voice_settings: Dict[str, Any]
    output_format: str
    priority: TaskPriority
    metadata: Dict[str, Any]


class SpeechRecognitionEngine:
    """Speech recognition and transcription engine"""

    def __init__(self):
        self.recognizer = None
        self.language_detector = None
        self.noise_reducer = None

        # Initialize speech recognition components
        self._initialize_speech_recognition()

        logger.info("Speech Recognition Engine initialized")

    def _initialize_speech_recognition(self):
        """Initialize speech recognition components"""
        try:
            # Try to import speech_recognition library
            import speech_recognition as sr

            self.recognizer = sr.Recognizer()

            # Configure recognizer settings
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            self.recognizer.phrase_threshold = 0.3

            logger.info("SpeechRecognition library loaded successfully")

        except ImportError:
            logger.warning("SpeechRecognition library not available")
            self.recognizer = None

        try:
            # Try to initialize language detection
            # from langdetect import detect
            logger.info("Language detection available")
        except ImportError:
            logger.warning("Language detection not available")

    async def transcribe_audio(
        self, audio_input: AudioInput
    ) -> SpeechRecognitionResult:
        """Transcribe audio to text using speech recognition"""

        async with task_tracker.track_task(
            "Speech Recognition",
            f"Transcribing audio: {audio_input.audio_id}",
            agent_type="voice_processing",
            priority=TaskPriority.HIGH,
            inputs={
                "audio_id": audio_input.audio_id,
                "duration": audio_input.duration,
                "sample_rate": audio_input.sample_rate,
            },
        ) as task_context:
            start_time = time.time()

            try:
                # Analyze audio quality first
                audio_quality = await self._analyze_audio_quality(audio_input)
                noise_level = await self._calculate_noise_level(audio_input)

                # Perform speech recognition
                if self.recognizer is not None:
                    transcription_result = await self._perform_speech_recognition(
                        audio_input
                    )
                else:
                    # Fallback when speech recognition not available
                    transcription_result = {
                        "transcription": "[Speech recognition not available]",
                        "confidence": 0.0,
                        "alternatives": [],
                        "language": "unknown",
                    }

                # Detect speech segments
                speech_segments = await self._detect_speech_segments(audio_input)

                processing_time = time.time() - start_time

                # Create result
                result = SpeechRecognitionResult(
                    audio_id=audio_input.audio_id,
                    transcription=transcription_result["transcription"],
                    confidence=transcription_result["confidence"],
                    language=transcription_result["language"],
                    alternative_transcriptions=transcription_result["alternatives"],
                    speech_segments=speech_segments,
                    audio_quality=audio_quality,
                    noise_level=noise_level,
                    processing_time=processing_time,
                    metadata={
                        "original_metadata": audio_input.metadata,
                        "processing_timestamp": time.time(),
                        "engine": (
                            "speech_recognition" if self.recognizer else "placeholder"
                        ),
                    },
                )

                task_context.set_outputs(
                    {
                        "transcription": result.transcription,
                        "confidence": result.confidence,
                        "audio_quality": result.audio_quality.value,
                        "processing_time": processing_time,
                    }
                )

                logger.info(
                    f"Speech recognition completed: {audio_input.audio_id}, "
                    f"confidence: {result.confidence:.2f}"
                )
                return result

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Speech recognition failed: {e}")
                raise

    async def _analyze_audio_quality(self, audio_input: AudioInput) -> SpeechQuality:
        """Analyze audio quality for speech recognition"""
        try:
            # Simple audio quality heuristics
            if audio_input.sample_rate < 8000:
                return SpeechQuality.POOR
            elif audio_input.sample_rate < 16000:
                return SpeechQuality.FAIR
            elif audio_input.duration < 0.5:
                return SpeechQuality.POOR
            elif audio_input.duration > 30:
                return SpeechQuality.FAIR  # Very long audio might have quality issues
            else:
                return SpeechQuality.GOOD

        except Exception as e:
            logger.debug(f"Audio quality analysis failed: {e}")
            return SpeechQuality.UNKNOWN

    async def _calculate_noise_level(self, audio_input: AudioInput) -> float:
        """Calculate background noise level in audio"""
        try:
            if isinstance(audio_input.audio_data, np.ndarray):
                # Calculate RMS (Root Mean Square) as noise estimate
                rms = np.sqrt(np.mean(audio_input.audio_data**2))
                return float(rms)
            else:
                return 0.5  # Default noise level

        except Exception as e:
            logger.debug(f"Noise level calculation failed: {e}")
            return 0.5

    async def _perform_speech_recognition(
        self, audio_input: AudioInput
    ) -> Dict[str, Any]:
        """Perform actual speech recognition"""
        try:
            if self.recognizer is None:
                return {
                    "transcription": "",
                    "confidence": 0.0,
                    "alternatives": [],
                    "language": "unknown",
                }

            # Convert audio data to AudioData format
            audio_data = self._convert_to_audio_data(audio_input)

            # Perform recognition with multiple engines
            transcription_results = []

            # Try Google Speech Recognition (requires internet)
            try:
                result = self.recognizer.recognize_google(audio_data, show_all=True)
                if result and "alternative" in result:
                    for alt in result["alternative"]:
                        transcription_results.append(
                            {
                                "text": alt.get("transcript", ""),
                                "confidence": alt.get("confidence", 0.0),
                                "engine": "google",
                            }
                        )
            except Exception as e:
                logger.debug(f"Google Speech Recognition failed: {e}")

            # Try Sphinx (offline) as fallback
            if not transcription_results:
                try:
                    text = self.recognizer.recognize_sphinx(audio_data)
                    transcription_results.append(
                        {
                            "text": text,
                            "confidence": 0.7,  # Sphinx doesn't provide confidence
                            "engine": "sphinx",
                        }
                    )
                except Exception as e:
                    logger.debug(f"Sphinx Recognition failed: {e}")

            # Process results
            if transcription_results:
                best_result = max(transcription_results, key=lambda x: x["confidence"])
                return {
                    "transcription": best_result["text"],
                    "confidence": best_result["confidence"],
                    "alternatives": transcription_results[1:],  # Other alternatives
                    "language": "en",  # Would detect language in real implementation
                }
            else:
                return {
                    "transcription": "",
                    "confidence": 0.0,
                    "alternatives": [],
                    "language": "unknown",
                }

        except Exception as e:
            logger.error(f"Speech recognition processing failed: {e}")
            return {
                "transcription": "",
                "confidence": 0.0,
                "alternatives": [],
                "language": "unknown",
            }

    def _convert_to_audio_data(self, audio_input: AudioInput):
        """Convert audio input to speech_recognition AudioData format"""
        try:
            import speech_recognition as sr

            if isinstance(audio_input.audio_data, bytes):
                # Convert bytes to AudioData
                audio_data = sr.AudioData(
                    audio_input.audio_data, audio_input.sample_rate, 2  # 16-bit samples
                )
            elif isinstance(audio_input.audio_data, np.ndarray):
                # Convert numpy array to bytes
                audio_bytes = (
                    (audio_input.audio_data * 32767).astype(np.int16).tobytes()
                )
                audio_data = sr.AudioData(audio_bytes, audio_input.sample_rate, 2)
            else:
                raise ValueError(
                    f"Unsupported audio data type: {type(audio_input.audio_data)}"
                )

            return audio_data

        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            raise

    async def _detect_speech_segments(
        self, audio_input: AudioInput
    ) -> List[Dict[str, Any]]:
        """Detect speech segments in audio for timing information"""
        try:
            # Simple speech segment detection
            # In a real implementation, this would use VAD (Voice Activity Detection)
            segments = [
                {
                    "start_time": 0.0,
                    "end_time": audio_input.duration,
                    "confidence": 0.8,
                    "type": "speech",
                }
            ]

            return segments

        except Exception as e:
            logger.debug(f"Speech segmentation failed: {e}")
            return []


class NaturalLanguageProcessor:
    """Natural language processing for voice commands"""

    def __init__(self):
        self.command_patterns = self._load_command_patterns()
        self.entity_extractor = None
        self.intent_classifier = None

        logger.info("Natural Language Processor initialized")

    def _load_command_patterns(self) -> Dict[str, Any]:
        """Load command patterns and intents"""
        return {
            "automation": {
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
            },
            "navigation": {
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
            },
            "control": {
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
            },
            "query": {
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
            },
            "system": {
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
            },
            "takeover": {
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
            },
        }

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
                # Classify command type
                (
                    command_type,
                    classification_confidence,
                ) = await self._classify_command_type(transcription)

                # Extract intent and entities
                intent = await self._extract_intent(transcription, command_type)
                entities = await self._extract_entities(transcription, command_type)
                parameters = await self._extract_parameters(
                    transcription, command_type, entities
                )

                # Determine if confirmation needed
                requires_confirmation = await self._requires_confirmation(
                    command_type, intent, parameters
                )

                # Check if additional context needed
                context_needed = await self._needs_context(
                    command_type, intent, parameters, context
                )

                # Generate suggested actions
                suggested_actions = await self._generate_suggested_actions(
                    command_type, intent, entities, parameters
                )

                # Calculate overall confidence
                overall_confidence = (
                    classification_confidence * 0.8
                )  # Weight by classification confidence

                command_id = f"voice_cmd_{int(time.time())}"

                analysis = VoiceCommandAnalysis(
                    command_id=command_id,
                    command_type=command_type,
                    intent=intent,
                    entities=entities,
                    parameters=parameters,
                    confidence=overall_confidence,
                    suggested_actions=suggested_actions,
                    requires_confirmation=requires_confirmation,
                    context_needed=context_needed,
                )

                task_context.set_outputs(
                    {
                        "command_type": command_type.value,
                        "intent": intent,
                        "confidence": overall_confidence,
                        "entities_count": len(entities),
                        "actions_count": len(suggested_actions),
                    }
                )

                logger.info(
                    f"Voice command analyzed: {command_type.value} - {intent} "
                    f"(confidence: {overall_confidence:.2f})"
                )
                return analysis

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Voice command analysis failed: {e}")
                raise

    async def _classify_command_type(
        self, transcription: str
    ) -> Tuple[VoiceCommand, float]:
        """Classify the type of voice command"""
        import re

        max_confidence = 0.0
        best_command = VoiceCommand.UNKNOWN

        for command_name, command_data in self.command_patterns.items():
            patterns = command_data["patterns"]
            match_count = 0

            for pattern in patterns:
                if re.search(pattern, transcription):
                    match_count += 1

            if match_count > 0:
                confidence = match_count / len(patterns)
                if confidence > max_confidence:
                    max_confidence = confidence
                    best_command = VoiceCommand(command_name.upper())

        return best_command, max_confidence

    async def _extract_intent(
        self, transcription: str, command_type: VoiceCommand
    ) -> str:
        """Extract specific intent from transcription"""
        import re

        # Simple intent extraction based on command type
        if command_type == VoiceCommand.AUTOMATION:
            if re.search(r"(?i)click", transcription):
                return "click_element"
            elif re.search(r"(?i)type|enter", transcription):
                return "type_text"
            elif re.search(r"(?i)open|start", transcription):
                return "open_application"
            elif re.search(r"(?i)scroll", transcription):
                return "scroll_page"
            else:
                return "automation_action"

        elif command_type == VoiceCommand.NAVIGATION:
            if re.search(r"(?i)go to|navigate", transcription):
                return "navigate_to"
            elif re.search(r"(?i)back", transcription):
                return "navigate_back"
            elif re.search(r"(?i)search", transcription):
                return "search_content"
            else:
                return "navigation_action"

        elif command_type == VoiceCommand.QUERY:
            if re.search(r"(?i)what", transcription):
                return "what_query"
            elif re.search(r"(?i)how", transcription):
                return "how_query"
            elif re.search(r"(?i)status", transcription):
                return "status_query"
            else:
                return "information_query"

        elif command_type == VoiceCommand.TAKEOVER:
            return "request_manual_control"

        else:
            return "unknown_intent"

    async def _extract_entities(
        self, transcription: str, command_type: VoiceCommand
    ) -> Dict[str, Any]:
        """Extract entities and parameters from transcription"""
        import re

        entities = {}

        # Extract common entities
        # Numbers
        numbers = re.findall(r"\b\d+\b", transcription)
        if numbers:
            entities["numbers"] = [int(n) for n in numbers]

        # Applications/programs
        app_patterns = [
            r"(?i)\b(chrome|firefox|safari|edge|browser)\b",
            r"(?i)\b(notepad|word|excel|powerpoint)\b",
            r"(?i)\b(calculator|terminal|cmd|console)\b",
        ]

        for pattern in app_patterns:
            matches = re.findall(pattern, transcription)
            if matches:
                entities.setdefault("applications", []).extend(matches)

        # Directions
        directions = re.findall(
            r"(?i)\b(up|down|left|right|top|bottom|center)\b", transcription
        )
        if directions:
            entities["directions"] = directions

        # Text content (quoted text)
        quoted_text = re.findall(r'"([^"]*)"', transcription)
        if quoted_text:
            entities["quoted_text"] = quoted_text

        # URLs
        urls = re.findall(r"https?://[^\s]+", transcription)
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

        # Commands that typically require confirmation
        high_risk_intents = [
            "shutdown",
            "restart",
            "delete",
            "uninstall",
            "request_manual_control",
            "emergency",
        ]

        if intent.lower() in [i.lower() for i in high_risk_intents]:
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

        # Check if command references elements that need screen context
        context_dependent_intents = [
            "click_element",
            "type_text",
            "scroll_page",
            "navigate_to",
        ]

        if intent in context_dependent_intents and not context:
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


class TextToSpeechEngine:
    """Text-to-speech synthesis engine"""

    def __init__(self):
        self.tts_engine = None
        self.voice_settings = {"rate": 150, "volume": 0.8, "voice_id": "default"}

        self._initialize_tts_engine()
        logger.info("Text-to-Speech Engine initialized")

    def _initialize_tts_engine(self):
        """Initialize TTS engine"""
        try:
            # Try pyttsx3 for offline TTS
            import pyttsx3

            self.tts_engine = pyttsx3.init()

            # Configure voice settings
            self.tts_engine.setProperty("rate", self.voice_settings["rate"])
            self.tts_engine.setProperty("volume", self.voice_settings["volume"])

            logger.info("pyttsx3 TTS engine initialized")

        except ImportError:
            logger.warning("pyttsx3 not available, TTS will be limited")
            self.tts_engine = None
        except Exception as e:
            logger.error(f"TTS engine initialization failed: {e}")
            self.tts_engine = None

    async def synthesize_speech(self, request: SpeechSynthesisRequest) -> bytes:
        """Convert text to speech audio"""

        async with task_tracker.track_task(
            "Speech Synthesis",
            f"Converting text to speech: {request.text[:50]}...",
            agent_type="voice_processing",
            priority=request.priority,
            inputs={
                "text_length": len(request.text),
                "output_format": request.output_format,
            },
        ) as task_context:
            try:
                if self.tts_engine is None:
                    # Return empty audio data when TTS not available
                    task_context.set_outputs({"error": "TTS engine not available"})
                    return b""

                # Apply voice settings from request
                if "rate" in request.voice_settings:
                    self.tts_engine.setProperty("rate", request.voice_settings["rate"])

                if "volume" in request.voice_settings:
                    self.tts_engine.setProperty(
                        "volume", request.voice_settings["volume"]
                    )

                # Generate speech
                if request.output_format.lower() == "wav":
                    audio_data = await self._generate_wav_audio(request.text)
                else:
                    audio_data = await self._generate_default_audio(request.text)

                task_context.set_outputs(
                    {
                        "audio_size": len(audio_data),
                        "format": request.output_format,
                        "success": len(audio_data) > 0,
                    }
                )

                logger.info(
                    f"Speech synthesis completed: {len(audio_data)} bytes generated"
                )
                return audio_data

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Speech synthesis failed: {e}")
                return b""

    async def _generate_wav_audio(self, text: str) -> bytes:
        """Generate WAV audio data"""
        try:
            import os
            import tempfile

            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name

            # Generate speech to file
            self.tts_engine.save_to_file(text, temp_path)
            self.tts_engine.runAndWait()

            # Read file content
            with open(temp_path, "rb") as audio_file:
                audio_data = audio_file.read()

            # Clean up
            os.unlink(temp_path)

            return audio_data

        except Exception as e:
            logger.error(f"WAV audio generation failed: {e}")
            return b""

    async def _generate_default_audio(self, text: str) -> bytes:
        """Generate audio in default format"""
        # For now, return empty bytes when specific format not supported
        logger.warning("Default audio format not implemented")
        return b""


class VoiceProcessingSystem:
    """Main voice processing system coordinator"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.speech_recognition = SpeechRecognitionEngine()
        self.nlp_processor = NaturalLanguageProcessor()
        self.tts_engine = TextToSpeechEngine()

        # Processing history
        self.voice_command_history: List[VoiceCommandAnalysis] = []
        self.max_history = 20

        logger.info("Voice Processing System initialized")

    async def process_voice_command(
        self, audio_input: AudioInput, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Complete voice command processing pipeline"""

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

                # Step 2: Natural Language Processing
                command_analysis = await self.nlp_processor.analyze_voice_command(
                    speech_result.transcription, context
                )

                # Step 3: Generate response and actions
                response = await self._generate_command_response(
                    command_analysis, speech_result, context
                )

                # Step 4: Update history
                self.voice_command_history.append(command_analysis)
                if len(self.voice_command_history) > self.max_history:
                    self.voice_command_history = self.voice_command_history[
                        -self.max_history :
                    ]

                task_context.set_outputs(
                    {
                        "transcription": speech_result.transcription,
                        "command_type": command_analysis.command_type.value,
                        "confidence": command_analysis.confidence,
                        "requires_confirmation": command_analysis.requires_confirmation,
                        "actions_count": len(command_analysis.suggested_actions),
                    }
                )

                logger.info(
                    f"Voice command processed successfully: "
                    f"{command_analysis.command_type.value}"
                )
                return response

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Voice command processing failed: {e}")
                raise

    async def _generate_command_response(
        self,
        command_analysis: VoiceCommandAnalysis,
        speech_result: SpeechRecognitionResult,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate comprehensive response to voice command"""

        response = {
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
            "execution_plan": {
                "suggested_actions": command_analysis.suggested_actions,
                "requires_confirmation": command_analysis.requires_confirmation,
                "context_needed": command_analysis.context_needed,
                "estimated_duration": await self._estimate_execution_duration(
                    command_analysis
                ),
            },
            "next_steps": await self._determine_next_steps(command_analysis, context),
        }

        # Add confirmation request if needed
        if command_analysis.requires_confirmation:
            response["confirmation_required"] = {
                "message": f"Confirm execution of: {command_analysis.intent}",
                "parameters": command_analysis.parameters,
                "risk_level": await self._assess_risk_level(command_analysis),
            }

        # Add context request if needed
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
        high_risk_types = {VoiceCommand.SYSTEM, VoiceCommand.TAKEOVER}
        high_risk_intents = ["shutdown", "restart", "delete", "uninstall"]

        if command_analysis.command_type in high_risk_types:
            return "high"

        if any(
            intent in command_analysis.intent.lower() for intent in high_risk_intents
        ):
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

            if command_analysis.intent in ["click_element", "type_text"]:
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
                "timestamp": cmd.metadata.get("timestamp", 0),
            }
            for cmd in history
        ]

    def get_system_status(self) -> Dict[str, Any]:
        """Get voice processing system status"""
        return {
            "speech_recognition_available": self.speech_recognition.recognizer
            is not None,
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


# Global instance
voice_processing_system = VoiceProcessingSystem()
