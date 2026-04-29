# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Typed payload models for chat_sessions.py DataResponse endpoints.

One model per endpoint, named <Noun>Data, used as DataResponse[<Noun>Data]
to give FastAPI enough type information to generate correct OpenAPI schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from constants.threshold_constants import CategoryDefaults
from type_defs.common import Metadata


class SessionMessagesData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}."""

    messages: List[Any]
    session_id: str
    total_count: int
    page: int
    per_page: int


class SessionListData(BaseModel):
    """data payload for GET /chat/sessions (all scope variants).

    The ``scope``, ``org_id``, and ``team_id`` fields are only present when
    the request uses scope=org or scope=team query params.
    ``intentional_empty`` is set when the authenticated user has zero sessions.
    """

    sessions: List[Any]
    count: int
    scope: Optional[str] = None
    org_id: Optional[str] = None
    team_id: Optional[str] = None
    intentional_empty: Optional[bool] = None


class SessionCreateData(BaseModel):
    """data payload for POST /chat/sessions."""

    id: Optional[str] = None
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    last_modified: Optional[str] = None


class SessionUpdateData(BaseModel):
    """data payload for PUT /chat/sessions/{session_id}."""

    id: Optional[str] = None
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    last_modified: Optional[str] = None


class FileHandlingResult(BaseModel):
    """Nested file-handling sub-payload within SessionDeleteData."""

    files_handled: bool
    action_taken: str
    files_deleted: Optional[int] = None
    files_transferred: Optional[int] = None
    files_failed: Optional[int] = None
    error: Optional[str] = None


class TerminalCleanupResult(BaseModel):
    """Nested terminal-cleanup sub-payload within SessionDeleteData."""

    terminal_sessions_closed: int
    pending_approvals_cleared: int
    error: Optional[str] = None


class KbCleanupResult(BaseModel):
    """Nested KB-cleanup sub-payload within SessionDeleteData."""

    facts_deleted: int
    facts_preserved: int
    cleanup_error: Optional[str] = None


class TranscriptCleanupResult(BaseModel):
    """Nested transcript-cleanup sub-payload within SessionDeleteData."""

    transcript_deleted: bool
    error: Optional[str] = None


class SessionDeleteData(BaseModel):
    """data payload for DELETE /chat/sessions/{session_id}."""

    session_id: str
    deleted: bool
    file_handling: Optional[FileHandlingResult] = None
    terminal_cleanup: Optional[TerminalCleanupResult] = None
    kb_cleanup: Optional[KbCleanupResult] = None
    transcript_cleanup: Optional[TranscriptCleanupResult] = None


class ChatResetData(BaseModel):
    """data payload for POST /chat/reset."""

    session_id: str
    reset: bool
    clear_context: bool
    keep_system_prompt: bool


class ActivityAddData(BaseModel):
    """data payload for POST /chat/sessions/{session_id}/activities."""

    activity_id: Optional[str] = None
    entity_id: Optional[str] = None
    stored: bool


class ActivityBatchData(BaseModel):
    """data payload for POST /chat/sessions/{session_id}/activities/batch."""

    total: int
    stored: int
    failed: int
    stored_ids: Optional[List[str]] = None


class SessionActivitiesData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}/activities."""

    activities: List[Any]
    total: int
    session_id: Optional[str] = None


class SessionShareData(BaseModel):
    """data payload for POST /chat/sessions/{session_id}/share."""

    session_id: str
    shared_with: List[str]
    include_knowledge: bool
    facts_shared: Optional[Any] = None


class FactPreview(BaseModel):
    """Individual fact entry within SessionSharePreviewData."""

    id: str
    content: str
    full_content: str
    metadata: Optional[Dict[str, Any]] = None


