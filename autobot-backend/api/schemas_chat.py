# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Typed payload models for chat_sessions.py and chat.py DataResponse endpoints.

One model per endpoint, named <Noun>Data, used as DataResponse[<Noun>Data]
to give FastAPI enough type information to generate correct OpenAPI schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

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
    scope: str | None = None
    org_id: str | None = None
    team_id: str | None = None
    intentional_empty: bool | None = None


class SessionCreateData(BaseModel):
    """data payload for POST /chat/sessions."""

    id: str | None = None
    title: str | None = None
    metadata: Dict[str, Any] | None = None
    created_at: str | None = None
    last_modified: str | None = None


class SessionUpdateData(BaseModel):
    """data payload for PUT /chat/sessions/{session_id}."""

    id: str | None = None
    title: str | None = None
    metadata: Dict[str, Any] | None = None
    created_at: str | None = None
    last_modified: str | None = None


class FileHandlingResult(BaseModel):
    """Nested file-handling sub-payload within SessionDeleteData."""

    files_handled: bool
    action_taken: str
    files_deleted: int | None = None
    files_transferred: int | None = None
    files_failed: int | None = None
    error: str | None = None


class TerminalCleanupResult(BaseModel):
    """Nested terminal-cleanup sub-payload within SessionDeleteData."""

    terminal_sessions_closed: int
    pending_approvals_cleared: int
    error: str | None = None


class KbCleanupResult(BaseModel):
    """Nested KB-cleanup sub-payload within SessionDeleteData."""

    facts_deleted: int
    facts_preserved: int
    cleanup_error: str | None = None


class TranscriptCleanupResult(BaseModel):
    """Nested transcript-cleanup sub-payload within SessionDeleteData."""

    transcript_deleted: bool
    error: str | None = None


class SessionDeleteData(BaseModel):
    """data payload for DELETE /chat/sessions/{session_id}."""

    session_id: str
    deleted: bool
    file_handling: FileHandlingResult | None = None
    terminal_cleanup: TerminalCleanupResult | None = None
    kb_cleanup: KbCleanupResult | None = None
    transcript_cleanup: TranscriptCleanupResult | None = None


class ChatResetData(BaseModel):
    """data payload for POST /chat/reset."""

    session_id: str
    reset: bool
    clear_context: bool
    keep_system_prompt: bool


class ActivityAddData(BaseModel):
    """data payload for POST /chat/sessions/{session_id}/activities."""

    activity_id: str | None = None
    entity_id: str | None = None
    stored: bool


class ActivityBatchData(BaseModel):
    """data payload for POST /chat/sessions/{session_id}/activities/batch."""

    total: int
    stored: int
    failed: int
    stored_ids: List[str] | None = None


class SessionActivitiesData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}/activities."""

    activities: List[Any]
    total: int
    session_id: str | None = None


class SessionShareData(BaseModel):
    """data payload for POST /chat/sessions/{session_id}/share."""

    session_id: str
    shared_with: List[str]
    include_knowledge: bool
    facts_shared: Any | None = None


class FactPreview(BaseModel):
    """Individual fact entry within SessionSharePreviewData."""

    id: str
    content: str
    full_content: str
    metadata: Dict[str, Any] | None = None


class SessionSharePreviewData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}/share/preview."""

    session_id: str
    fact_count: int
    facts: List[FactPreview]


class SessionCheckpointClearData(BaseModel):
    """data payload for DELETE /sessions/{session_id}/checkpoints."""

    session_id: str


# ---------------------------------------------------------------------------
# chat.py response schemas (#6410)
# ---------------------------------------------------------------------------


class ThinkingMetadata(BaseModel):
    """Thinking mode metadata for Claude 3.7+ reasoning models (MVA-3090)."""

    used: bool = Field(..., description="Whether thinking mode was used for this response")
    tokens_used: int | None = Field(None, description="Number of thinking tokens consumed (null if thinking not used)")


class ChatMessageData(BaseModel):
    """data payload for POST /chat and POST /chat/message (alias).

    Both endpoints return the dict produced by ``process_chat_message``
    in chat.py.
    """

    content: str
    role: str
    session_id: str
    message_id: str | None = None
    timestamp: str | None = None
    metadata: Dict[str, Any] | None = None
    thinking_metadata: ThinkingMetadata | None = Field(
        None, description="Thinking mode metadata (Claude 3.7+ reasoning models)"
    )


class ChatHealthComponents(BaseModel):
    """Component health subsection of ChatHealthData (kept for import compat)."""

    chat_history_manager: str
    llm_service: str


