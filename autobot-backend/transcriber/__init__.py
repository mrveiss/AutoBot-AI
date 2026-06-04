# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Module
# Issue #9044

"""Transcriber module for audio transcription with speaker diarization."""

from transcriber.database import TranscriberDatabase, get_transcriber_db
from transcriber.models import Recording, RecordingStatus, TranscriptionSegment
from transcriber.orchestrator import TranscriberOrchestrator, get_transcriber_orchestrator

__all__ = [
    "TranscriberDatabase",
    "get_transcriber_db",
    "Recording",
    "RecordingStatus",
    "TranscriptionSegment",
    "TranscriberOrchestrator",
    "get_transcriber_orchestrator",
]
