# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Interface - Speech-to-text and text-to-speech operations.

Supports multiple backends:
- Speech Recognition: Google Web Speech API, Vosk (offline)
- Text-to-Speech: pyttsx3, Coqui TTS, gTTS

Updated in Issue #454 to use real Vosk/Coqui TTS integration.
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Check speech recognition availability
try:
    import speech_recognition as sr

    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    sr = None
    SPEECH_RECOGNITION_AVAILABLE = False

# Check pyttsx3 availability
try:
    import pyttsx3

    PYTTSX3_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    PYTTSX3_AVAILABLE = False

# Check Vosk availability
try:
    from vosk import KaldiRecognizer, Model

    VOSK_AVAILABLE = True
except ImportError:
    KaldiRecognizer = None
    Model = None
    VOSK_AVAILABLE = False

# Check Coqui TTS availability
try:
    from TTS.api import TTS as CoquiTTS

    COQUI_TTS_AVAILABLE = True
except ImportError:
    CoquiTTS = None
    COQUI_TTS_AVAILABLE = False

# Check gTTS availability (Google Text-to-Speech - online fallback)
try:
    from gtts import gTTS

    GTTS_AVAILABLE = True
except ImportError:
    gTTS = None
    GTTS_AVAILABLE = False

# Check sounddevice for audio playback
try:
    import sounddevice as sd
    import soundfile as sf

    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    sf = None
    SOUNDDEVICE_AVAILABLE = False


def _check_vosk_dependencies(vosk_model_path: str, model) -> Optional[Dict[str, Any]]:
    """
    Check Vosk dependencies and return error dict if not available.

    Returns:
        Error dict if dependencies missing, None if all OK
    """
    if not VOSK_AVAILABLE:
        return {
            "status": "error",
            "message": "Vosk not available. Install with: pip install vosk",
        }

    if not SOUNDDEVICE_AVAILABLE:
        return {
            "status": "error",
            "message": (
                "sounddevice not available. "
                "Install with: pip install sounddevice soundfile"
            ),
        }

    if model is None:
        return {
            "status": "error",
            "message": (
                f"Vosk model not found at {vosk_model_path}. "
                "Download from https://alphacephei.com/vosk/models"
            ),
        }

    return None


def _check_vosk_timeout(
    elapsed: float, timeout: Optional[float], speech_detected: bool
) -> Optional[Dict[str, Any]]:
    """Issue #665: Extracted from _vosk_recognize_blocking to reduce function length.

    Check if speech recognition has timed out waiting for speech to start.
    """
    if timeout and elapsed > timeout and not speech_detected:
        return {"status": "timeout", "message": "No speech detected within timeout."}
    return None


def _check_vosk_phrase_limit(
    elapsed: float, phrase_time_limit: Optional[float], recognizer
) -> Optional[Dict[str, Any]]:
    """Issue #665: Extracted from _vosk_recognize_blocking to reduce function length.

    Check phrase time limit and return final result if exceeded.
    """
    if phrase_time_limit and elapsed > phrase_time_limit:
        partial = json.loads(recognizer.FinalResult())
        text = partial.get("text", "").strip()
        if text:
            return {"status": "success", "text": text}
        return {"status": "no_match", "message": "Could not understand audio."}
    return None


def _process_vosk_audio_data(recognizer, data) -> Optional[Dict[str, Any]]:
    """Issue #665: Extracted from _vosk_recognize_blocking to reduce function length.

    Process audio data through recognizer and return result if speech recognized.
    """
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        text = result.get("text", "").strip()
        if text:
            return {"status": "success", "text": text}
    return None


