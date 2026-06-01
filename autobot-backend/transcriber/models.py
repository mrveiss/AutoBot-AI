# autobot-backend/transcriber/models.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pydantic request/response schemas for the transcriber module."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    user_id: str


class RecordingOut(BaseModel):
    id: int
    project_id: int
    filename: str
    duration: float | None
    status: Literal["pending", "processing", "complete", "error"]
    speaker_count: int
    process_seconds: float | None
    engine_used: str | None
    language_detected: str | None
    uploaded_at: datetime
    failure_stage: str | None
    failure_reason: str | None


class SpeakerOut(BaseModel):
    id: int
    recording_id: int
    label: str
    display_name: str
    language: str | None


class SpeakerUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class SegmentOut(BaseModel):
    id: int
    recording_id: int
    speaker_id: int | None
    start_time: float
    end_time: float
    text: str
    original_text: str
    is_edited: bool
    is_overlap: bool


class SegmentUpdate(BaseModel):
    text: str = Field(min_length=0, max_length=5000)


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class NoteUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class NoteOut(BaseModel):
    id: int
    segment_id: int
    recording_id: int
    content: str
    created_at: datetime


class TranscriptOut(BaseModel):
    recording: RecordingOut
    speakers: list[SpeakerOut]
    segments: list[SegmentOut]


class ExportRequest(BaseModel):
    format: Literal["docx", "pdf", "srt", "vtt"]
    include_timestamps: bool = True
    include_notes: bool = True
    include_speaker_names: bool = True


class AiAskRequest(BaseModel):
    action: Literal["summarize", "key_facts", "protocol", "custom"]
    custom_question: str | None = None


class KbPushRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=200)


class KbPushStatus(BaseModel):
    pushed: bool
    pushed_at: datetime | None
    kb_collection_id: str | None
    pushed_by: str | None


class AiAskRequest(BaseModel):
    action: Literal["summarize", "key_facts", "protocol", "custom"]
    custom_question: str | None = None


class KbPushRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=200)


class KbPushStatus(BaseModel):
    pushed: bool
    pushed_at: datetime | None
    kb_collection_id: str | None
    pushed_by: str | None
