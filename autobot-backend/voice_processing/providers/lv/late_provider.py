# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LATE Provider for Latvian Speech Recognition

Local LATE (Latvian Automatic Transcription Engine) provider.
Part of Issue MVA-2185.
"""

import asyncio
import json
import os
import subprocess
from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import SpeechProvider, TranscriptSegment

logger = get_logger(__name__)


class LateProvider(SpeechProvider):
    """LATE provider for Latvian speech recognition."""

    def __init__(self, late_binary_path: Optional[str] = None):
        """Initialize LATE provider.

        Args:
            late_binary_path: Path to LATE binary (defaults to env var or 'late')
        """
        self.late_binary = late_binary_path or os.getenv("LATE_BINARY_PATH", "late")
        self._check_availability()

    def _check_availability(self):
        """Check if LATE binary is available."""
        try:
            result = subprocess.run(
                [self.late_binary, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8',
            )
            if result.returncode == 0:
                logger.info(f"LATE binary available: {self.late_binary}")
            else:
                logger.warning(f"LATE binary check failed: {result.stderr}")
        except FileNotFoundError:
            logger.warning(
                f"LATE binary not found at: {self.late_binary}. "
                "Install LATE or set LATE_BINARY_PATH environment variable."
            )
        except Exception as e:
            logger.warning(f"LATE availability check failed: {e}")

    async def transcribe(
        self, audio_path: str, language: Optional[str] = None
    ) -> List[TranscriptSegment]:
        """Transcribe audio using LATE.

        Args:
            audio_path: Path to audio file
            language: Language hint (ignored for LATE - Latvian only)

        Returns:
            List of transcript segments
        """
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return []

        try:
            # Run LATE transcription
            # LATE typically outputs JSON with segments
            cmd = [
                self.late_binary,
                "transcribe",
                audio_path,
                "--format",
                "json",
                "--segments",
            ]

            logger.info(f"Running LATE transcription: {' '.join(cmd)}")

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._run_late_command, cmd
            )

            if result is None:
                logger.error("LATE transcription failed")
                return []

            # Parse LATE JSON output
            segments = self._parse_late_output(result)
            logger.info(
                f"LATE transcription completed: {len(segments)} segments"
            )
            return segments

        except Exception as e:
            logger.error(f"LATE transcription failed: {e}")
            return []

    def _run_late_command(self, cmd: List[str]) -> Optional[str]:
        """Run LATE command and return output.

        Args:
            cmd: Command and arguments

        Returns:
            JSON output string or None on failure
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                encoding='utf-8',
            )

            if result.returncode != 0:
                logger.error(f"LATE command failed: {result.stderr}")
                return None

            return result.stdout

        except subprocess.TimeoutExpired:
            logger.error("LATE command timed out after 5 minutes")
            return None
        except Exception as e:
            logger.error(f"LATE command execution failed: {e}")
            return None

    def _parse_late_output(self, json_output: str) -> List[TranscriptSegment]:
        """Parse LATE JSON output into TranscriptSegments.

        Args:
            json_output: JSON string from LATE

        Returns:
            List of transcript segments
        """
        try:
            data = json.loads(json_output)

            # LATE format (assumed):
            # {
            #   "segments": [
            #     {
            #       "text": "...",
            #       "start": 0.0,
            #       "end": 1.5,
            #       "confidence": 0.95
            #     },
            #     ...
            #   ]
            # }

            segments = []
            for seg in data.get("segments", []):
                segments.append(
                    TranscriptSegment(
                        text=seg.get("text", ""),
                        start_time=seg.get("start", 0.0),
                        end_time=seg.get("end", 0.0),
                        confidence=seg.get("confidence", 0.0),
                        language="lv",
                    )
                )

            return segments

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LATE JSON output: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to parse LATE output: {e}")
            return []

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "LATE"

    @property
    def supported_languages(self) -> List[str]:
        """Return supported languages."""
        return ["lv", "lat"]  # Latvian (BCP-47 and ISO 639-2)