class ChatHealthData(BaseModel):
    """Response shape for GET /chat/health and GET /health-ai-stack (#6497, #10654).

    Canonical model for both health endpoints. Wire format is the model itself —
    no DataResponse envelope. ``components`` is Dict[str, Any] so it handles
    both the fixed {chat_history_manager, llm_service} shape from /chat/health
    and the heterogeneous per-component map from /health-ai-stack.
    ``error`` is only populated on the /health-ai-stack error path.
    """

    status: str
    timestamp: str
    components: Dict[str, Any]
    error: str | None = None


class ChatStatsData(BaseModel):
    """data payload for GET /chat/stats (#6490).

    Wraps the dict returned by ChatHistoryManager.get_statistics() —
    session_count, message_count, and a recent-sessions sample.
    """

    stats: Dict[str, Any] | None = None


class ChatSaveData(BaseModel):
    """data payload for POST /chats/{chat_id}/save.

    ``save_session`` returns ``None`` so the wrapped data is ``null`` in
    practice; declared as Any | None for forward compatibility.
    """

    result: Any | None = None


class ChatDeleteData(BaseModel):
    """data payload for DELETE /chats/{chat_id}."""

    session_id: str
    deleted: Any


class ChatData(BaseModel):
    """data payload for POST /ai-stack.

    Mirrors ChatMessageData with an additional ``knowledge_sources``
    field for KB-augmented AI Stack chats.
    """

    content: str
    role: str
    session_id: str
    message_id: str | None = None
    timestamp: str | None = None
    metadata: Dict[str, Any] | None = None
    knowledge_sources: List[Dict[str, Any]] | None = None


class ChatCapabilitiesData(BaseModel):
    """data payload for GET /capabilities.

    Some fields are absent on the fallback path when AI Stack is
    unavailable (only ``ai_stack_chat_available``, ``ai_stack_integration``,
    ``knowledge_base_integration``, ``error`` are populated then).
    """

    ai_stack_chat_available: bool
    ai_stack_integration: bool
    knowledge_base_integration: bool
    source_citations: bool | None = None
    streaming_responses: bool | None = None
    multi_agent_coordination: bool | None = None
    available_agents: List[Any] | None = None
    response_styles: List[str] | None = None
    supported_languages: List[str] | None = None
    max_message_length: int | None = None
    context_window: int | None = None
    error: str | None = None


class TranslateData(BaseModel):
    """Response shape for POST /translate (#6497).

    Wire format is the model itself — no DataResponse envelope. Shape
    comes from TranslationAgent.process_query.
    """

    status: str
    response: str | None = None
    response_text: str | None = None
    agent_type: str | None = None
    model_used: str | None = None
    token_usage: Dict[str, Any] | None = None


class DetectLanguageData(BaseModel):
    """Response shape for POST /detect-language (#6497).

    Wire format is the model itself — no DataResponse envelope. Same
    fields as TranslateData (both call TranslationAgent.process_query);
    the parsed language/language_name/confidence JSON sits inside
    response/response_text as a string.
    """

    status: str
    response: str | None = None
    response_text: str | None = None
    agent_type: str | None = None
    model_used: str | None = None
    token_usage: Dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# chat_sessions.py request schemas (#6042)
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    """Session creation model"""

    # #6746: accept client-supplied session_id so frontend and backend stay
    # aligned on a single UUID. Backend validates and uses it as-is; if absent
    # or invalid, backend mints a new one. Eliminates the two-phase create
    # that produced divergent IDs and "blank session" sidebar entries (#6745).
    id: str | None = Field(
        None,
        max_length=64,
        description="Optional client-supplied session UUID. Validated server-side; "
        "backend mints a new ID when absent or malformed.",
    )
    title: str | None = Field(None, max_length=200, description="Session title")
    team_id: str | None = Field(None, description="Team ID for team-scoped sessions (#684)")
    metadata: Metadata | None = Field(default_factory=dict, description="Session metadata")


class SessionUpdate(BaseModel):
    """Session update model"""

    title: str | None = Field(None, max_length=200, description="New session title")
    metadata: Metadata | None = Field(None, description="Updated metadata")


class ActivityCreate(BaseModel):
    """Single activity creation model"""

    activity_id: str = Field(..., description="Frontend-generated activity ID")
    type: str = Field(..., description="Activity type: terminal, file, browser, desktop")
    user_id: str = Field(..., description="User who performed the activity")
    content: str = Field(..., max_length=10000, description="Activity content/description")
    secrets_used: list[str] = Field(default_factory=list, description="Secret IDs used")
    metadata: Metadata | None = Field(default_factory=dict, description="Activity metadata")
    timestamp: str = Field(..., description="ISO format timestamp from frontend")


