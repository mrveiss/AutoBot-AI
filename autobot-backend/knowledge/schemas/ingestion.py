# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ingestion pipeline response schemas.

Covers document/fact upload endpoints under ``/api/knowledge_base/*``:
``/add_text``, ``/facts``, ``/url``, ``/upload``, ``/audio``, and
``/clear_all``.  These are the response shapes returned after content is
written into the knowledge base.

Split from ``facts.py`` per Issue #5486.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AddTextResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/add_text``.

    Legacy text-ingestion endpoint (newer frontend uses /facts — see
    :class:`AddFactResponse`). Returns the fact_id plus ownership
    metadata echo for audit visibility.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'success' on insert")
    message: str = ""
    fact_id: str | None = None
    text_length: int = 0
    title: str = ""
    source: str = ""
    access_level: str | None = None
    visibility: str | None = None


class AddFactResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/facts`` (frontend-compatible).

    Returns a truncated content echo (first 100 chars) — callers that
    need the full content should re-fetch via ``GET /fact/{key}``.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: str | None = None
    title: str = ""
    content: str = Field("", description="Truncated to first 100 chars + ellipsis")
    message: str = ""


class AddUrlResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/url``.

    Same envelope as :class:`AddFactResponse`; the content field carries
    the truncated fetched page text.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: str | None = None
    title: str = ""
    content: str = ""
    message: str = ""


class UploadFileResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/upload``.

    Adds ``word_count`` over the base upload envelope.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: str | None = None
    title: str = ""
    content: str = ""
    word_count: int = 0
    message: str = ""


class AudioIngestResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/audio`` and ``/audio/upload``.

    Returned by the shared ``_ingest_audio_source`` helper after Whisper
    transcription completes.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: str | None = None
    title: str = ""
    word_count: int = 0
    message: str = ""


class ClearAllResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/clear_all``.

    The route deletes nothing (#21048, #17038): it proposes a knowledge wipe, and the wipe runs only after a
    human approves it. ``approval_id`` names the pending approval; ``items_removed`` and ``items_before`` stay
    for compatibility and are 0 because nothing was removed by this request.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="Approval status of the wipe request, 'pending' until a human decides")
    items_removed: int = 0
    items_before: int = 0
    message: str = ""
    approval_id: str | None = Field(None, description="Id of the pending wipe approval in the Approvals inbox")
    action: str | None = Field(None, description="The approval action the wipe runs under")