class SessionSharePreviewData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}/share/preview."""

    session_id: str
    fact_count: int
    facts: List[FactPreview]


class SessionCheckpointClearData(BaseModel):
    """data payload for DELETE /sessions/{session_id}/checkpoints."""

    session_id: str


# ---------------------------------------------------------------------------
# chat_sessions.py request schemas (#6042)
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    """Session creation model"""

    title: Optional[str] = Field(None, max_length=200, description="Session title")
    team_id: Optional[str] = Field(None, description="Team ID for team-scoped sessions (#684)")
    metadata: Optional[Metadata] = Field(default_factory=dict, description="Session metadata")


class SessionUpdate(BaseModel):
    """Session update model"""

    title: Optional[str] = Field(None, max_length=200, description="New session title")
    metadata: Optional[Metadata] = Field(None, description="Updated metadata")


class ActivityCreate(BaseModel):
    """Single activity creation model"""

    activity_id: str = Field(..., description="Frontend-generated activity ID")
    type: str = Field(..., description="Activity type: terminal, file, browser, desktop")
    user_id: str = Field(..., description="User who performed the activity")
    content: str = Field(..., max_length=10000, description="Activity content/description")
    secrets_used: list[str] = Field(default_factory=list, description="Secret IDs used")
    metadata: Optional[Metadata] = Field(default_factory=dict, description="Activity metadata")
    timestamp: str = Field(..., description="ISO format timestamp from frontend")


class ActivityBatchCreate(BaseModel):
    """Batch activity creation model"""

    activities: list[ActivityCreate] = Field(..., description="List of activities to create")


class SessionShareRequest(BaseModel):
    """Request to share a session with users"""

    share_with: list[str] = Field(..., min_length=1, description="User IDs to share with")
    include_knowledge: bool = Field(False, description="Include KB facts from this session")
    knowledge_facts: Optional[list[str]] = Field(
        None, description="Specific fact IDs to share (all if omitted)"
    )


class ChatResetRequest(BaseModel):
    """Request model for chat reset"""

    session_id: Optional[str] = Field(None, description="Session ID to reset (optional)")
    clear_context: bool = Field(True, description="Clear conversation context")
    keep_system_prompt: bool = Field(True, description="Keep system prompt after reset")


class ChatMessage(BaseModel):
    """Chat message model for requests"""

    content: str = Field(..., min_length=1, max_length=50000, description="Message content")
    role: str = Field(
        default=CategoryDefaults.ROLE_USER,
        pattern="^(user|assistant|system)$",
        description="Message role",
    )
    session_id: Optional[str] = Field(None, description="Chat session ID")
    message_type: Optional[str] = Field("text", description="Message type")
    metadata: Optional[Metadata] = Field(default_factory=dict, description="Additional metadata")
    language: Optional[str] = Field(
        None,
        description="Preferred response language code (e.g. 'en', 'es', 'de'). "
        "Overrides personality language when set.",
    )


class ChatResponse(BaseModel):
    """Chat response model"""

    content: str
    role: str = CategoryDefaults.ROLE_ASSISTANT
    session_id: str
    message_id: str
    timestamp: datetime
    metadata: Metadata = Field(default_factory=dict)


class MessageHistory(BaseModel):
    """Message history response model"""

    messages: List[Metadata]
    session_id: str
    total_count: int
    page: int = 1
    per_page: int = 50


class EnhancedChatMessage(BaseModel):
    """Enhanced chat message with AI Stack integration."""

    content: str = Field(..., min_length=1, max_length=50000, description="Message content")
    role: str = Field(
        default=CategoryDefaults.ROLE_USER,
        pattern="^(user|assistant|system)$",
        description="Message role",
    )
    session_id: Optional[str] = Field(None, description="Chat session ID")
    message_type: Optional[str] = Field("text", description="Message type")
    metadata: Optional[Metadata] = Field(default_factory=dict, description="Additional metadata")
    language: Optional[str] = Field(
        None,
        description="Preferred response language code (e.g. 'en', 'es', 'de'). "
        "Overrides personality language when set.",
    )
    use_ai_stack: bool = Field(True, description="Whether to use AI Stack for enhanced responses")
    use_knowledge_base: bool = Field(True, description="Whether to include knowledge base context")
    response_style: str = Field("conversational", description="Response style preference")
    include_sources: bool = Field(True, description="Whether to include source citations")


class ChatPreferences(BaseModel):
    """Chat preferences for customizing AI behavior."""

    response_length: str = Field("medium", description="Preferred response length (short, medium, long)")
    technical_level: str = Field("adaptive", description="Technical complexity level")
    include_reasoning: bool = Field(False, description="Include reasoning steps in responses")
    fact_checking: bool = Field(True, description="Enable fact checking against knowledge base")


class TranslateRequest(BaseModel):
    """Request model for direct translation."""

    text: str = Field(..., min_length=1, max_length=50000, description="Text to translate")
    target_language: str = Field(..., min_length=1, max_length=50, description="Target language name")
    source_language: Optional[str] = Field(None, description="Source language (auto-detect if omitted)")


class DetectLanguageRequest(BaseModel):
    """Request model for language detection."""

    text: str = Field(..., min_length=1, max_length=50000, description="Text to detect language of")
