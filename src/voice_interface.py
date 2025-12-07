# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

try:
    import speech_recognition as sr

    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    sr = None
    SPEECH_RECOGNITION_AVAILABLE = False

try:
    import pyttsx3

    PYTTSX3_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    PYTTSX3_AVAILABLE = False

import asyncio
import os
from typing import Any, Dict, Optional

import yaml


class VoiceInterface:
    """Voice interface for speech-to-text and text-to-speech operations."""

    def __init__(self, config_path="config/config.yaml"):
        """Initialize voice interface with configuration and speech engines."""
        self.config = self._load_config(config_path)
        self.voice_config = self.config.get("voice_interface", {})

        self.recognizer = sr.Recognizer() if SPEECH_RECOGNITION_AVAILABLE else None
        self.tts_engine = self._init_tts_engine() if PYTTSX3_AVAILABLE else None

        self.continuous_listening = self.voice_config.get("continuous_listening", False)
        self.push_to_talk_key = self.voice_config.get(
            "push_to_talk_key", None
        )  # e.g., 'space'

        availability_status = []
        if not SPEECH_RECOGNITION_AVAILABLE:
            availability_status.append("Speech Recognition unavailable")
        if not PYTTSX3_AVAILABLE:
            availability_status.append("Text-to-Speech unavailable")

        status_msg = (
            "VoiceInterface initialized. Continuous listening: "
            f"{self.continuous_listening}"
        )
        if availability_status:
            status_msg += f" ({', '.join(availability_status)})"

        print(status_msg)

    def _load_config(self, config_path):
        """Load YAML configuration from file path."""
        with open(config_path, "r") as f:
            return yaml.safe_load(f)

    def _init_tts_engine(self):
        """Initialize pyttsx3 text-to-speech engine if available."""
        if not PYTTSX3_AVAILABLE:
            return None
        engine = pyttsx3.init()
        # Optional: Configure voice properties
        # voices = engine.getProperty('voices')
        # engine.setProperty('voice', voices[0].id)
        # # Change index for different voices
        # engine.setProperty('rate', 150)  # Speed of speech
        # engine.setProperty('volume', 1.0) # Volume (0.0 to 1.0)
        return engine

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
            print("Listening for speech...")
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
                print("Processing speech...")
                # Use Google Web Speech API for recognition
                text = self.recognizer.recognize_google(audio)
                print(f"Recognized: {text}")
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
            print(f"Speaking: {text}")
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

    # Placeholder for Vosk integration
    async def _listen_vosk(self) -> Dict[str, Any]:
        """
        Placeholder for Vosk-based speech recognition (offline).
        Requires vosk and sounddevice.
        """
        # from vosk import Model, KaldiRecognizer
        # import sounddevice as sd
        # model = Model(lang="en-us") # Download model first
        # recognizer = KaldiRecognizer(model, 16000)
        # with sd.RawInputStream(samplerate=16000, blocksize=8000,
        #                       dtype='int16', channels=1) as device:
        #     while True:
        #         data = device.read(8000)[0]
        #         if recognizer.AcceptWaveform(data):
        #             result = json.loads(recognizer.Result())
        #             return {
        #                 "status": "success",
        #                 "text": result.get("text", ""),
        #             }
        return {
            "status": "error",
            "message": "Vosk integration is a placeholder. Not implemented.",
        }

    # Placeholder for Coqui TTS integration
    async def _speak_coqui_tts(self, text: str) -> Dict[str, Any]:
        """
        Placeholder for Coqui TTS text-to-speech.
        Requires coqui_tts library and downloaded models.
        """
        # from TTS.api import TTS
        # tts = TTS("tts_models/en/ljspeech/tacotron2-DDC", gpu=False)
        # # Example model
        # tts.tts_to_file(text=text, file_path="output.wav")
        # # Play the audio file
        # import soundfile as sf
        # import sounddevice as sd
        # data, samplerate = sf.read("output.wav")
        # sd.play(data, samplerate)
        # sd.wait()
        return {
            "status": "error",
            "message": "Coqui TTS integration is a placeholder. Not implemented.",
        }


# Example Usage (for testing)
if __name__ == "__main__":
    # Ensure config.yaml exists for testing
    if not os.path.exists("config/config.yaml"):
        print("config/config.yaml not found. Copying from template for testing.")
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

        print("\n--- Testing Speech Recognition (speak into mic) ---")
        # result = await vi.listen_and_convert_to_text()
        # if result["status"] == "success":
        #     print(f"You said: {result['text']}")
        # else:
        #     print(f"Speech recognition failed: {result['message']}")

        print("\n--- Testing Text-to-Speech ---")
        # await vi.speak_text("Hello, I am AutoBot. How can I help you today?")

        print(
            "\n--- Testing continuous listening (requires manual stop "
            "or external trigger) ---"
        )
        # if vi.continuous_listening:
        #     print("Continuous listening enabled. Say something...")
        #     while True:
        #         text_result = await vi.listen_and_convert_to_text(
        #             timeout=None, phrase_time_limit=None)
        #         if text_result["status"] == "success":
        #             print(f"Continuous: {text_result['text']}")
        #             if "stop listening" in text_result['text'].lower():
        #                 await vi.speak_text("Stopping continuous listening.")
        #                 break
        #         elif text_result["status"] == "timeout":
        #             print("No speech detected, continuing to listen...")
        #         else:
        #             print(
        #                 "Error in continuous listening: "
        #                 f"{text_result['message']}"
        #             )
        #         await asyncio.sleep(0.1)  # Small delay to prevent
        #         # busy-waiting

    asyncio.run(test_voice_interface())