class ActivityBatchCreate(BaseModel):
    """Batch activity creation model"""

    activities: list[ActivityCreate] = Field(..., description="List of activities to create")


class SessionShareRequest(BaseModel):
    """Request to share a session with users"""

    share_with: list[str] = Field(..., min_length=1, description="User IDs to share with")
    include_knowledge: bool = Field(False, description="Include KB facts from this session")
    knowledge_facts: list[str] | None = Field(None, description="Specific fact IDs to share (all if omitted)")


# ---------------------------------------------------------------------------
# Shared link schemas (GH#8996)
# ---------------------------------------------------------------------------


class SharedLinkCreateRequest(BaseModel):
    """Request to create a public shared link for a chat session."""

    password: str | None = Field(None, min_length=1, max_length=128, description="Optional access password")
    expires_in_seconds: int | None = Field(None, ge=60, description="Link TTL in seconds; omit for no expiry")


class SharedLinkData(BaseModel):
    """Response payload after creating a shared link."""

    token: str
    session_id: str
    has_password: bool
    expires_at: datetime | None
    created_at: datetime


class SharedLinkAdminItem(BaseModel):
    """Admin view of a single active shared link, including its owner (GH#8996)."""

    id: str
    token: str
    session_id: str
    owner: str
    has_password: bool
    expires_at: datetime | None
    created_at: datetime


class SharedLinkAccessRequest(BaseModel):
    """Request body for accessing a password-protected shared link."""

    password: str | None = Field(None, description="Password for protected links")


class SharedMessageItem(BaseModel):
    """A single message in a shared conversation view."""

    role: str
    content: str
    created_at: datetime | None = None


class SharedLinkSessionData(BaseModel):
    """Public read-only view of a shared conversation."""

    session_id: str
    title: str | None = None
    messages: list[SharedMessageItem]
    has_password: bool


class ChatResetRequest(BaseModel):
    """Request model for chat reset"""

    session_id: str | None = Field(None, description="Session ID to reset (optional)")
    clear_context: bool = Field(True, description="Clear conversation context")
    keep_system_prompt: bool = Field(True, description="Keep system prompt after reset")


class ChatMessage(BaseModel):
    """Chat message model for requests — canonical for both /chat and /enhanced (#10654).

    Fields from the former enhanced variant (use_ai_stack, use_knowledge_base,
    response_style, include_sources) carry defaults so a plain /chat request
    that omits them validates without change. ``reasoning_effort`` is used by
    /chat only and is also optional, so /enhanced requests that omit it still
    validate.
    """

    content: str = Field(..., min_length=1, max_length=50000, description="Message content")
    role: str = Field(
        default=CategoryDefaults.ROLE_USER,
        pattern="^(user|assistant|system)$",
        description="Message role",
    )
    session_id: str = Field(..., description="Chat session ID")
    message_type: str | None = Field("text", description="Message type")
    metadata: Metadata | None = Field(default_factory=dict, description="Additional metadata")
    language: str | None = Field(
        None,
        description="Preferred response language code (e.g. 'en', 'es', 'de'). "
        "Overrides personality language when set.",
    )
    # AI Stack fields (used by /enhanced endpoints; defaulted so /chat requests omit safely)
    use_ai_stack: bool = Field(True, description="Whether to use AI Stack for enhanced responses")
    use_knowledge_base: bool = Field(True, description="Whether to include knowledge base context")
    response_style: str = Field("conversational", description="Response style preference")
    include_sources: bool = Field(True, description="Whether to include source citations")
    # Thinking / reasoning fields (shared by both /chat and /enhanced)
    thinking_mode_enabled: bool | None = Field(
        None,
        description="Enable extended thinking mode for reasoning models (Claude 3.7+, DeepSeek R1). "
        "When enabled, the model performs chain-of-thought reasoning before responding.",
    )
    thinking_budget_tokens: int | None = Field(
        None,
        ge=1000,
        le=128000,
        description="Thinking budget in tokens (e.g., 1000, 5000, 10000, 63000). "
        "Only used when thinking_mode_enabled=True. Limits the amount of reasoning tokens.",
    )
    reasoning_effort: str | None = Field(
        None,
        pattern="^(low|medium|high|auto)$",
        description="Per-conversation reasoning effort override (low, medium, high, auto). "
        "Overrides the user's account-level default. Omit to use the user default. "
        "When 'auto' or absent the provider's own defaults are used (#9017).",
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


class ChatPreferences(BaseModel):
    """Chat preferences for customizing AI behavior."""

    response_length: str = Field("medium", description="Preferred response length (short, medium, long)")
    technical_level: str = Field("adaptive", description="Technical complexity level")
    include_reasoning: bool = Field(False, description="Include reasoning steps in responses")
    fact_checking: bool = Field(True, description="Enable fact checking against knowledge base")


class ThinkingPreferences(BaseModel):
    """Thinking mode preferences per conversation (#8993)."""

    enabled: bool = Field(False, description="Enable extended thinking mode by default")
    budget_tokens: int = Field(
        10000,
        ge=1000,
        le=128000,
        description="Default thinking budget in tokens (1k-128k)",
    )


class ThinkingPreferencesData(BaseModel):
    """Data payload for GET/PUT /chat/sessions/{session_id}/thinking-preferences."""

    session_id: str
    enabled: bool
    budget_tokens: int


class TranslateRequest(BaseModel):
    """Request model for direct translation."""

    text: str = Field(..., min_length=1, max_length=50000, description="Text to translate")
    target_language: str = Field(..., min_length=1, max_length=50, description="Target language name")
    source_language: str | None = Field(None, description="Source language (auto-detect if omitted)")


class DetectLanguageRequest(BaseModel):
    """Request model for language detection."""

    text: str = Field(..., min_length=1, max_length=50000, description="Text to detect language of")


# ---------------------------------------------------------------------------
# chat_compare.py schemas
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    """Request body for /api/chat/compare multi-model comparison."""

    prompt: str = Field(..., min_length=1, max_length=50000)
    models: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of 'provider/model' strings, e.g. ['ollama/llama3', 'openai/gpt-4o']",
    )
    context: str | None = Field(None, max_length=50000)


