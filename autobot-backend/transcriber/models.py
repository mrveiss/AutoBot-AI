# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Data Models
# Issue #9044

"""Data models for transcriber module."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RecordingStatus(str, Enum):
    """Recording processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Recording:
    """Recording record from database."""

    id: int
    filename: str
    file_path: str
    user_id: str
    duration: Optional[float]
    language: Optional[str]
    status: RecordingStatus
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TranscriptionSegment:
    """Transcription segment with speaker and timestamp."""

    id: int
    recording_id: int
    speaker_label: str
    start_time: float
    end_time: float
    text: str
    confidence: float
    created_at: datetime


# Pydantic schemas for API


class RecordingCreate(BaseModel):
    """Request schema for creating a recording."""

    filename: str = Field(..., description="Original filename")
    file_path: str = Field(..., description="Path to audio file")


class RecordingResponse(BaseModel):
    """Response schema for recording."""

    id: int
    filename: str
    file_path: str
    user_id: str
    duration: Optional[float]
    language: Optional[str]
    status: RecordingStatus
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class SegmentResponse(BaseModel):
    """Response schema for transcription segment."""

    id: int
    recording_id: int
    speaker_label: str
    start_time: float
    end_time: float
    text: str
    confidence: float
    created_at: datetime


class ProcessingResponse(BaseModel):
    """Response schema for processing request."""

    recording_id: int
    status: RecordingStatus
    segments_count: int
    message: str
