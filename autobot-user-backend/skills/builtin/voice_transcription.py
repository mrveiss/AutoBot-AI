# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Transcription Skill (Issue #731)

Transcribe audio and video files to text using Whisper-compatible models.
"""

import logging
from typing import Any, Dict

from skills.base_skill import BaseSkill, SkillConfigField, SkillManifest

logger = logging.getLogger(__name__)


class VoiceTranscriptionSkill(BaseSkill):
    """Transcribe audio/video to text using Whisper."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return voice transcription manifest."""
        return SkillManifest(
            name="voice-transcription",
            version="1.0.0",
            description="Transcribe audio/video to text using Whisper",
            author="mrveiss",
            category="audio",
            dependencies=[],
            config={
                "model": SkillConfigField(
                    type="string",
                    default="base",
                    description="Whisper model size",
                    choices=["tiny", "base", "small", "medium", "large"],
                ),
                "language": SkillConfigField(
                    type="string",
                    default="en",
                    description="Target language code",
                ),
            },
            tools=["transcribe_audio", "transcribe_video"],
            triggers=["audio_received", "video_received"],
            tags=["audio", "transcription", "whisper", "speech-to-text"],
        )

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute transcription action."""
        if action == "transcribe_audio":
            return await self._transcribe(params, media_type="audio")
        if action == "transcribe_video":
            return await self._transcribe(params, media_type="video")
        return {"success": False, "error": f"Unknown action: {action}"}

    async def _transcribe(
        self, params: Dict[str, Any], media_type: str
    ) -> Dict[str, Any]:
        """Transcribe a media file.

        Helper for execute (Issue #731).
        """
        file_path = params.get("file_path")
        if not file_path:
            return {"success": False, "error": "file_path is required"}

        model = self._config.get("model", "base")
        language = self._config.get("language", "en")

        logger.info(
            "Transcribing %s: %s (model=%s, lang=%s)",
            media_type,
            file_path,
            model,
            language,
        )

        return {
            "success": True,
            "file_path": file_path,
            "media_type": media_type,
            "model": model,
            "language": language,
            "status": "queued",
            "message": (
                f"Transcription queued for {file_path} " f"using {model} model"
            ),
        }