# ---------------------------------------------------------------------------
# conversation_files.py response schemas (#6509c)
# ---------------------------------------------------------------------------


class ConvFileInfoData(BaseModel):
    """data payload for create/copy/agent-generate conversation file endpoints."""

    model_config = {"extra": "allow"}

    success: bool


class ConvFileOpData(BaseModel):
    """data payload for rename/get-content/update-content conversation file endpoints."""

    model_config = {"extra": "allow"}

    success: bool


class ConvFileSearchData(BaseModel):
    """data payload for GET /sessions/{session_id}/files/search."""

    success: bool
    files: List[Any]
    total: int


class SessionMcpToolsData(BaseModel):
    """data payload for GET /sessions/{session_id}/mcp/tools."""

    tools: List[Dict[str, Any]]
    session_id: str


class SessionMcpCallData(BaseModel):
    """data payload for POST /sessions/{session_id}/mcp/call."""

    model_config = {"extra": "allow"}

    success: bool


# ── Chat Folder schemas (GH#8987) ────────────────────────────────────────────


class FolderCreate(BaseModel):
    """Request body for POST /chat/folders."""

    name: str = Field(..., min_length=1, max_length=100, description="Folder display name")
    parent_id: str | None = Field(None, description="Parent folder ID for nesting (max 3 levels)")


class FolderUpdate(BaseModel):
    """Request body for PUT /chat/folders/{folder_id}."""

    name: str | None = Field(None, min_length=1, max_length=100, description="New folder name")
    parent_id: str | None = Field(None, description="New parent folder ID (None = root)")
    pinned: bool | None = Field(None, description="Pin folder to top of list")
    archived: bool | None = Field(None, description="Archive folder (hidden from main list, still searchable)")


class FolderData(BaseModel):
    """Single folder object returned by the API."""

    id: str
    name: str
    parent_id: str | None = None
    owner: str
    pinned: bool = False
    archived: bool = False
    created_at: str
    session_ids: List[str] = Field(default_factory=list)
    session_count: int = 0


class FolderListData(BaseModel):
    """data payload for GET /chat/folders."""

    folders: List[FolderData]
    count: int


class SessionFolderAssign(BaseModel):
    """Request body for PUT /chat/sessions/{session_id}/folder."""

    folder_id: str | None = Field(None, description="Folder ID to assign; None removes from folder")


# ── Context Overflow Protection schemas (GH#9043) ────────────────────────────


class ConversationSummarizeRequest(BaseModel):
    """Request body for POST /chat/summarize."""

    session_id: str = Field(..., description="Chat session ID")
    message_ids: List[str] = Field(..., min_length=1, description="Message IDs to summarize")
    target_length: int | None = Field(
        500, ge=100, le=2000, description="Target summary length in tokens (default: 500)"
    )


class ConversationSummarizeData(BaseModel):
    """data payload for POST /chat/summarize."""

    summary: str = Field(..., description="Generated summary of the conversation segment")
    original_message_count: int = Field(..., description="Number of messages summarized")
    summary_token_count: int | None = Field(None, description="Token count of the summary")
    timestamp: str = Field(..., description="ISO timestamp when summary was generated")
