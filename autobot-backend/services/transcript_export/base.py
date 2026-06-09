# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Base classes and data models for transcript export.

Provides abstract exporter interface and Pydantic models for transcript data.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """A single transcript segment with timestamp and speaker."""

    id: str
    transcript_id: str
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    speaker_label: str = Field(..., description="Display name for speaker")
    text: str
    confidence: Optional[float] = None
    notes: Optional[str] = None

    @property
    def duration(self) -> float:
        """Calculate segment duration in seconds."""
        return self.end_time - self.start_time


class Transcript(BaseModel):
    """Complete transcript with metadata and segments."""

    id: str
    project_id: Optional[str] = None
    title: str
    audio_file: Optional[str] = None
    duration_seconds: float
    language: str
    created_at: Optional[datetime] = None
    segments: List[Segment] = Field(default_factory=list)


class BaseExporter(ABC):
    """Abstract base class for transcript exporters."""

    def __init__(self, transcript: Transcript):
        """Initialize exporter with transcript data.

        Args:
            transcript: Transcript object to export
        """
        self.transcript = transcript

    @abstractmethod
    async def generate(self) -> bytes:
        """Generate export file content.

        Returns:
            bytes: Generated file content
        """
        ...

    @abstractmethod
    def get_mime_type(self) -> str:
        """Return MIME type for this format.

        Returns:
            str: MIME type (e.g., "application/pdf")
        """
        ...

    @abstractmethod
    def get_file_extension(self) -> str:
        """Return file extension for this format.

        Returns:
            str: File extension (e.g., ".pdf")
        """
        ...

    def get_filename(self) -> str:
        """Generate filename from transcript title and extension.

        Returns:
            str: Sanitized filename
        """
        # Sanitize title: remove special characters
        safe_title = "".join(c for c in self.transcript.title if c.isalnum() or c in (" ", "-", "_"))
        safe_title = safe_title.strip().replace(" ", "_")
        return f"{safe_title}{self.get_file_extension()}"
