# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Data Models
# Issue #9044, #9214

"""Data models for transcriber module."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

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
    """Request schema for creating a recording.

    Note: file_path is now server-managed after upload.
    Use POST /api/transcriber/upload to upload files first.

    Issue #9214: Removed client-provided file_path to prevent path injection
    """

    filename: str = Field(..., description="Original filename")
    # file_path removed - now server-managed via upload endpoint


class UploadResponse(BaseModel):
    """Response schema for file upload."""

    file_path: str = Field(..., description="Server-managed file path")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")


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


class AiAskRequest(BaseModel):
    """Request schema for AI analysis."""

    action: Literal["summarize", "key_facts", "protocol", "custom"]
    custom_question: str | None = None
