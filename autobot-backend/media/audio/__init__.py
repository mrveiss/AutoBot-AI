# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Audio Processing Pipeline
# Issue #735, #9044

"""Audio processing pipeline and components."""

from media.audio.diarization_service import (
    DiarizationService,
    SpeakerSegment,
    get_diarization_service,
    is_diarization_available,
)
from media.audio.ffmpeg_service import FFmpegService, get_ffmpeg_service
from media.audio.pipeline import AudioPipeline

__all__ = [
    "AudioPipeline",
    "FFmpegService",
    "get_ffmpeg_service",
    "DiarizationService",
    "SpeakerSegment",
    "get_diarization_service",
    "is_diarization_available",
]
