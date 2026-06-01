# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transcript API schemas for AI analysis and KB integration (MVA-2176).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnalysisType(str, Enum):
    """Supported transcript analysis types."""

    SUMMARIZE = "summarize"
    KEY_FACTS = "key_facts"
    PROTOCOL = "protocol"
    CUSTOM = "custom"


class TranscriptAnalyzeRequest(BaseModel):
    """Request for WebSocket transcript analysis."""

    analysis_type: AnalysisType = Field(..., description="Type of analysis to perform")
    custom_prompt: Optional[str] = Field(None, description="Custom prompt for CUSTOM analysis type")
    context: Optional[str] = Field(None, description="Additional context for analysis")


class TranscriptKBPushRequest(BaseModel):
    """Request to push transcript segment to Knowledge Base."""

    segment_text: str = Field(..., description="Transcript segment text to push to KB")
    segment_start: Optional[float] = Field(None, description="Start time of segment in seconds")
    segment_end: Optional[float] = Field(None, description="End time of segment in seconds")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata for KB entry")


class TranscriptKBPushResponse(BaseModel):
    """Response from KB push operation."""

    success: bool = Field(..., description="Whether KB push succeeded")
    doc_id: Optional[str] = Field(None, description="Document ID in KB if successful")
    message: str = Field(..., description="Status message")