def _vosk_recognize_blocking(
    model,
    timeout: Optional[float],
    phrase_time_limit: Optional[float],
) -> Dict[str, Any]:
    """Issue #665: Refactored blocking Vosk recognition using extracted helpers."""
    import queue

    sample_rate = 16000
    block_size = 8000
    recognizer = KaldiRecognizer(model, sample_rate)
    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            logger.warning("Vosk audio callback status: %s", status)
        audio_queue.put(bytes(indata))

    with sd.RawInputStream(
        samplerate=sample_rate, blocksize=block_size,
        dtype="int16", channels=1, callback=callback,
    ):
        logger.debug("Vosk listening started...")
        start_time = asyncio.get_event_loop().time()
        speech_detected = False

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time

            if result := _check_vosk_timeout(elapsed, timeout, speech_detected):
                return result
            if result := _check_vosk_phrase_limit(elapsed, phrase_time_limit, recognizer):
                return result

            try:
                data = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if result := _process_vosk_audio_data(recognizer, data):
                return result
            speech_detected = True


class VoiceInterface:
    """Voice interface for speech-to-text and text-to-speech operations.

    Supports multiple backends:
    - STT: Google Web Speech API (online), Vosk (offline)
    - TTS: pyttsx3, Coqui TTS (neural), gTTS (online)
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize voice interface with configuration and speech engines.

        Args:
            config_path: Path to YAML configuration file.
        """
        self.config = self._load_config(config_path)
        self.voice_config = self.config.get("voice_interface", {})

        # Speech recognition engines
        self.recognizer = sr.Recognizer() if SPEECH_RECOGNITION_AVAILABLE else None

        # Vosk offline model initialization
        self._vosk_model: Optional[Model] = None
        self._vosk_model_path = self.voice_config.get(
            "vosk_model_path",
            os.getenv("AUTOBOT_VOSK_MODEL_PATH", "models/vosk-model-small-en-us-0.15"),
        )

        # TTS engines
        self.tts_engine = self._init_tts_engine() if PYTTSX3_AVAILABLE else None

        # Coqui TTS initialization
        self._coqui_tts: Optional[CoquiTTS] = None
        self._coqui_model = self.voice_config.get(
            "coqui_model",
            os.getenv("AUTOBOT_COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC"),
        )

        # Configuration options
        self.continuous_listening = self.voice_config.get("continuous_listening", False)
        self.push_to_talk_key = self.voice_config.get("push_to_talk_key", None)
        self.preferred_stt = self.voice_config.get("preferred_stt", "google")
        self.preferred_tts = self.voice_config.get("preferred_tts", "pyttsx3")

        # Log availability status
        self._log_availability_status()

    def _log_availability_status(self) -> None:
        """Log availability status of all voice backends."""
        stt_backends = []
        tts_backends = []

        if SPEECH_RECOGNITION_AVAILABLE:
            stt_backends.append("Google Web Speech")
        if VOSK_AVAILABLE:
            stt_backends.append("Vosk (offline)")

        if PYTTSX3_AVAILABLE:
            tts_backends.append("pyttsx3")
        if COQUI_TTS_AVAILABLE:
            tts_backends.append("Coqui TTS")
        if GTTS_AVAILABLE:
            tts_backends.append("gTTS")

        stt_status = ", ".join(stt_backends) if stt_backends else "None available"
        tts_status = ", ".join(tts_backends) if tts_backends else "None available"

        logger.info(
            "VoiceInterface initialized - STT: [%s], TTS: [%s], "
            "Continuous listening: %s",
            stt_status,
            tts_status,
            self.continuous_listening,
        )

        if not stt_backends:
            logger.warning(
                "No STT backends available. Install speech_recognition or vosk."
            )
        if not tts_backends:
            logger.warning(
                "No TTS backends available. Install pyttsx3, TTS (coqui), or gtts."
            )

    def _load_config(self, config_path: str) -> dict:
        """Load YAML configuration from file path.

        Args:
            config_path: Path to configuration file.

        Returns:
            Loaded configuration dictionary.
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("Config file not found: %s, using defaults", config_path)
            return {}
        except Exception as e:
            logger.error("Failed to load config from %s: %s", config_path, e)
            return {}

    def _init_tts_engine(self) -> Optional[pyttsx3.Engine]:
        """Initialize pyttsx3 text-to-speech engine if available.

        Returns:
            Initialized pyttsx3 engine or None.
        """
        if not PYTTSX3_AVAILABLE:
            return None
        try:
            engine = pyttsx3.init()
            # Configure voice properties from config
            rate = self.voice_config.get("pyttsx3_rate", 150)
            volume = self.voice_config.get("pyttsx3_volume", 1.0)
            engine.setProperty("rate", rate)
            engine.setProperty("volume", volume)
            logger.debug("pyttsx3 engine initialized (rate=%d, volume=%.1f)", rate, volume)
            return engine
        except Exception as e:
            logger.error("Failed to initialize pyttsx3: %s", e)
            return None

    def _get_vosk_model(self) -> Optional[Model]:
        """Get or initialize Vosk model (lazy loading).

        Returns:
            Vosk Model instance or None if unavailable.
        """
        if not VOSK_AVAILABLE:
            return None

        if self._vosk_model is None:
            if not os.path.exists(self._vosk_model_path):
                logger.warning(
                    "Vosk model not found at %s. Download from "
                    "https://alphacephei.com/vosk/models",
                    self._vosk_model_path,
                )
                return None
            try:
                logger.info("Loading Vosk model from %s", self._vosk_model_path)
                self._vosk_model = Model(self._vosk_model_path)
                logger.info("Vosk model loaded successfully")
            except Exception as e:
                logger.error("Failed to load Vosk model: %s", e)
                return None

        return self._vosk_model

    def _get_coqui_tts(self) -> Optional[CoquiTTS]:
        """Get or initialize Coqui TTS engine (lazy loading).

        Returns:
            Coqui TTS instance or None if unavailable.
        """
        if not COQUI_TTS_AVAILABLE:
            return None

        if self._coqui_tts is None:
            try:
                logger.info("Initializing Coqui TTS with model: %s", self._coqui_model)
                # Use GPU if available, fallback to CPU
                use_gpu = self.voice_config.get("coqui_use_gpu", False)
                self._coqui_tts = CoquiTTS(self._coqui_model, gpu=use_gpu)
                logger.info("Coqui TTS initialized successfully (GPU=%s)", use_gpu)
            except Exception as e:
                logger.error("Failed to initialize Coqui TTS: %s", e)
                return None

        return self._coqui_tts

    async def listen_and_convert_to_text(
        self, timeout: Optional[int] = 5, phrase_time_limit: Optional[int] = 5
    ) -> Dict[str, Any]:
        """
        Captures audio from the microphone and converts it to text.

        Args:
            timeout (int): Seconds to wait for a phrase to start.
            phrase_time_limit (int): Seconds to listen for a phrase
                if no speech is detected.

        Returns:
            Dict[str, Any]: Status and recognized text or error message.
        """
        if not SPEECH_RECOGNITION_AVAILABLE or not self.recognizer:
            return {
                "status": "error",
                "message": (
                    "Speech recognition not available. Install speech_recognition "
                    "and pyaudio."
                ),
            }

        with sr.Microphone() as source:
            # Adjust for ambient noise
            self.recognizer.adjust_for_ambient_noise(source)
            logger.info("Listening for speech...")
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
                logger.info("Processing speech...")
                # Use Google Web Speech API for recognition
                text = self.recognizer.recognize_google(audio)
                logger.info("Recognized: %s", text)
                return {"status": "success", "text": text}
            except sr.WaitTimeoutError:
                return {
                    "status": "timeout",
                    "message": "No speech detected within timeout.",
                }
            except sr.UnknownValueError:
                return {
                    "status": "no_match",
                    "message": "Could not understand audio.",
                }
            except sr.RequestError as e:
                return {
                    "status": "error",
                    "message": (
                        "Could not request results from Google "
                        f"Speech Recognition service; {e}"
                    ),
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": (
                        "An unexpected error occurred during "
                        f"speech recognition: {e}"
                    ),
                }

    async def speak_text(self, text: str) -> Dict[str, Any]:
        """
        Converts text to speech and plays it aloud.
        """
        if not PYTTSX3_AVAILABLE or not self.tts_engine:
            return {
                "status": "error",
                "message": "Text-to-speech not available. Install pyttsx3.",
            }

        try:
            logger.info("Speaking: %s", text)
            # pyttsx3 runAndWait() is blocking, so run in a thread
            # or process pool executor
            # to avoid blocking the asyncio event loop.
            # For simplicity in this example, we'll just run it directly,
            # but in a real async app, this needs careful handling.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.tts_engine.say, text)
            await loop.run_in_executor(None, self.tts_engine.runAndWait)
            return {
                "status": "success",
                "message": "Text spoken successfully.",
            }
        except Exception as e:
            return {"status": "error", "message": f"Error speaking text: {e}"}

    async def _listen_vosk(
        self,
        timeout: Optional[float] = 10.0,
        phrase_time_limit: Optional[float] = 5.0,
    ) -> Dict[str, Any]:
        """
        Vosk-based offline speech recognition.

        Uses Vosk for local, offline speech-to-text conversion.
        Requires vosk and sounddevice packages, plus a downloaded model.

        Args:
            timeout: Maximum time to wait for speech start (seconds).
            phrase_time_limit: Maximum time to listen for a phrase (seconds).

        Returns:
            Dict with status and recognized text or error message.
        """
        model = self._get_vosk_model()
        dep_error = _check_vosk_dependencies(self._vosk_model_path, model)
        if dep_error:
            return dep_error

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                _vosk_recognize_blocking,
                model,
                timeout,
                phrase_time_limit,
            )
            logger.debug("Vosk recognition result: %s", result)
            return result

        except Exception as e:
            logger.error("Vosk recognition error: %s", e)
            return {
                "status": "error",
                "message": f"Vosk recognition failed: {str(e)}",
            }

    async def _speak_coqui_tts(self, text: str) -> Dict[str, Any]:
        """
        Coqui TTS text-to-speech synthesis and playback (Issue #665: refactored).

        Uses Coqui TTS for high-quality neural text-to-speech.
        Requires TTS package and sounddevice for playback.

        Args:
            text: Text to convert to speech.

        Returns:
            Dict with status and message.
        """
        # Check dependencies
        dep_error = self._check_coqui_dependencies()
        if dep_error:
            return dep_error

        tts = self._get_coqui_tts()
        if tts is None:
            return {
                "status": "error",
                "message": (
                    f"Failed to initialize Coqui TTS with model: {self._coqui_model}"
                ),
            }

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, self._synthesize_and_play_blocking, tts, text
            )
            return result

        except Exception as e:
            logger.error("Coqui TTS error: %s", e)
            return {
                "status": "error",
                "message": f"Coqui TTS failed: {str(e)}",
            }

    def _check_coqui_dependencies(self) -> Optional[Dict[str, Any]]:
        """Check Coqui TTS dependencies (Issue #665: extracted helper)."""
        if not COQUI_TTS_AVAILABLE:
            return {
                "status": "error",
                "message": "Coqui TTS not available. Install with: pip install TTS",
            }

        if not SOUNDDEVICE_AVAILABLE:
            return {
                "status": "error",
                "message": (
                    "sounddevice not available for playback. "
                    "Install with: pip install sounddevice soundfile"
                ),
            }
        return None

    def _synthesize_and_play_blocking(self, tts: Any, text: str) -> Dict[str, Any]:
        """Blocking TTS synthesis and playback (Issue #665: extracted helper)."""
        # Create temporary file for audio output
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            output_path = tmp_file.name

        try:
            # Synthesize speech to file
            logger.debug("Synthesizing speech: %s", text[:50])
            tts.tts_to_file(text=text, file_path=output_path)

            # Read and play the audio
            data, samplerate = sf.read(output_path)
            logger.debug(
                "Playing audio: %d samples at %d Hz",
                len(data),
                samplerate,
            )
            sd.play(data, samplerate)
            sd.wait()

            return {
                "status": "success",
                "message": "Text spoken successfully via Coqui TTS.",
            }
        finally:
            # Clean up temporary file
            if os.path.exists(output_path):
                os.unlink(output_path)

    async def _speak_gtts(self, text: str) -> Dict[str, Any]:
        """
        gTTS (Google Text-to-Speech) synthesis and playback.

        Uses gTTS as an online fallback for text-to-speech.
        Requires gtts package and sounddevice for playback.

        Args:
            text: Text to convert to speech.

        Returns:
            Dict with status and message.
        """
        if not GTTS_AVAILABLE:
            return {
                "status": "error",
                "message": "gTTS not available. Install with: pip install gtts",
            }

        if not SOUNDDEVICE_AVAILABLE:
            return {
                "status": "error",
                "message": (
                    "sounddevice not available for playback. "
                    "Install with: pip install sounddevice soundfile"
                ),
            }

        try:
            loop = asyncio.get_running_loop()

            def _synthesize_and_play():
                """Blocking gTTS synthesis and playback in executor."""
                with tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False
                ) as tmp_file:
                    output_path = tmp_file.name

                try:
                    # Synthesize speech to file
                    logger.debug("gTTS synthesizing: %s", text[:50])
                    lang = self.voice_config.get("gtts_lang", "en")
                    tts_obj = gTTS(text=text, lang=lang)
                    tts_obj.save(output_path)

                    # Read and play the audio
                    data, samplerate = sf.read(output_path)
                    sd.play(data, samplerate)
                    sd.wait()

                    return {
                        "status": "success",
                        "message": "Text spoken successfully via gTTS.",
                    }
                finally:
                    if os.path.exists(output_path):
                        os.unlink(output_path)

            result = await loop.run_in_executor(None, _synthesize_and_play)
            return result

        except Exception as e:
            logger.error("gTTS error: %s", e)
            return {
                "status": "error",
                "message": f"gTTS failed: {str(e)}",
            }

    async def listen_with_fallback(
        self,
        timeout: Optional[int] = 5,
        phrase_time_limit: Optional[int] = 5,
    ) -> Dict[str, Any]:
        """
        Listen for speech with automatic fallback between backends.

        Tries preferred STT backend first, falls back to alternatives.

        Args:
            timeout: Seconds to wait for speech start.
            phrase_time_limit: Seconds to listen for a phrase.

        Returns:
            Dict with status and recognized text or error.
        """
        backends = []

        # Order based on preference
        if self.preferred_stt == "vosk":
            if VOSK_AVAILABLE:
                backends.append(("vosk", self._listen_vosk))
            if SPEECH_RECOGNITION_AVAILABLE:
                backends.append(("google", self.listen_and_convert_to_text))
        else:
            if SPEECH_RECOGNITION_AVAILABLE:
                backends.append(("google", self.listen_and_convert_to_text))
            if VOSK_AVAILABLE:
                backends.append(("vosk", self._listen_vosk))

        if not backends:
            return {
                "status": "error",
                "message": "No STT backends available.",
            }

        errors = []
        for name, method in backends:
            logger.debug("Trying STT backend: %s", name)
            try:
                result = await method(timeout=timeout, phrase_time_limit=phrase_time_limit)
                if result.get("status") == "success":
                    result["backend"] = name
                    return result
                elif result.get("status") in ("timeout", "no_match"):
                    # These are expected conditions, not errors
                    result["backend"] = name
                    return result
                else:
                    errors.append(f"{name}: {result.get('message', 'Unknown error')}")
            except Exception as e:
                errors.append(f"{name}: {str(e)}")
                logger.warning("STT backend %s failed: %s", name, e)

        return {
            "status": "error",
            "message": f"All STT backends failed: {'; '.join(errors)}",
        }

    async def speak_with_fallback(self, text: str) -> Dict[str, Any]:
        """
        Speak text with automatic fallback between TTS backends.

        Tries preferred TTS backend first, falls back to alternatives.

        Args:
            text: Text to speak.

        Returns:
            Dict with status and message.
        """
        backends = []

        # Order based on preference
        if self.preferred_tts == "coqui":
            if COQUI_TTS_AVAILABLE:
                backends.append(("coqui", self._speak_coqui_tts))
            if PYTTSX3_AVAILABLE:
                backends.append(("pyttsx3", self.speak_text))
            if GTTS_AVAILABLE:
                backends.append(("gtts", self._speak_gtts))
        elif self.preferred_tts == "gtts":
            if GTTS_AVAILABLE:
                backends.append(("gtts", self._speak_gtts))
            if PYTTSX3_AVAILABLE:
                backends.append(("pyttsx3", self.speak_text))
            if COQUI_TTS_AVAILABLE:
                backends.append(("coqui", self._speak_coqui_tts))
        else:  # Default: pyttsx3
            if PYTTSX3_AVAILABLE:
                backends.append(("pyttsx3", self.speak_text))
            if COQUI_TTS_AVAILABLE:
                backends.append(("coqui", self._speak_coqui_tts))
            if GTTS_AVAILABLE:
                backends.append(("gtts", self._speak_gtts))

        if not backends:
            return {
                "status": "error",
                "message": "No TTS backends available.",
            }

        errors = []
        for name, method in backends:
            logger.debug("Trying TTS backend: %s", name)
            try:
                result = await method(text)
                if result.get("status") == "success":
                    result["backend"] = name
                    return result
                else:
                    errors.append(f"{name}: {result.get('message', 'Unknown error')}")
            except Exception as e:
                errors.append(f"{name}: {str(e)}")
                logger.warning("TTS backend %s failed: %s", name, e)

        return {
            "status": "error",
            "message": f"All TTS backends failed: {'; '.join(errors)}",
        }


# Example Usage (for testing)
if __name__ == "__main__":
    # Ensure config.yaml exists for testing
    if not os.path.exists("config/config.yaml"):
        logger.info("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r") as f_template:
            with open("config/config.yaml", "w") as f_config:
                f_config.write(f_template.read())

    # Add voice_interface section to config.yaml for testing
    with open("config/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    if "voice_interface" not in cfg:
        cfg["voice_interface"] = {
            "enabled": True,
            "continuous_listening": False,
            "push_to_talk_key": "space",
        }
        with open("config/config.yaml", "w") as f:
            yaml.safe_dump(cfg, f, indent=2)

    async def test_voice_interface():
        """Test voice interface with speech recognition and TTS demos."""
        # Test function placeholder - VoiceInterface initialization removed
        # to avoid unused variable warning
        pass  # Placeholder function

        logger.info("\n--- Testing Speech Recognition (speak into mic) ---")
        # result = await vi.listen_and_convert_to_text()
        # if result["status"] == "success":
        #     logger.info("You said: {result['text']}")
        # else:
        #     logger.info("Speech recognition failed: {result['message']}")

        logger.info("\n--- Testing Text-to-Speech ---")
        # await vi.speak_text("Hello, I am AutoBot. How can I help you today?")

        print(
            "\n--- Testing continuous listening (requires manual stop "
            "or external trigger) ---"
        )
        # if vi.continuous_listening:
        #     logger.info("Continuous listening enabled. Say something...")
        #     while True:
        #         text_result = await vi.listen_and_convert_to_text(
        #             timeout=None, phrase_time_limit=None)
        #         if text_result["status"] == "success":
        #             logger.info("Continuous: {text_result['text']}")
        #             if "stop listening" in text_result['text'].lower():
        #                 await vi.speak_text("Stopping continuous listening.")
        #                 break
        #         elif text_result["status"] == "timeout":
        #             logger.info("No speech detected, continuing to listen...")
        #         else:
        #             print(
        #                 "Error in continuous listening: "
        #                 f"{text_result['message']}"
        #             )
        #         await asyncio.sleep(0.1)  # Small delay to prevent
        #         # busy-waiting

    asyncio.run(test_voice_interface())
