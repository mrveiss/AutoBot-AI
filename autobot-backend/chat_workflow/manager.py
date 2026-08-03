# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat Workflow Manager - Main orchestration class.

Composes all functionality through mixins:
- ConversationHandlerMixin: Conversation history management
- ToolHandlerMixin: Tool and command handling
- LLMHandlerMixin: LLM interaction
- SessionHandlerMixin: Session management
"""

import asyncio
import json
import os
import re
import uuid
from contextvars import ContextVar
from typing import Any, Dict, FrozenSet, List

from async_chat_workflow import WorkflowMessage
from autobot_shared.env_utils import env_int
from autobot_shared.error_boundaries import error_boundary, get_error_boundary_manager
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client as get_redis_manager
from chat_workflow.tool_call_grammar import (
    TOOL_CALL_BARE_CLOSE_RE,
    TOOL_CALL_CLOSE_RE,
    TOOL_CALL_COMPLETE_RE,
    TOOL_CALL_OPEN_RE,
    TOOL_CALL_OPENING_RE,
    strip_unparsed_tool_tags,
)
from constants.api_constants import PATH_OLLAMA_GENERATE
from constants.model_constants import ModelConfig
from constants.ttl_constants import TIMEOUT_HTTP_DEFAULT, TTL_24_HOURS
from llm_shared.providers.reasoning_effort import map_effort_to_provider_params
from services.tool_output_filter import get_tool_output_filter
from slash_command_handler import get_slash_command_handler

from .conversation import ConversationHandlerMixin
from .llm_handler import LLMHandlerMixin, _emit_after_continuation, _emit_before_continuation
from .models import (
    LLMIterationContext,
    StreamingMessage,
    WorkflowSession,
    build_governed_identity,
    filter_internal_prompts,
)
from .session_handler import SessionHandlerMixin
from .tool_handler import ToolHandlerMixin

logger = get_logger(__name__)

# #11216 (MVA-1993): lightweight-mode cost indicator for the stream-metadata badge.
# Held in a task-local ContextVar rather than shared instance state, so two
# concurrent drivers of _execute_llm_continuation_loop (e.g. a real lightweight
# chat and the internal delegation subagent) cannot clobber each other's flag.
# Token-based set/reset also restores the caller's value for nested/inline drives.
_current_lightweight_mode: ContextVar[bool] = ContextVar("current_lightweight_mode", default=False)

# Issue #380: Module-level frozenset for terminal message types
_TERMINAL_MESSAGE_TYPES: FrozenSet[str] = frozenset({"terminal_command", "terminal_output", "error"})

# Issue #380: Module-level frozenset for block content types
_BLOCK_CONTENT_TYPES: FrozenSet[str] = frozenset({"thought", "planning"})

# Issue #11693: the tool-call grammar (normalization, completion detector,
# truncated-close tolerance for #11545/#11552) is now the single canonical
# source of truth in tool_call_grammar.py, shared with
# chat_workflow/tool_handler.py. Module-level aliases kept for
# backwards-compatible imports (tests import these names directly).
_TOOL_CALL_OPEN_RE = TOOL_CALL_OPEN_RE
_TOOL_CALL_CLOSE_RE = TOOL_CALL_CLOSE_RE
_TOOL_CALL_COMPLETE_RE = TOOL_CALL_COMPLETE_RE
_TOOL_CALL_BARE_CLOSE_RE = TOOL_CALL_BARE_CLOSE_RE
_TOOL_CALL_OPENING_RE = TOOL_CALL_OPENING_RE


# Issue #716/#11867: internal-prompt-echo patterns are consolidated into the
# canonical `filter_internal_prompts` in chat_workflow.models (imported above).


def _kb_sources_from_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map raw knowledge-base citation dicts to the persisted sources shape.

    Issue #13296: extracted from ``_persist_workflow_messages`` — was
    duplicated inline for the per-``WorkflowMessage`` citation list (already
    tagged ``type='knowledge_base'`` by ``_build_source_list``) and, per
    #13292, for the completed streamed reply's citations (the raw
    ``rag_citations`` list, which never carries the always-appended
    ``llm_training`` placeholder in the first place).
    """
    return [
        {
            "title": c.get("title") or c.get("source", ""),
            "path": c.get("source", ""),
            "score": c.get("score", 0.0),
            "chunk_id": c.get("id", ""),
        }
        for c in citations
    ]


async def _resolve_reasoning_effort(context: Dict[str, Any]) -> str:
    """Resolve reasoning effort with priority: per-request > user-default > 'auto'.

    Resolution order (#9017):
      1. context["reasoning_effort"] — per-conversation value from the request
      2. Redis user:{id}:preferences:reasoning_effort — account-level default
      3. 'auto' — no extra params, provider decides

    Invalid or missing values are returned as 'auto' (inert).
    """
    effort: str | None = context.get("reasoning_effort")
    if effort:
        return effort

    user_id: str | None = context.get("user_id")
    if user_id:
        try:
            from api.users import _get_user_preferences_from_redis

            prefs = await _get_user_preferences_from_redis(user_id)
            return prefs.reasoning_effort
        except Exception as exc:
            logger.warning("[#9017] Failed to load user reasoning_effort pref: %s", exc)

    return "auto"


# Issue #11538: vision-in-the-loop. OpenManus threads the current screenshot
# into the model's context on every step while the browser is active (N=3
# messages of look-back); mirrored here as a bounded window over the most
# recent tool execution_results so the model *sees* the effect of its last
# browser/VNC action instead of driving blind.
VISION_TOOL_LOOKBACK_MESSAGES = env_int("CHAT_VISION_TOOL_LOOKBACK_MESSAGES", default=3)

# Fixed per-image token cost used to gate attachment against the context
# budget (OpenAI's high-detail image estimate is ~765-1105 tokens; picked a
# representative default, env-overridable — never hardcode a tunable).
VISION_IMAGE_TOKEN_ESTIMATE = env_int("CHAT_VISION_IMAGE_TOKEN_ESTIMATE", default=1100)

# Case-insensitive substrings of a model name that indicate vision support.
# Ollama exposes no per-tag capability registry (unlike the fixed AIProvider
# registry in modern_ai_integration.py), so this is the pragmatic gate.
_DEFAULT_VISION_MODEL_PATTERNS = (
    "llava,vision,gpt-4o,gpt-4-vision,claude-3,claude-4,gemini,qwen-vl,qwen2-vl,qwen2.5-vl,pixtral,bakllava"
)
VISION_MODEL_NAME_PATTERNS = tuple(
    p.strip().lower()
    for p in os.getenv("CHAT_VISION_MODEL_PATTERNS", _DEFAULT_VISION_MODEL_PATTERNS).split(",")
    if p.strip()
)


def _model_supports_vision(model_name: str) -> bool:
    """Heuristic vision-capability gate for the chat continuation loop (#11538).

    Ollama exposes no per-tag capability registry, so this matches known
    vision-model name substrings (env-overridable via CHAT_VISION_MODEL_PATTERNS).
    """
    name = (model_name or "").lower()
    return any(pattern in name for pattern in VISION_MODEL_NAME_PATTERNS)


def _extract_latest_tool_screenshot(execution_history: List[Dict[str, Any]]) -> str | None:
    """Return the single most recent base64 screenshot from recent tool results (#11538).

    Looks back over the last VISION_TOOL_LOOKBACK_MESSAGES execution results
    (OpenManus uses N=3) and returns only the latest ``base64_image`` — older
    screenshots are dropped so context never accumulates more than one image.
    """
    window = execution_history[-VISION_TOOL_LOOKBACK_MESSAGES:] if VISION_TOOL_LOOKBACK_MESSAGES > 0 else []
    for result in reversed(window):
        image = result.get("base64_image")
        if image:
            return image
    return None


def _prune_stale_screenshots(execution_history: List[Dict[str, Any]]) -> None:
    """Drop ``base64_image`` from entries outside the vision lookback window (#11538).

    _record_browser_success stores the raw screenshot on every screenshot
    tool's execution_results entry, but only the latest one within
    VISION_TOOL_LOOKBACK_MESSAGES is ever read (_extract_latest_tool_screenshot).
    Without pruning, every multi-hundred-KB blob from the whole task would live
    in execution_history (and therefore conversation state) for the task's
    entire lifetime. Mutates *execution_history* in place.
    """
    if VISION_TOOL_LOOKBACK_MESSAGES <= 0:
        cutoff = len(execution_history)
    else:
        cutoff = max(0, len(execution_history) - VISION_TOOL_LOOKBACK_MESSAGES)
    for entry in execution_history[:cutoff]:
        entry.pop("base64_image", None)


def _strip_data_url_prefix(image_b64: str) -> str:
    """Strip a ``data:image/...;base64,`` prefix, if present (#11538).

    Screenshots already arrive as raw base64 from the browser worker, but this
    is defensive: Ollama's /api/generate ``images`` field wants raw base64
    only — a data-URL-prefixed string would be treated as invalid image bytes.
    """
    if "," in image_b64 and image_b64.strip().lower().startswith("data:"):
        return image_b64.split(",", 1)[1]
    return image_b64


def _resolve_vision_payload_shape(ollama_endpoint: str) -> str:
    """Return which image-attachment shape the target endpoint actually consumes (#11538).

    manager.py's continuation loop always POSTs to an Ollama-shaped endpoint —
    llm_handler._get_ollama_endpoint_for_model() (and every other endpoint
    resolver in llm_handler.py) unconditionally suffixes PATH_OLLAMA_GENERATE,
    and the stream is parsed as Ollama-native (_parse_stream_chunk reads
    chunk_data["response"]). Ollama's /api/generate ignores an OpenAI-style
    "messages" field entirely and instead expects a top-level "images" list of
    raw base64 strings — so that's the shape used whenever the endpoint is the
    Ollama generate path. If/when an OpenAI-compatible /chat/completions path
    is wired into this loop, route it to "openai_chat" here instead of
    guessing at the payload builder.
    """
    if ollama_endpoint.endswith(PATH_OLLAMA_GENERATE):
        return "ollama_generate"
    return "openai_chat"


class ChatWorkflowManager(
    ConversationHandlerMixin,
    ToolHandlerMixin,
    LLMHandlerMixin,
    SessionHandlerMixin,
):
    """
    Centralized manager for chat workflows across the application.

    Manages workflow sessions, provides unified interface, and handles
    lifecycle management for chat workflows.
    """

    def __init__(self):
        """Initialize the chat workflow manager."""
        self.sessions: Dict[str, WorkflowSession] = {}
        self.default_workflow: Any | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self.redis_manager = None  # Async Redis manager
        self.redis_client = None  # Main database connection
        self.conversation_history_ttl = TTL_24_HOURS
        self.transcript_dir = "data/conversation_transcripts"  # Long-term file storage

        # Error boundary manager for enhanced error tracking
        self.error_manager = get_error_boundary_manager()

        # Terminal tool integration
        self.terminal_tool = None
        self._init_terminal_tool()

        # Knowledge service for RAG integration (Issue #249)
        self.knowledge_service = None
        self._use_knowledge = True  # Can be toggled per session/request

        logger.info("ChatWorkflowManager initialized")

    async def _init_redis_client(self) -> None:
        """Initialize Redis client for conversation history."""
        try:
            self.redis_client = await get_redis_manager(async_client=True, database="main")
            logger.info("✅ Redis client initialized for conversation history")
        except Exception as redis_error:
            logger.warning(
                "⚠️ Redis initialization failed: %s - continuing without persistence",
                redis_error,
            )
            self.redis_client = None

    async def _init_knowledge_service(self) -> None:
        """Initialize knowledge service for RAG (Issue #249)."""
        try:
            from knowledge_factory import get_knowledge_base_async
            from services.chat_knowledge_service import ChatKnowledgeService
            from services.rag_service import RAGService

            kb = await get_knowledge_base_async()
            if kb:
                rag_service = RAGService(kb)
                await rag_service.initialize()
                self.knowledge_service = ChatKnowledgeService(rag_service)
                logger.info("✅ Knowledge service initialized for RAG")
            else:
                logger.warning("⚠️ Knowledge base not available - RAG disabled")
        except Exception as kb_error:
            logger.warning(
                "⚠️ Knowledge service initialization failed: %s - continuing without RAG",
                kb_error,
            )
            self.knowledge_service = None

    async def set_knowledge_base(self, kb) -> None:
        """Wire an already-initialized KnowledgeBase into the knowledge service.

        Issue #2309: Called by lifespan Phase 2 after the knowledge base is ready
        so that RAG is available even when the KB was not ready during Phase 1.
        """
        if kb is None:
            logger.warning("set_knowledge_base called with None -- RAG stays disabled")
            return
        try:
            from services.chat_knowledge_service import ChatKnowledgeService
            from services.rag_service import RAGService

            rag_service = RAGService(kb)
            await rag_service.initialize()
            self.knowledge_service = ChatKnowledgeService(rag_service)
            logger.info("Knowledge service wired from app-level knowledge base (#2309)")
        except Exception as exc:
            logger.warning("Failed to wire knowledge service from app KB: %s", exc)

    @error_boundary(component="chat_workflow_manager", function="initialize")
    async def initialize(self) -> bool:
        """Initialize the workflow manager with default workflow and async Redis."""
        try:
            async with self._lock:
                if self._initialized:
                    return True

                await self._init_redis_client()

                from async_chat_workflow import AsyncChatWorkflow

                self.default_workflow = AsyncChatWorkflow()

                await self._init_knowledge_service()

                self._initialized = True
                logger.info("✅ ChatWorkflowManager initialized successfully")
                return True

        except Exception as e:
            logger.error("❌ Failed to initialize ChatWorkflowManager: %s", e)
            return False

    # Issue #352: Maximum iterations for multi-step task continuation
    MAX_CONTINUATION_ITERATIONS = 5

    # Issue #351 Fix: Tag patterns for thought/planning detection
    THOUGHT_TAG_PATTERN = re.compile(r"\[THOUGHT\]", re.IGNORECASE)
    THOUGHT_END_PATTERN = re.compile(r"\[/THOUGHT\]", re.IGNORECASE)
    PLANNING_TAG_PATTERN = re.compile(r"\[PLANNING\]", re.IGNORECASE)
    PLANNING_END_PATTERN = re.compile(r"\[/PLANNING\]", re.IGNORECASE)

    def _normalize_tool_call_text(self, text: str) -> str:
        """Normalize TOOL_CALL spacing in LLM response text (Issue #332)."""
        # Issue #380: Use pre-compiled patterns
        text = _TOOL_CALL_OPEN_RE.sub("<TOOL_CALL", text)
        text = _TOOL_CALL_CLOSE_RE.sub("</TOOL_CALL>", text)
        return text

    def _filter_internal_prompts(self, text: str) -> str:
        """Filter out internal continuation prompts that LLM echoes back (Issue #716).

        Delegates to the canonical module-level
        :func:`chat_workflow.models.filter_internal_prompts` (Issue #11867
        consolidation) so the patterns and behaviour live in exactly one place.

        Args:
            text: LLM response text that may contain echoed internal prompts

        Returns:
            Text with internal prompts removed
        """
        return filter_internal_prompts(text)

    def _find_last_tag_positions(self, content: str) -> Dict[str, int]:
        """Find last occurrence positions of thought/planning tags."""
        positions = {
            "thought_start": -1,
            "thought_end": -1,
            "planning_start": -1,
            "planning_end": -1,
        }

        for match in self.THOUGHT_TAG_PATTERN.finditer(content):
            positions["thought_start"] = match.start()
        for match in self.THOUGHT_END_PATTERN.finditer(content):
            positions["thought_end"] = match.start()
        for match in self.PLANNING_TAG_PATTERN.finditer(content):
            positions["planning_start"] = match.start()
        for match in self.PLANNING_END_PATTERN.finditer(content):
            positions["planning_end"] = match.start()

        return positions

    def _detect_content_type(self, content: str, current_type: str = "response") -> str:
        """Detect message type from content tags (Issue #351 Fix)."""
        positions = self._find_last_tag_positions(content)
        thought_start = positions["thought_start"]
        thought_end = positions["thought_end"]
        planning_start = positions["planning_start"]
        planning_end = positions["planning_end"]

        # Check thought block status
        if thought_start >= 0:
            if thought_end > thought_start:
                # Block is closed - check for planning after
                if planning_start > thought_end and planning_end < planning_start:
                    return "planning"
                return "response"
            else:
                return "thought"

        # Check planning block status
        if planning_start >= 0:
            if planning_end > planning_start:
                return "response"
            else:
                return "planning"

        # No tags - maintain current type if in block
        if current_type in _BLOCK_CONTENT_TYPES:
            return current_type

        return "response"

    def _build_chunk_message(
        self,
        chunk_text: str,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        accumulated_content: str = "",
        current_type: str = "response",
    ) -> WorkflowMessage:
        """
        Build a WorkflowMessage for a streaming chunk (Issue #332).

        Issue #351 Fix: Now detects thought/planning tags and emits proper types.

        Args:
            chunk_text: Current chunk text
            selected_model: Model name
            terminal_session_id: Terminal session ID
            used_knowledge: Whether knowledge base was used
            rag_citations: RAG citations if any
            accumulated_content: Full accumulated content for type detection
            current_type: Current detected message type

        Returns:
            WorkflowMessage with appropriate type
        """
        # Issue #351: Detect message type from accumulated content
        detected_type = self._detect_content_type(accumulated_content, current_type)

        # Issue #352: Debug logging for thought/planning detection
        if detected_type in _BLOCK_CONTENT_TYPES:
            logger.info(
                "[Issue #352] Detected message type: %s (accumulated len: %d)",
                detected_type,
                len(accumulated_content),
            )

        return WorkflowMessage(
            type=detected_type,
            content=chunk_text,
            metadata={
                "message_type": "llm_response_chunk",
                "model": selected_model,
                "streaming": True,
                "terminal_session_id": terminal_session_id,
                "used_knowledge": used_knowledge,
                "citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
            },
        )

    def _build_source_list(
        self,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        selected_model: str,
    ) -> List[Dict[str, Any]]:
        """Build citation list always containing >=1 entry. Issue #1186.

        When KB was used, KB citations come first.
        LLM training data entry is always appended last so users
        always see what the response is based on.
        """
        sources: List[Dict[str, Any]] = []
        if used_knowledge and not rag_citations:
            logger.warning("_build_source_list: used_knowledge=True but rag_citations is empty")
        if used_knowledge and rag_citations:
            for c in rag_citations:
                sources.append({**c, "type": "knowledge_base", "reliability": "high"})
        sources.append(
            {
                "type": "llm_training",
                "title": "AI Training Data",
                "model": selected_model,
                "reliability": "medium",
                "source": "LLM",
                "content": "Response generated using LLM training data.",
                "score": 0.5,
            }
        )
        return sources

    def _parse_stream_chunk(self, line: bytes) -> Dict[str, Any] | None:
        """Parse a single stream chunk line (Issue #315: depth reduction).

        Args:
            line: Raw bytes from response stream

        Returns:
            Parsed JSON dict or None if invalid/empty
        """
        line_str = line.decode("utf-8").strip()
        if not line_str:
            return None

        try:
            return json.loads(line_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse stream chunk: %s", e)
            return None

    def _handle_type_transition(
        self,
        new_type: str,
        current_message_type: str,
        current_message_id: str,
        selected_model: str,
        llm_response: str,
        chunk_text: str,
    ) -> tuple:
        """Handle message type transitions. Returns (complete_msg or None, new_id, new_segment, new_type).

        Issue #680: Fixed tag splitting - don't start new segment from partial tag content.
        When transitioning types (e.g., response → thought or thought → response),
        we need to find where the tag ends in the accumulated response and start
        the new segment from there, not from the current chunk which may just be
        a closing bracket like ']'.
        """
        import uuid

        if new_type != current_message_type and current_message_type != "response":
            # Transitioning from thought/planning back to response
            # Issue #680: Find content after closing tag [/THOUGHT] or [/PLANNING]
            logger.info(
                "[Issue #352] Message type transition: %s → %s",
                current_message_type,
                new_type,
            )
            # Find content after the closing tag
            new_segment_start = self._find_new_segment_start(llm_response, new_type, previous_type=current_message_type)
            complete_msg = WorkflowMessage(
                type="segment_complete",
                content="",
                metadata={
                    "completed_type": current_message_type,
                    "message_id": current_message_id,
                    "model": selected_model,
                },
            )
            return (complete_msg, str(uuid.uuid4()), new_segment_start, new_type)

        elif new_type != current_message_type:
            # Type changed from response to thought/planning
            # Issue #680: Find the tag position to properly split content
            new_segment_start = self._find_new_segment_start(llm_response, new_type, previous_type=current_message_type)
            return (None, str(uuid.uuid4()), new_segment_start, new_type)

        return (None, current_message_id, None, current_message_type)

    def _find_new_segment_start(self, llm_response: str, new_type: str, previous_type: str = "response") -> str:
        """Find content after the relevant tag for the new segment type.

        Issue #680: When type changes, extract only the content AFTER the complete
        tag, not including partial tag characters like ']'.

        For opening tags (thought/planning), find content after [TYPE].
        For closing tags (response after thought/planning), find content after [/TYPE].
        """
        # Opening tags for entering a block
        opening_tag_map = {
            "thought": r"\[THOUGHT\]",
            "planning": r"\[PLANNING\]",
        }

        # Closing tags for exiting a block
        closing_tag_map = {
            "thought": r"\[/THOUGHT\]",
            "planning": r"\[/PLANNING\]",
        }

        # Determine which tag to look for
        if new_type in opening_tag_map:
            # Entering a thought/planning block
            pattern = opening_tag_map[new_type]
        elif new_type == "response" and previous_type in closing_tag_map:
            # Exiting a thought/planning block back to response
            pattern = closing_tag_map[previous_type]
        else:
            return ""

        # Find the last occurrence of the complete tag
        match = None
        for m in re.finditer(pattern, llm_response, re.IGNORECASE):
            match = m

        if match:
            # Return content after the tag
            content_after_tag = llm_response[match.end() :]
            logger.debug(
                "[Issue #680] New segment for %s starts after tag: '%s...'",
                new_type,
                content_after_tag[:50] if content_after_tag else "(empty)",
            )
            return content_after_tag

        return ""

    def _build_stream_chunk_message(
        self,
        chunk_text: str,
        current_message_type: str,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        current_message_id: str,
    ) -> WorkflowMessage:
        """Build a WorkflowMessage for a streaming chunk.

        Issue #650: Added display_type to metadata for frontend filtering.
        The top-level 'type' field now carries the detected display type (thought/planning/response),
        while 'message_type' in metadata indicates streaming status.
        """
        return WorkflowMessage(
            type=current_message_type,  # Issue #650: This is the display type
            content=chunk_text,
            metadata={
                "message_type": "llm_response_chunk",  # Backwards compat
                "display_type": current_message_type,  # Issue #650: Explicit display type
                "model": selected_model,
                "streaming": True,
                "terminal_session_id": terminal_session_id,
                "used_knowledge": used_knowledge,
                "citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
                "message_id": current_message_id,
            },
        )

    def _log_stream_completion(self, llm_response: str) -> None:
        """Log completion of LLM response stream."""
        has_thought = "[THOUGHT]" in llm_response
        has_planning = "[PLANNING]" in llm_response
        if has_thought or has_planning:
            logger.info(
                "[Issue #352] LLM response contains: THOUGHT=%s, PLANNING=%s",
                has_thought,
                has_planning,
            )
        else:
            logger.debug(
                "[Issue #352] LLM response (no thought/planning tags): %s...",
                llm_response[:200],
            )

    def _init_streaming_message(
        self,
        message_type: str,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        lightweight_mode_used: bool = False,
    ) -> StreamingMessage:
        """
        Initialize a StreamingMessage with metadata.

        Issue #665: Extracted from _stream_llm_response to reduce function length.
        Issue MVA-1993: Includes lightweight_mode_used in metadata for cost indicator.
        """
        streaming_msg = StreamingMessage(type=message_type)
        metadata = {
            "model": selected_model,
            "terminal_session_id": terminal_session_id,
            "used_knowledge": used_knowledge,
            "citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
        }
        # MVA-1993 / #11216: lightweight indicator from the explicit parameter or the
        # task-local ContextVar (no longer shared instance state).
        lw_mode = lightweight_mode_used or _current_lightweight_mode.get()
        if lw_mode:
            metadata["lightweight_mode_used"] = True
        streaming_msg.merge_metadata(metadata)
        return streaming_msg

    def _process_chunk_and_detect_type(
        self,
        chunk_data: Dict[str, Any],
        llm_response: str,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """
        Process chunk data and detect content type.

        Issue #665: Extracted from _stream_llm_response to reduce function length.
        Issue #1313: Only run full type detection when chunk contains '[' or ']',
        which is the only way a tag boundary can occur. This avoids scanning
        the entire accumulated content on every chunk (O(n²) → amortized O(n)).

        Returns:
            Tuple of (chunk_text, new_llm_response, new_current_segment, new_type)
        """
        chunk_text = chunk_data.get("response", "")
        if not chunk_text:
            return (None, llm_response, current_segment, current_message_type)

        chunk_text = self._normalize_tool_call_text(chunk_text)
        new_llm_response = llm_response + chunk_text
        new_current_segment = current_segment + chunk_text

        # Issue #1313: Skip expensive full-content scan when chunk has no tag chars
        if "[" in chunk_text or "]" in chunk_text:
            new_type = self._detect_content_type(new_llm_response, current_message_type)
        else:
            new_type = current_message_type

        return (chunk_text, new_llm_response, new_current_segment, new_type)

    def _apply_type_transition(
        self,
        complete_msg: WorkflowMessage | None,
        new_segment: str | None,
        new_type: str,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        lightweight_mode_used: bool = False,
    ) -> tuple:
        """
        Apply type transition and create new StreamingMessage if needed.

        Issue #665: Extracted from _stream_llm_response to reduce function length.
        Issue MVA-1993: Includes lightweight_mode_used for cost indicator.

        Returns:
            Tuple of (new_streaming_msg, new_segment_value, new_type, just_transitioned, transition_content)
        """
        if complete_msg or new_segment is not None:
            # Issue #656: Create new StreamingMessage for new type
            streaming_msg = self._init_streaming_message(
                new_type,
                selected_model,
                terminal_session_id,
                used_knowledge,
                rag_citations,
                lightweight_mode_used=lightweight_mode_used,
            )
            return (streaming_msg, new_segment, new_type, True, new_segment)
        return (None, None, new_type, False, None)

    def _check_tool_call_completion(self, llm_response: str, tool_call_completed: bool) -> bool:
        """
        Check if tool call has completed in accumulated response.

        Issue #620: Extracted from _stream_llm_response to reduce function length.
        Issue #727: Detects </tool_call> to stop streaming hallucinations.

        Args:
            llm_response: Accumulated LLM response text
            tool_call_completed: Current completion state

        Returns:
            True if tool call is now complete, False otherwise. Issue #620.
        """
        if tool_call_completed:
            return tool_call_completed
        # A well-formed close, OR (#11552) a truncated bare `</tool` close but only
        # once a real opening tag is present — so legit prose mentioning `</tool>`
        # never truncates a general-chat response.
        completed = bool(_TOOL_CALL_COMPLETE_RE.search(llm_response)) or bool(
            _TOOL_CALL_OPENING_RE.search(llm_response) and _TOOL_CALL_BARE_CLOSE_RE.search(llm_response)
        )
        if completed:
            logger.info(
                "[Issue #727] Tool call completion detected - stopping frontend streaming "
                "to prevent hallucination display. Response length: %d",
                len(llm_response),
            )
            return True
        return tool_call_completed

    def _update_transition_state(
        self,
        new_msg,
        new_segment_val,
        new_type: str,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Update streaming state after type transition. Issue #620."""
        if new_msg:
            return (new_msg, new_segment_val, new_type)
        return (streaming_msg, current_segment, current_message_type)

    def _execute_type_transition_steps(
        self,
        new_type: str,
        current_message_type: str,
        streaming_msg,
        selected_model: str,
        llm_response: str,
        chunk_text: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ) -> tuple:
        """Execute the type transition processing steps. Issue #620."""
        complete_msg, _, new_segment, new_type = self._handle_type_transition(
            new_type,
            current_message_type,
            streaming_msg.id,
            selected_model,
            llm_response,
            chunk_text,
        )
        return self._apply_type_transition(
            complete_msg,
            new_segment,
            new_type,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
        ) + (complete_msg,)

    def _process_chunk_type_transition(
        self,
        chunk_text: str,
        new_type: str,
        current_message_type: str,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        llm_response: str,
        current_segment: str,
    ) -> tuple:
        """Process type transitions and update streaming message state. Issue #620."""
        result = self._execute_type_transition_steps(
            new_type,
            current_message_type,
            streaming_msg,
            selected_model,
            llm_response,
            chunk_text,
            terminal_session_id,
            used_knowledge,
            rag_citations,
        )
        (
            new_msg,
            new_segment_val,
            new_type,
            just_transitioned,
            transition_content,
            complete_msg,
        ) = result
        (
            streaming_msg,
            current_segment,
            current_message_type,
        ) = self._update_transition_state(
            new_msg,
            new_segment_val,
            new_type,
            streaming_msg,
            current_segment,
            current_message_type,
        )
        return (
            complete_msg,
            streaming_msg,
            current_segment,
            current_message_type,
            just_transitioned,
            transition_content,
        )

    def _stream_chunk_content(
        self,
        streaming_msg,
        chunk_text: str,
        just_transitioned: bool,
        transition_content: str | None,
        current_message_type: str,
    ) -> None:
        """Stream chunk content to the streaming message. Issue #620, #1140."""
        if just_transitioned:
            # Only stream transition_content (text after the tag); skip chunk_text
            # (which is just the closing ] of the tag) to prevent ] leaking into
            # the new message when transition_content is empty.
            if transition_content:
                streaming_msg.stream(transition_content)
        else:
            streaming_msg.stream(chunk_text)
        streaming_msg.set_metadata("display_type", current_message_type)
        streaming_msg.set_metadata("message_type", "llm_response_chunk")

    def _handle_tool_call_done(self, chunk_data: Dict[str, Any], llm_response: str):
        """Handle completion when tool call is done. Issue #620."""
        if chunk_data.get("done", False):
            self._log_stream_completion(llm_response)
            return (None, llm_response, True, False)
        return None

    def _process_chunk_with_transitions(
        self,
        chunk_text: str,
        new_type: str,
        current_message_type: str,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        llm_response: str,
        current_segment: str,
    ):
        """Process chunk and apply type transitions. Issue #620."""
        result = self._process_chunk_type_transition(
            chunk_text,
            new_type,
            current_message_type,
            streaming_msg,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
            llm_response,
            current_segment,
        )
        (
            complete_msg,
            streaming_msg,
            current_segment,
            current_message_type,
            just_transitioned,
            transition_content,
        ) = result
        self._stream_chunk_content(
            streaming_msg,
            chunk_text,
            just_transitioned,
            transition_content,
            current_message_type,
        )
        return complete_msg, streaming_msg, current_segment, current_message_type

    def _handle_tool_call_completion_check(
        self,
        chunk_data: Dict[str, Any],
        llm_response: str,
        tool_call_completed: bool,
    ) -> tuple:
        """Handle tool call completion detection during streaming.

        Issue #620.

        Returns:
            Tuple of (done_result, should_break, tool_call_completed)
        """
        tool_call_completed = self._check_tool_call_completion(llm_response, tool_call_completed)
        if tool_call_completed:
            done_result = self._handle_tool_call_done(chunk_data, llm_response)
            if done_result:
                return (done_result, True, tool_call_completed)
            return (None, False, tool_call_completed)
        return (None, False, tool_call_completed)

    def _yield_chunk_messages(
        self,
        chunk_text: str,
        new_type: str,
        current_message_type: str,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        llm_response: str,
        current_segment: str,
    ) -> tuple:
        """Process chunk and prepare messages for yielding.

        Issue #620.

        Returns:
            Tuple of (complete_msg, workflow_msg, streaming_msg, segment, msg_type)
        """
        (
            complete_msg,
            streaming_msg,
            current_segment,
            current_message_type,
        ) = self._process_chunk_with_transitions(
            chunk_text,
            new_type,
            current_message_type,
            streaming_msg,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
            llm_response,
            current_segment,
        )
        workflow_msg = streaming_msg.to_workflow_message()
        return (
            complete_msg,
            workflow_msg,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _initialize_stream_state(
        self,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        lightweight_mode_used: bool = False,
    ) -> tuple:
        """Initialize state for streaming LLM response.

        Issue #620.
        Issue MVA-1993: Includes lightweight_mode_used for cost indicator.
        """
        streaming_msg = self._init_streaming_message(
            "response",
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
            lightweight_mode_used=lightweight_mode_used,
        )
        return "", "", "response", False, streaming_msg

    def _build_stream_state_tuple(
        self,
        action: str,
        extra_data: Any,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Build state tuple for stream chunk iteration results.

        Issue #620.
        """
        return (
            action,
            extra_data,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _build_chunk_result_tuple(
        self,
        complete_msg,
        workflow_msg,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Build result tuple for chunk action with messages.

        Issue #620.
        """
        return (
            "chunk",
            complete_msg,
            workflow_msg,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_early_exit_conditions(
        self,
        should_break: bool,
        tool_call_completed: bool,
        done_result,
        llm_response: str,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ):
        """Check early exit conditions and return appropriate tuple if needed.

        Issue #620.
        """
        if should_break:
            return self._build_stream_state_tuple(
                "break",
                done_result,
                llm_response,
                tool_call_completed,
                streaming_msg,
                current_segment,
                current_message_type,
            )
        if tool_call_completed:
            return self._build_stream_state_tuple(
                "continue",
                None,
                llm_response,
                tool_call_completed,
                streaming_msg,
                current_segment,
                current_message_type,
            )
        return None

    def _process_chunk_with_messages(
        self,
        chunk_text: str,
        new_type: str,
        current_message_type: str,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        llm_response: str,
        current_segment: str,
        tool_call_completed: bool,
    ) -> tuple:
        """Process chunk and build result tuple with messages.

        Issue #620.
        """
        (
            complete_msg,
            workflow_msg,
            streaming_msg,
            current_segment,
            current_message_type,
        ) = self._yield_chunk_messages(
            chunk_text,
            new_type,
            current_message_type,
            streaming_msg,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
            llm_response,
            current_segment,
        )
        return self._build_chunk_result_tuple(
            complete_msg,
            workflow_msg,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_empty_chunk(
        self,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Build state tuple for empty chunk case. Issue #620."""
        return self._build_stream_state_tuple(
            "no_chunk",
            None,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _extract_chunk_processing_state(
        self,
        chunk_data: Dict[str, Any],
        llm_response: str,
        current_segment: str,
        current_message_type: str,
        tool_call_completed: bool,
    ) -> tuple:
        """Extract and process chunk state from chunk data.

        Combines chunk text extraction and tool call completion checking.
        Issue #620.
        """
        (
            chunk_text,
            llm_response,
            current_segment,
            new_type,
        ) = self._process_chunk_and_detect_type(chunk_data, llm_response, current_segment, current_message_type)
        (
            done_result,
            should_break,
            tool_call_completed,
        ) = self._handle_tool_call_completion_check(chunk_data, llm_response, tool_call_completed)
        return (
            chunk_text,
            llm_response,
            current_segment,
            new_type,
            done_result,
            should_break,
            tool_call_completed,
        )

    def _build_chunk_iteration_context(
        self,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build context dictionary for chunk iteration processing.

        Issue #620.
        """
        return {
            "streaming_msg": streaming_msg,
            "selected_model": selected_model,
            "terminal_session_id": terminal_session_id,
            "used_knowledge": used_knowledge,
            "rag_citations": rag_citations,
        }

    def _yield_chunk_result(
        self,
        chunk_text: str,
        new_type: str,
        current_message_type: str,
        ctx: Dict[str, Any],
        llm_response: str,
        current_segment: str,
        tool_call_completed: bool,
    ):
        """Build and return chunk processing result. Issue #620."""
        return self._process_chunk_with_messages(
            chunk_text,
            new_type,
            current_message_type,
            ctx["streaming_msg"],
            ctx["selected_model"],
            ctx["terminal_session_id"],
            ctx["used_knowledge"],
            ctx["rag_citations"],
            llm_response,
            current_segment,
            tool_call_completed,
        )

    def _check_chunk_exit_condition(
        self,
        chunk_text: str,
        should_break: bool,
        tool_call_completed: bool,
        done_result,
        llm_response: str,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ):
        """Check if chunk processing should exit early. Issue #620.

        Returns:
            Tuple of (should_exit, exit_result) where exit_result is the
            value to yield if should_exit is True.
        """
        early_exit = self._handle_early_exit_conditions(
            should_break,
            tool_call_completed,
            done_result,
            llm_response,
            streaming_msg,
            current_segment,
            current_message_type,
        )
        if early_exit:
            return (True, early_exit)
        if not chunk_text:
            return (
                True,
                self._handle_empty_chunk(
                    llm_response,
                    tool_call_completed,
                    streaming_msg,
                    current_segment,
                    current_message_type,
                ),
            )
        return (False, None)

    def _build_and_yield_chunk(
        self,
        chunk_text: str,
        new_type: str,
        current_message_type: str,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        llm_response: str,
        current_segment: str,
        tool_call_completed: bool,
    ):
        """Build context and yield chunk result. Issue #620."""
        ctx = self._build_chunk_iteration_context(
            streaming_msg,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
        )
        return self._yield_chunk_result(
            chunk_text,
            new_type,
            current_message_type,
            ctx,
            llm_response,
            current_segment,
            tool_call_completed,
        )

    async def _process_stream_chunk_iteration(
        self,
        chunk_data: Dict[str, Any],
        llm_response: str,
        current_segment: str,
        current_message_type: str,
        tool_call_completed: bool,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ):
        """Process a single chunk iteration in the stream. Issue #620."""
        state = self._extract_chunk_processing_state(
            chunk_data,
            llm_response,
            current_segment,
            current_message_type,
            tool_call_completed,
        )
        chunk_text, llm_response, current_segment, new_type = state[:4]
        done_result, should_break, tool_call_completed = state[4:]

        should_exit, exit_result = self._check_chunk_exit_condition(
            chunk_text,
            should_break,
            tool_call_completed,
            done_result,
            llm_response,
            streaming_msg,
            current_segment,
            current_message_type,
        )
        if should_exit:
            yield exit_result
            return

        yield self._build_and_yield_chunk(
            chunk_text,
            new_type,
            current_message_type,
            streaming_msg,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
            llm_response,
            current_segment,
            tool_call_completed,
        )

    def _unpack_stream_action_state(self, result: tuple) -> tuple:
        """Unpack state variables from stream action result.

        Issue #620.

        Args:
            result: Tuple from _process_stream_chunk_iteration

        Returns:
            Tuple of (llm_response, tool_call_completed, streaming_msg,
                     current_segment, current_message_type). Issue #620.
        """
        return (result[2], result[3], result[4], result[5], result[6])

    def _unpack_chunk_action_state(self, result: tuple) -> tuple:
        """Unpack state and messages from chunk action result.

        Issue #620.

        Args:
            result: Tuple from _process_stream_chunk_iteration with action="chunk"

        Returns:
            Tuple of (complete_msg, workflow_msg, llm_response, tool_call_completed,
                     streaming_msg, current_segment, current_message_type). Issue #620.
        """
        return (
            result[1],
            result[2],
            result[3],
            result[4],
            result[5],
            result[6],
            result[7],
        )

    def _build_action_result(
        self,
        should_return: bool,
        should_break: bool,
        yields: List,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Build standardized result tuple for stream action handling.

        Issue #620.
        """
        return (
            should_return,
            should_break,
            yields,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_break_action(
        self,
        result: tuple,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Handle break action from stream chunk iteration.

        Issue #620.
        """
        return self._build_action_result(
            True,
            False,
            [result[1]],
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_continue_or_no_chunk_action(
        self,
        action: str,
        result: tuple,
    ) -> tuple:
        """Handle continue or no_chunk action from stream chunk iteration.

        Issue #620.
        """
        (
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        ) = self._unpack_stream_action_state(result)
        should_break = action == "continue"
        return self._build_action_result(
            False,
            should_break,
            [],
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_chunk_action(self, result: tuple) -> tuple:
        """Handle chunk action from stream chunk iteration.

        Issue #620.
        """
        (
            complete_msg,
            workflow_msg,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        ) = self._unpack_chunk_action_state(result)
        yields = []
        if complete_msg:
            yields.append((complete_msg, llm_response, False, True))
        yields.append((workflow_msg, llm_response, False, False))
        return self._build_action_result(
            False,
            False,
            yields,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_stream_action(
        self,
        action: str,
        result: tuple,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Handle stream action and return updated state with yields.

        Issue #620.
        """
        if action == "break":
            return self._handle_break_action(
                result,
                llm_response,
                tool_call_completed,
                streaming_msg,
                current_segment,
                current_message_type,
            )

        if action in ("continue", "no_chunk"):
            return self._handle_continue_or_no_chunk_action(action, result)

        if action == "chunk":
            return self._handle_chunk_action(result)

        return self._build_action_result(
            False,
            False,
            [],
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _process_stream_result(
        self,
        result: tuple,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Process a single stream result and return updated state with yields.

        Issue #620.

        Args:
            result: Result tuple from _process_stream_chunk_iteration
            llm_response: Current accumulated LLM response
            tool_call_completed: Whether tool call has completed
            streaming_msg: Current streaming message object
            current_segment: Current response segment
            current_message_type: Current message type

        Returns:
            Tuple of (should_return, should_break, yields, llm_response,
                     tool_call_completed, streaming_msg, current_segment,
                     current_message_type). Issue #620.
        """
        return self._handle_stream_action(
            result[0],
            result,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    def _handle_chunk_result_yields(self, result: tuple, state: tuple) -> tuple:
        """Process chunk result and update state variables. Issue #620.

        Args:
            result: Result from _process_stream_chunk_iteration
            state: Current state tuple (llm_response, tool_call_completed,
                   streaming_msg, current_segment, current_message_type)

        Returns:
            Tuple of (should_return, should_break, yields, updated_state)
        """
        llm_response, tool_call_completed, streaming_msg = state[:3]
        current_segment, current_message_type = state[3:]
        (
            should_return,
            should_break,
            yields,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        ) = self._process_stream_result(
            result,
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )
        new_state = (
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )
        return should_return, should_break, yields, new_state

    def _build_chunk_iteration_params(
        self,
        chunk_data: Dict[str, Any],
        llm_response: str,
        current_segment: str,
        current_message_type: str,
        tool_call_completed: bool,
        streaming_msg,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ) -> tuple:
        """Build parameters tuple for chunk iteration processing. Issue #620."""
        return (
            chunk_data,
            llm_response,
            current_segment,
            current_message_type,
            tool_call_completed,
            streaming_msg,
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
        )

    async def _iterate_chunk_results(self, params: tuple, current_state: tuple):
        """Iterate chunk results and yield processed items. Issue #620."""
        (
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        ) = current_state
        async for result in self._process_stream_chunk_iteration(*params):
            state = (
                llm_response,
                tool_call_completed,
                streaming_msg,
                current_segment,
                current_message_type,
            )
            (
                should_return,
                should_break,
                yields,
                updated,
            ) = self._handle_chunk_result_yields(result, state)
            llm_response, tool_call_completed, streaming_msg = updated[:3]
            current_segment, current_message_type = updated[3:]
            new_state = (
                llm_response,
                tool_call_completed,
                streaming_msg,
                current_segment,
                current_message_type,
            )
            yield (should_return, should_break, yields, new_state)

    def _build_stream_current_state(
        self,
        llm_response: str,
        tool_call_completed: bool,
        streaming_msg,
        current_segment: str,
        current_message_type: str,
    ) -> tuple:
        """Build current state tuple for stream iteration. Issue #620."""
        return (
            llm_response,
            tool_call_completed,
            streaming_msg,
            current_segment,
            current_message_type,
        )

    async def _stream_llm_response(
        self,
        response,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        lightweight_mode_used: bool = False,
    ):
        """Stream LLM response chunks. Issue #620. Issue MVA-1993: Includes lightweight_mode_used."""
        state = self._initialize_stream_state(
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
            lightweight_mode_used=lightweight_mode_used,
        )
        llm_response, current_segment, current_message_type = state[:3]
        tool_call_completed, streaming_msg = state[3:]

        async for line in response.content:
            chunk_data = self._parse_stream_chunk(line)
            if not chunk_data:
                continue
            params = self._build_chunk_iteration_params(
                chunk_data,
                llm_response,
                current_segment,
                current_message_type,
                tool_call_completed,
                streaming_msg,
                selected_model,
                terminal_session_id,
                used_knowledge,
                rag_citations,
            )
            current_state = self._build_stream_current_state(
                llm_response,
                tool_call_completed,
                streaming_msg,
                current_segment,
                current_message_type,
            )
            async for (
                should_return,
                should_break,
                yields,
                updated,
            ) in self._iterate_chunk_results(params, current_state):
                (
                    llm_response,
                    tool_call_completed,
                    streaming_msg,
                    current_segment,
                    current_message_type,
                ) = updated
                for item in yields:
                    yield item
                if should_return:
                    return
                if should_break:
                    break
            if chunk_data.get("done", False):
                self._log_stream_completion(llm_response)
                yield (None, llm_response, True, False)
                break

    def _format_execution_step(self, step_num: int, result: Dict[str, Any]) -> str:
        """Format a single execution step for the continuation prompt.

        Issue #650: Increased output limit from 500 to 2000 chars for better LLM context.
        Truncated output is clearly marked to help LLM understand when data is incomplete.
        """
        cmd = result.get("command", "unknown")
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        status = result.get("status", "unknown")

        output_text = stdout if stdout else "(no output)"
        if stderr:
            output_text += f"\nStderr: {stderr}"

        output_text = get_tool_output_filter().prepare_and_filter(cmd, output_text)

        return f"**Step {step_num}:** `{cmd}`\n- Status: {status}\n- Output:\n```\n{output_text}\n```"

    def _build_tools_reminder(self, consecutive_invalid_tool_calls: int) -> str:
        """Build an optional tool-name correction block for continuation prompts. Issue #2735.

        Returns a non-empty string only when the LLM has made 2+ consecutive invalid
        tool calls (Issue #2310), so the reminder is injected into the next prompt.
        """
        if consecutive_invalid_tool_calls < 2:
            return ""
        logger.warning(
            "[Issue #2310] Injecting available-tools reminder after %d consecutive invalid tool calls",
            consecutive_invalid_tool_calls,
        )
        _reminder = (
            f"\n**[SYSTEM] TOOL NAME CORRECTION REQUIRED:**\n"  # nosec B608 - prompt template, not SQL
            f"Your last {consecutive_invalid_tool_calls} tool call(s) used invalid tool names. "
            "You MUST use ONLY the following tool names:\n"
            "- execute_command: Run shell commands\n"
            "- web_search: Search the web for information\n"
            "- navigate: Browse to a URL\n"
            "- click: Click an element on a web page\n"
            "- fill: Fill a form field on a web page\n"
            "- select: Select an option on a web page\n"
            "- hover: Hover over an element\n"
            "- screenshot: Capture the current page\n"
            "- evaluate: Evaluate JavaScript on a web page\n"
            "- get_text: Get text from an element\n"
            "- get_attribute: Get an attribute from an element\n"
            "- wait_for_selector: Wait for an element to appear\n"
            "- browser_state: Get the current page's numbered interactive-element menu\n"
            "- click_index: Click an element by its numbered index\n"
            "- fill_index: Fill an element by its numbered index\n"
            "- select_index: Select an option on an element by its numbered index\n"
            "- hover_index: Hover over an element by its numbered index\n"
            "- delegate: Delegate a subtask to a subordinate agent\n"
            "- respond: Signal task completion with a final message\n"
            "Do NOT invent new tool names. Use ONLY the names listed above.\n\n"
        )  # nosec B608 - prompt template, not SQL; consecutive_invalid_tool_calls is an int counter
        return _reminder

    def _get_continuation_instructions(
        self,
        original_message: str,
        steps_completed: int,
        consecutive_invalid_tool_calls: int = 0,
    ) -> str:
        """Get the critical instructions for continuation prompts.

        Issue #651: Enhanced instructions to prevent premature task completion.
        Issue #2310: Injects available-tools reminder after 2+ consecutive invalid tool calls.
        """
        # Issue #2310: Build optional tools reminder block when LLM has repeatedly
        # hallucinated non-existent tool names.
        tools_reminder = self._build_tools_reminder(consecutive_invalid_tool_calls)

        return f"""**CRITICAL MULTI-STEP TASK INSTRUCTIONS - READ CAREFULLY:**
{tools_reminder}
You are in the middle of a multi-step task. {steps_completed} step(s) have been completed.

**ORIGINAL USER REQUEST (analyze this to determine if more steps needed):**
"{original_message}"

**DECISION PROCESS:**
1. Read the original request above carefully
2. Look at what has been executed so far
3. Determine: Are ALL parts of the request satisfied?

**IF MORE STEPS NEEDED** (task NOT fully complete):
- Generate the NEXT `<TOOL_CALL>` for the next command
- Do NOT provide a summary yet
- Do NOT repeat commands already executed
- Format: `<TOOL_CALL name="execute_command" params='{{"command":"YOUR_NEXT_CMD"}}'>description</TOOL_CALL>`

**IF TASK IS COMPLETE** (all parts of original request are done):
- Provide a summary of what was accomplished
- Do NOT generate any TOOL_CALL

**IMPORTANT**: Look at the original request. If it mentions multiple actions
(e.g., "create X, then do Y, then do Z"), ensure ALL actions are complete
before summarizing.

**YOUR RESPONSE:**"""

    def _build_continuation_prompt(
        self,
        original_message: str,
        execution_history: List[Dict[str, Any]],
        consecutive_invalid_tool_calls: int = 0,
    ) -> str:
        """Build continuation prompt with execution results for multi-step tasks.

        Issue #651: Enhanced prompt structure for better multi-step task handling.
        Issue #2310: Passes consecutive_invalid_tool_calls to inject tools reminder.
        Issue #3784: system_prompt removed — sent via Ollama system field to avoid
        double-injection on continuation iterations.
        """
        history_parts = [self._format_execution_step(i, result) for i, result in enumerate(execution_history, 1)]
        history_text = "\n\n".join(history_parts)
        steps_completed = len(execution_history)
        instructions = self._get_continuation_instructions(
            original_message, steps_completed, consecutive_invalid_tool_calls
        )

        return f"""## MULTI-STEP TASK CONTINUATION (Step {steps_completed + 1})

**Commands Already Executed ({steps_completed} step(s) completed so far):**
{history_text}

---
{instructions}"""

    def _image_fits_budget(self, prompt: str, model_name: str) -> bool:
        """Gate image attachment on the context budget (#11538).

        Uses ContextWindowManager's token estimate plus the fixed per-image
        token cost (VISION_IMAGE_TOKEN_ESTIMATE) so a screenshot never
        silently blows the model's max-history-token budget.
        """
        from context_window_manager import ContextWindowManager

        mgr = ContextWindowManager()
        prompt_tokens = mgr.estimate_tokens(prompt)
        max_tokens = mgr.get_max_history_tokens(model_name)
        return (prompt_tokens + VISION_IMAGE_TOKEN_ESTIMATE) <= max_tokens

    def _build_vision_messages(self, current_prompt: str, image_b64: str) -> list[dict]:
        """Build the OpenAI-style image content block for an OpenAI-compatible
        /chat/completions payload. Issue #11538.

        Reuses OpenAIGPT4VProvider._build_openai_image_content — the existing
        content-block builder — rather than inventing a second one. Only used
        when _resolve_vision_payload_shape() says the target endpoint is
        "openai_chat" — the continuation loop today always targets Ollama's
        /api/generate instead (see _attach_vision_payload).
        """
        from modern_ai_integration import OpenAIGPT4VProvider

        content = OpenAIGPT4VProvider._build_openai_image_content(current_prompt, [image_b64])
        return [{"role": "user", "content": content}]

    def _attach_vision_payload(self, payload: dict, ollama_endpoint: str, current_prompt: str, image_b64: str) -> None:
        """Attach *image_b64* to *payload* in the shape the target endpoint reads. Issue #11538.

        Provider-aware: Ollama's /api/generate ignores "messages" entirely and
        reads images from a top-level raw-base64 "images" list
        (_resolve_vision_payload_shape picks this for every endpoint this loop
        currently targets). An OpenAI-compatible /chat/completions path — not
        wired into this loop today — would read the "messages" content-block
        shape instead. Mutates *payload* in place.
        """
        shape = _resolve_vision_payload_shape(ollama_endpoint)
        if shape == "ollama_generate":
            payload["images"] = [_strip_data_url_prefix(image_b64)]
        else:
            payload["messages"] = self._build_vision_messages(current_prompt, image_b64)

    def _get_llm_request_payload(
        self,
        selected_model: str,
        current_prompt: str,
        system_prompt: str = "",
        api_kwargs: dict | None = None,
        image_b64: str | None = None,
        ollama_endpoint: str = "",
    ) -> dict:
        """Build LLM request payload.

        Issue #8993: api_kwargs are merged at top level for Anthropic extended-thinking.
        Issue #11538: when *image_b64* is set and the model is vision-capable and the
        image fits the context budget, it is attached in the shape *ollama_endpoint*
        actually consumes (see _attach_vision_payload) — vision-capable models get it,
        non-vision models keep the existing text-only "prompt" field, unaffected.
        """
        payload = {
            "model": selected_model,
            "prompt": current_prompt,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_ctx": ModelConfig.CHAT_NUM_CTX,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt
        if api_kwargs:
            payload.update(api_kwargs)
        vision_ready = image_b64 and _model_supports_vision(selected_model)
        if vision_ready and self._image_fits_budget(current_prompt, selected_model):
            self._attach_vision_payload(payload, ollama_endpoint, current_prompt, image_b64)
        return payload

    async def _log_and_parse_tool_calls(
        self, llm_response: str, iteration: int, session_id: str = "", context: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """
        Log response details and parse tool calls.

        Issue #620: Extracted from _process_single_llm_iteration.
        Issue #4262: Emit BEFORE_TOOL_PARSE hook before parsing tool calls.
        """
        from chat_workflow.llm_handler import _emit_before_tool_parse

        # Emit BEFORE_TOOL_PARSE hook to allow extensions to inspect/modify response
        modified_response = await _emit_before_tool_parse(llm_response, session_id, context or {})

        has_tool_call_tag = "<TOOL_CALL" in modified_response or "<tool_call" in modified_response
        logger.info(
            "[Issue #651] Iteration %d: Response has TOOL_CALL tag: %s, snippet: %s",
            iteration,
            has_tool_call_tag,
            modified_response[:500].replace("\n", " "),
        )

        # Issue #716: On first iteration, defer tool execution for plan-first
        is_first_iteration = iteration == 1
        tool_calls = self._parse_tool_calls(modified_response, is_first_iteration=is_first_iteration)
        logger.info(
            "[Issue #352] Iteration %d: Parsed %d tool calls",
            iteration,
            len(tool_calls),
        )
        return tool_calls

    def _create_llm_service_error(self, status_code: int) -> WorkflowMessage:
        """
        Create an error WorkflowMessage for LLM service failures.

        Issue #620: Extracted from _process_single_llm_iteration to reduce function length.

        Args:
            status_code: HTTP status code from the failed request

        Returns:
            WorkflowMessage with error details. Issue #620.
        """
        logger.error("[ChatWorkflowManager] Ollama request failed: %s", status_code)
        return WorkflowMessage(
            type="error",
            content=f"LLM service error: {status_code}",
            metadata={"error": True},
        )

    async def _stream_and_collect_llm_chunks(
        self,
        response,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ):
        """
        Stream LLM response and collect chunks.

        Issue #620: Extracted from _process_single_llm_iteration to reduce function length.

        Yields:
            WorkflowMessage chunks, then the final llm_response string. Issue #620.
        """
        llm_response = ""
        async for chunk_msg, llm_response, is_done, _ in self._stream_llm_response(
            response, selected_model, terminal_session_id, used_knowledge, rag_citations
        ):
            if chunk_msg:
                yield chunk_msg
            if is_done:
                break
        yield llm_response

    async def _process_single_llm_iteration(
        self,
        http_client,
        ollama_endpoint: str,
        selected_model: str,
        current_prompt: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        iteration: int,
        system_prompt: str = "",
        api_kwargs: dict | None = None,
        image_b64: str | None = None,
    ):
        """Process a single LLM iteration. Yields chunks, then (llm_response, tool_calls). Issue #620.

        Issue #11538: ``image_b64`` (the latest browser/VNC screenshot, if any) is
        threaded into the payload, gated on vision support and attached in the shape
        ``ollama_endpoint`` (the actual POST target) consumes — see _attach_vision_payload.
        """
        import aiohttp

        payload = self._get_llm_request_payload(
            selected_model,
            current_prompt,
            system_prompt,
            api_kwargs=api_kwargs,
            image_b64=image_b64,
            ollama_endpoint=ollama_endpoint,
        )
        llm_response = ""

        try:
            async with await http_client.post(
                ollama_endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=None, connect=TIMEOUT_HTTP_DEFAULT),
            ) as response:
                logger.info("[ChatWorkflowManager] Ollama response status: %s", response.status)
                if response.status != 200:
                    yield self._create_llm_service_error(response.status)
                    yield (None, None)
                    return

                async for item in self._stream_and_collect_llm_chunks(
                    response,
                    selected_model,
                    terminal_session_id,
                    used_knowledge,
                    rag_citations,
                ):
                    if isinstance(item, str):
                        llm_response = item
                    else:
                        yield item

                logger.info(
                    "[ChatWorkflowManager] Full LLM response length: %d chars (iter %d)",
                    len(llm_response),
                    iteration,
                )
        finally:
            await http_client.decrement_active()

        tool_calls = await self._log_and_parse_tool_calls(llm_response, iteration, terminal_session_id, {})
        yield (llm_response, tool_calls)

    def _handle_break_loop_tuple(self, tool_msg: Any) -> tuple:
        """Issue #665: Extracted from _process_tool_results to reduce function length.

        Handle break_loop tuple from _process_tool_calls.

        Returns:
            Tuple of (is_break_loop_tuple, break_loop_requested)
        """
        if isinstance(tool_msg, tuple) and len(tool_msg) == 2:
            break_loop_requested, _ = tool_msg
            if break_loop_requested:
                logger.info("[Issue #654] break_loop=True signal received from respond tool")
            return (True, break_loop_requested)
        return (False, False)

    def _validate_tool_message(self, tool_msg: Any) -> bool:
        """Issue #665: Extracted from _process_tool_results to reduce function length.

        Validate that tool_msg is valid and has required attributes.

        Returns:
            True if valid, False if should skip
        """
        if tool_msg is None:
            logger.warning("[Issue #680] Received None from _process_tool_calls - skipping")
            return False

        if not hasattr(tool_msg, "type"):
            logger.warning(
                "[Issue #680] tool_msg missing 'type' attribute: %s - skipping",
                type(tool_msg).__name__,
            )
            return False

        return True

    def _handle_execution_summary(
        self,
        tool_msg: WorkflowMessage,
        new_execution_results: List[Dict[str, Any]],
        execution_history: List[Dict[str, Any]],
    ) -> bool:
        """Issue #665: Extracted from _process_tool_results to reduce function length.

        Handle execution_summary message type.

        Returns:
            True if this was an execution_summary (caller should continue)
        """
        if tool_msg.type == "execution_summary":
            new_results = tool_msg.metadata.get("execution_results", [])
            new_execution_results.extend(new_results)
            execution_history.extend(new_results)
            logger.info(
                "[Issue #651] Collected %d execution results (total history: %d)",
                len(new_results),
                len(execution_history),
            )
            return True
        return False

    def _handle_tool_message_types(
        self,
        tool_msg: WorkflowMessage,
        workflow_messages: List[WorkflowMessage],
    ) -> tuple:
        """Issue #665: Extracted from _process_tool_results to reduce function length.

        Handle various tool message types and track state.

        Returns:
            Tuple of (has_pending_approval, processed_any_command)
        """
        has_pending_approval = False

        if tool_msg.type == "command_approval_request":
            has_pending_approval = True
            logger.info("[Issue #651] Command requires approval - will wait for resolution")

        if tool_msg.type in _TERMINAL_MESSAGE_TYPES:
            workflow_messages.append(tool_msg)

        if tool_msg.type == "error":
            logger.warning(
                "[Issue #651] Tool processing error: %s - LLM will decide next action",
                tool_msg.content[:100],
            )

        return (has_pending_approval, True)

    async def _process_tool_results(
        self,
        tool_calls: List[Dict[str, Any]],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_history: List[Dict[str, Any]],
        workflow_messages: List[WorkflowMessage],
        iteration: int,
        ctx: LLMIterationContext | None = None,
    ):
        """Issue #665: Refactored - Process tool calls and collect results.

        Issue #651: Fixed logic that incorrectly broke continuation loop.
        Issue #654: Added support for 'respond' tool with break_loop pattern.
        Issue #2310: Accepts optional ctx for consecutive-invalid-tool tracking.
        Issue #13295 (review B1): *iteration* is stamped on EVERY yielded tool
        message, not only the ``_TERMINAL_MESSAGE_TYPES`` ones
        ``_handle_tool_message_types`` appends to ``workflow_messages``. The
        graph path's accumulator (``graph._run_llm_iteration``) persists every
        non-streaming item this generator yields regardless of type — an
        untagged ``tool_result``/``response``/etc. fell into
        ``_build_persist_batch``'s untagged-leftover fallback and was
        misordered (and, for a ``response``-type duplicate of the completing
        prose, skipped the dedup guard entirely).

        Yields:
            WorkflowMessage items, then (results, has_pending_approval, should_break, break_loop_requested)
        """
        new_execution_results = []
        has_pending_approval = False
        break_loop_requested = False

        async for tool_msg in self._process_tool_calls(
            tool_calls,
            session_id,
            terminal_session_id,
            ollama_endpoint,
            selected_model,
            ctx=ctx,
        ):
            is_tuple, loop_requested = self._handle_break_loop_tuple(tool_msg)
            if is_tuple:
                break_loop_requested = loop_requested or break_loop_requested
                continue

            if not self._validate_tool_message(tool_msg):
                continue

            if self._handle_execution_summary(tool_msg, new_execution_results, execution_history):
                continue

            if tool_msg.metadata is not None:
                tool_msg.metadata["iteration"] = iteration

            pending, _ = self._handle_tool_message_types(tool_msg, workflow_messages)
            has_pending_approval = has_pending_approval or pending

            yield tool_msg

        logger.info(
            "[Issue #654] Tool results: exec_results=%d, pending_approval=%s, break_loop_requested=%s",
            len(new_execution_results),
            has_pending_approval,
            break_loop_requested,
        )

        yield (new_execution_results, has_pending_approval, False, break_loop_requested)

    async def _collect_llm_iteration_response(
        self,
        http_client,
        current_prompt: str,
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """
        Collect LLM response from iteration. Yields messages, then (llm_response, tool_calls).

        Issue #375: Uses LLMIterationContext to reduce parameter count from 10 to 4.
        """
        llm_response = None
        tool_calls = None

        # Issue #8993: Wire thinking mode from request context for Anthropic models.
        api_kwargs = None
        if ctx.context.get("thinking_mode_enabled") and "claude" in ctx.selected_model.lower():
            budget_tokens = int(ctx.context.get("thinking_budget_tokens", 10000))
            api_kwargs = {
                "thinking": {"type": "enabled", "budget_tokens": budget_tokens},
                "max_tokens": max(budget_tokens + 1000, 8192),
                "temperature": 1,
                "betas": ["interleaved-thinking-2025-05-14"],
            }
            logger.info(
                "[#8993] Thinking mode enabled for model=%s budget_tokens=%d",
                ctx.selected_model,
                budget_tokens,
            )

        # #9017: Reasoning effort — per-conversation override > user-default > 'auto'.
        # Only applied when thinking_mode is NOT already set (avoid double-config).
        if api_kwargs is None:
            effort = await _resolve_reasoning_effort(ctx.context)
            if effort and effort != "auto":
                effort_params = map_effort_to_provider_params(effort, ctx.selected_model)
                if effort_params:
                    thinking_tokens = effort_params.get("thinking_tokens")
                    if thinking_tokens and "claude" in ctx.selected_model.lower():
                        api_kwargs = {
                            "thinking": {"type": "enabled", "budget_tokens": thinking_tokens},
                            "max_tokens": max(thinking_tokens + 1000, 8192),
                            "temperature": 1,
                            "betas": ["interleaved-thinking-2025-05-14"],
                        }
                    else:
                        api_kwargs = effort_params
                    logger.info(
                        "[#9017] Reasoning effort=%s applied for model=%s params=%s",
                        effort,
                        ctx.selected_model,
                        list(effort_params),
                    )
        # Issue #11538: thread the most recent browser/VNC screenshot (last
        # VISION_TOOL_LOOKBACK_MESSAGES tool results) into this iteration's payload.
        latest_screenshot = _extract_latest_tool_screenshot(ctx.execution_history)
        # Prune older screenshots now that this iteration has read the window —
        # nothing outside it is ever consulted again (#11538 MINOR: retention).
        _prune_stale_screenshots(ctx.execution_history)

        async for item in self._process_single_llm_iteration(
            http_client,
            ctx.ollama_endpoint,
            ctx.selected_model,
            current_prompt,
            ctx.terminal_session_id,
            ctx.used_knowledge,
            ctx.rag_citations,
            iteration,
            system_prompt=ctx.system_prompt or "",
            api_kwargs=api_kwargs,
            image_b64=latest_screenshot,
        ):
            if isinstance(item, tuple):
                llm_response, tool_calls = item
            else:
                # Don't persist streaming chunks - they're for live display only
                # The final complete response is persisted in _persist_workflow_messages
                is_streaming_chunk = hasattr(item, "metadata") and item.metadata.get("streaming", False)
                if not is_streaming_chunk:
                    # Issue #13295: stamp the iteration that produced this
                    # message so _build_persist_batch can interleave it with
                    # the prose it followed, instead of collapsing the turn.
                    if hasattr(item, "metadata") and item.metadata is not None:
                        item.metadata["iteration"] = iteration
                    ctx.workflow_messages.append(item)
                yield item

        yield (llm_response, tool_calls)

    async def _collect_and_validate_llm_response(
        self,
        http_client,
        current_prompt: str,
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """
        Collect LLM response and validate it's not empty.

        Issue #665: Extracted from _run_continuation_iteration to reduce function length.

        Yields:
            WorkflowMessages, then (llm_response, tool_calls, should_stop)
        """
        llm_response = None
        tool_calls = None

        async for item in self._collect_llm_iteration_response(http_client, current_prompt, iteration, ctx):
            if isinstance(item, tuple):
                llm_response, tool_calls = item
            else:
                yield item

        if llm_response is None:
            logger.warning("[Issue #651] Iteration %d: No LLM response - stopping", iteration)
            yield (None, None, True)
            return

        if not tool_calls:
            logger.info(
                "[Issue #651] Iteration %d: No tool calls in response - task complete after %d step(s)",
                iteration,
                len(ctx.execution_history),
            )
            yield (llm_response, tool_calls, True)
            return

        yield (llm_response, tool_calls, False)

    def _parse_tool_result_tuple(
        self,
        item: tuple,
        current_results: List[Dict[str, Any]],
    ) -> tuple:
        """Parse tool result tuple with backwards compatibility.

        Issue #620.

        Returns:
            Tuple of (new_results, has_pending_approval, should_break, break_loop_requested)
        """
        if len(item) == 4:
            return item
        elif len(item) == 3:
            new_results, has_pending_approval, should_break = item
            return (new_results, has_pending_approval, should_break, False)
        else:
            new_results_or_empty, should_break = item
            if isinstance(new_results_or_empty, list):
                return (new_results_or_empty, False, should_break, False)
            return (current_results, False, should_break, False)

    async def _collect_tool_execution_results(
        self,
        tool_calls: List[Dict[str, Any]],
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """Collect tool execution results. Issue #620.

        Yields:
            WorkflowMessages, then (new_results, has_pending_approval, should_break, break_loop_requested)
        """
        logger.info(
            "[Issue #651] Iteration %d: Processing %d tool call(s)",
            iteration,
            len(tool_calls),
        )

        new_results, has_pending_approval, should_break, break_loop_requested = (
            [],
            False,
            False,
            False,
        )

        async for item in self._process_tool_results(
            tool_calls,
            ctx.session_id,
            ctx.terminal_session_id,
            ctx.ollama_endpoint,
            ctx.selected_model,
            ctx.execution_history,
            ctx.workflow_messages,
            iteration,
            ctx=ctx,
        ):
            if isinstance(item, tuple):
                (
                    new_results,
                    has_pending_approval,
                    should_break,
                    break_loop_requested,
                ) = self._parse_tool_result_tuple(item, new_results)
            else:
                yield item

        yield (new_results, has_pending_approval, should_break, break_loop_requested)

    def _check_continuation_decision(
        self,
        iteration: int,
        break_loop_requested: bool,
        should_break: bool,
        new_results: List[Dict[str, Any]],
        has_pending_approval: bool,
    ) -> bool:
        """
        Determine if continuation loop should continue or stop.

        Issue #665: Extracted from _run_continuation_iteration to reduce function length.

        Returns:
            True if should continue, False if should stop
        """
        # Issue #654: If respond tool was used with break_loop=True, stop the loop
        if break_loop_requested:
            logger.info(
                "[Issue #654] Iteration %d: Respond tool signaled task completion (break_loop=True)",
                iteration,
            )
            return False

        # Issue #651: Only break if there was a catastrophic failure, not just empty results
        if should_break:
            logger.warning(
                "[Issue #651] Iteration %d: Catastrophic tool failure - stopping continuation",
                iteration,
            )
            return False

        # Issue #651: Log decision to continue
        logger.info(
            "[Issue #651] Iteration %d: Completed with %d new result(s), "
            "pending_approval=%s - continuing to next iteration",
            iteration,
            len(new_results),
            has_pending_approval,
        )
        return True

    async def _yield_llm_response_and_check_stop(
        self,
        http_client,
        current_prompt: str,
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """
        Yield LLM response items and check if iteration should stop early.

        Issue #620: Extracted from _run_continuation_iteration to reduce function length.

        Yields:
            WorkflowMessages, then (llm_response, tool_calls, should_stop). Issue #620.
        """
        llm_response = None
        tool_calls = None
        should_stop = False

        async for item in self._collect_and_validate_llm_response(http_client, current_prompt, iteration, ctx):
            if isinstance(item, tuple) and len(item) == 3:
                llm_response, tool_calls, should_stop = item
            else:
                yield item

        yield (llm_response, tool_calls, should_stop)

    async def _yield_tool_results_and_decide(
        self, tool_calls: List[Dict[str, Any]], iteration: int, ctx: LLMIterationContext
    ):
        """
        Yield tool execution results and determine if loop should continue.

        Issue #620: Extracted from _run_continuation_iteration to reduce function length.

        Yields:
            WorkflowMessages, then should_continue boolean. Issue #620.
        """
        new_results = []
        has_pending_approval = False
        should_break = False
        break_loop_requested = False

        async for item in self._collect_tool_execution_results(tool_calls, iteration, ctx):
            if isinstance(item, tuple) and len(item) == 4:
                (
                    new_results,
                    has_pending_approval,
                    should_break,
                    break_loop_requested,
                ) = item
            else:
                yield item

        should_continue = self._check_continuation_decision(
            iteration,
            break_loop_requested,
            should_break,
            new_results,
            has_pending_approval,
        )
        yield should_continue

    async def _run_continuation_iteration(
        self,
        http_client,
        current_prompt: str,
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """
        Run a single continuation iteration.

        Issue #375: Uses LLMIterationContext to reduce parameter count from 12 to 4.
        Issue #620: Refactored using Extract Method to reduce function length.
        Yields WorkflowMessages, then (llm_response, tool_calls, should_continue).
        """
        logger.info(
            "[Issue #651] Starting iteration %d - execution history has %d entries",
            iteration,
            len(ctx.execution_history),
        )

        llm_response = None
        tool_calls = None
        should_stop = False

        async for item in self._yield_llm_response_and_check_stop(http_client, current_prompt, iteration, ctx):
            if isinstance(item, tuple) and len(item) == 3:
                llm_response, tool_calls, should_stop = item
            else:
                yield item

        if should_stop:
            yield (llm_response, tool_calls, False)
            return

        should_continue = False
        async for item in self._yield_tool_results_and_decide(tool_calls, iteration, ctx):
            if isinstance(item, bool):
                should_continue = item
            else:
                yield item

        yield (llm_response, tool_calls, should_continue)

    def _create_llm_error_message(self, error: Exception, workflow_messages: List[WorkflowMessage]) -> WorkflowMessage:
        """Create and log LLM error message."""
        logger.error("[ChatWorkflowManager] Direct LLM call failed: %s", error)
        error_msg = WorkflowMessage(
            type="error",
            content=f"Failed to connect to LLM: {str(error)}",
            metadata={"error": True},
        )
        workflow_messages.append(error_msg)
        return error_msg

    async def _run_continuation_loop_iteration(
        self,
        http_client,
        current_prompt: str,
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """
        Run a single loop iteration. Yields (llm_response, should_continue) at end.

        Issue #375: Uses LLMIterationContext to reduce parameter count from 12 to 4.
        Issue #11612: Sets the lightweight_mode_used ContextVar here — the single
        seam both the legacy continuation loop (_run_llm_iterations) and the
        LangGraph path (graph.py::_run_llm_iteration) call through — instead of
        in the outer _execute_llm_continuation_loop wrapper, which the graph
        path bypasses entirely (causing the cost badge to always read False).
        """
        logger.info(
            "[ChatWorkflowManager] Continuation iteration %d/%d",
            iteration,
            self.MAX_CONTINUATION_ITERATIONS,
        )

        # MVA-1993 / #11216 / #11612: store lightweight_mode_used in a task-local
        # ContextVar (not on the shared singleton) for the response-metadata badge.
        _lw_token = _current_lightweight_mode.set(ctx.context.get("lightweight_mode_used", False))
        try:
            llm_response = None
            should_continue = False

            async for item in self._run_continuation_iteration(http_client, current_prompt, iteration, ctx):
                if isinstance(item, tuple) and len(item) == 3:
                    llm_response, _, should_continue = item
                else:
                    yield item

            yield (llm_response, should_continue)
        finally:
            # MVA-1993 / #11216: restore the caller's task-local value (token reset).
            _current_lightweight_mode.reset(_lw_token)

    async def _run_llm_iteration_plan_only(
        self,
        http_client,
        current_prompt: str,
        iteration: int,
        ctx: LLMIterationContext,
    ):
        """Plan-only LLM iteration for the flag-gated approval-interrupt (GH#11202).

        Unlike ``_run_continuation_loop_iteration``, this NEVER dispatches the
        parsed tool calls — it only calls the LLM and parses its response via
        ``_collect_and_validate_llm_response`` (the same seam, minus dispatch).
        The caller (the graph's ``execute_tools`` node) is the sole dispatch
        point, so the approval interrupt can pause before any side effect.

        Yields WorkflowMessages, then ``(llm_response, tool_calls, should_stop)``
        where ``tool_calls`` are the raw pre-execution ``{"name", "params"}``
        dicts (never execution summaries).
        """
        _lw_token = _current_lightweight_mode.set(ctx.context.get("lightweight_mode_used", False))
        try:
            llm_response = None
            tool_calls = None
            should_stop = False

            async for item in self._collect_and_validate_llm_response(http_client, current_prompt, iteration, ctx):
                if isinstance(item, tuple) and len(item) == 3:
                    llm_response, tool_calls, should_stop = item
                else:
                    yield item

            yield (llm_response, tool_calls, should_stop)
        finally:
            _current_lightweight_mode.reset(_lw_token)

    def _log_iteration_start(self, ctx: LLMIterationContext) -> None:
        """Issue #665: Extracted from _run_llm_iterations to reduce function length.

        Log the start of the multi-step task loop.
        """
        logger.info(
            "[Issue #651] Starting multi-step task loop. Max iterations: %d, Original message: '%s'",
            self.MAX_CONTINUATION_ITERATIONS,
            ctx.message[:100] if ctx.message else "None",
        )

    def _log_iteration_complete(
        self,
        iteration: int,
        should_continue: bool,
        all_responses_count: int,
        history_count: int,
    ) -> None:
        """Issue #665: Extracted from _run_llm_iterations to reduce function length.

        Log completion of an iteration.
        """
        logger.info(
            "[Issue #651] Iteration %d complete: should_continue=%s, total_responses=%d, execution_history=%d",
            iteration,
            should_continue,
            all_responses_count,
            history_count,
        )

    def _build_and_log_continuation_prompt(
        self,
        ctx: LLMIterationContext,
        execution_history: List[Dict[str, Any]],
    ) -> str:
        """Issue #665: Extracted from _run_llm_iterations to reduce function length.

        Build continuation prompt and log debug info.
        """
        current_prompt = self._build_continuation_prompt(
            ctx.message,
            execution_history,
            ctx.consecutive_invalid_tool_calls,
        )
        logger.info(
            "[Issue #651] Built continuation prompt: %d chars, %d executed steps",
            len(current_prompt),
            len(execution_history),
        )
        instructions_start = current_prompt.find("MULTI-STEP TASK CONTINUATION")
        if instructions_start > -1:
            logger.debug(
                "[Issue #651] Continuation prompt instructions: %s",
                current_prompt[instructions_start : instructions_start + 1500].replace("\n", " | "),
            )
        return current_prompt

    def _log_task_complete(self, iteration: int, history_count: int) -> None:
        """Issue #665: Extracted from _run_llm_iterations to reduce function length."""
        logger.info(
            "[Issue #651] Task complete after %d iteration(s). Executed %d command(s) total.",
            iteration,
            history_count,
        )

    def _log_max_iterations_warning(self, iteration: int) -> None:
        """Issue #665: Extracted from _run_llm_iterations to reduce function length."""
        if iteration >= self.MAX_CONTINUATION_ITERATIONS:
            logger.warning(
                "[Issue #651] Reached max continuation iterations (%d) - stopping loop",
                self.MAX_CONTINUATION_ITERATIONS,
            )

    async def _run_llm_iterations(
        self,
        http_client,
        ctx: LLMIterationContext,
    ):
        """Issue #665: Refactored - Run LLM continuation iterations.

        Issue #375: Uses LLMIterationContext to reduce parameter count from 11 to 2.
        Issue #651: Added comprehensive logging for debugging multi-step tasks.

        Yields messages, then (all_responses, history, error).
        """
        execution_history = ctx.execution_history
        all_llm_responses = []
        current_prompt = ctx.initial_prompt

        self._log_iteration_start(ctx)

        for iteration in range(1, self.MAX_CONTINUATION_ITERATIONS + 1):
            # Issue #4264: Fire BEFORE_CONTINUATION hook before iteration starts
            should_continue_iteration = await _emit_before_continuation(iteration, ctx.session_id, ctx.context)
            if not should_continue_iteration:
                logger.info(
                    "[Issue #4264] BEFORE_CONTINUATION hook cancelled iteration %d",
                    iteration,
                )
                break

            llm_response, should_continue = None, False

            async for item in self._run_continuation_loop_iteration(http_client, current_prompt, iteration, ctx):
                if isinstance(item, tuple) and len(item) == 2:
                    llm_response, should_continue = item
                else:
                    yield item

            if llm_response is None:
                logger.warning("[Issue #651] No LLM response in iteration %d - aborting", iteration)
                yield ([], [], None)
                return

            all_llm_responses.append(llm_response)

            # Issue #4264: Fire AFTER_CONTINUATION hook after iteration completes
            llm_response = await _emit_after_continuation(iteration, llm_response, ctx.session_id, ctx.context)

            self._log_iteration_complete(
                iteration,
                should_continue,
                len(all_llm_responses),
                len(execution_history),
            )

            if not should_continue:
                self._log_task_complete(iteration, len(execution_history))
                break

            current_prompt = self._build_and_log_continuation_prompt(ctx, execution_history)

        self._log_max_iterations_warning(iteration)
        yield (all_llm_responses, execution_history, None)

    async def _execute_llm_continuation_loop(
        self,
        ctx: LLMIterationContext,
    ):
        """
        Execute the multi-step LLM continuation loop.

        Issue #375: Uses LLMIterationContext to reduce parameter count from 10 to 1.
        Issue MVA-1993 / #11612: lightweight_mode_used ContextVar is now set inside
        _run_continuation_loop_iteration (the shared seam both this loop and the
        LangGraph path call through), not here — see that method's docstring.
        """
        import aiohttp

        from autobot_shared.http_client import get_http_client

        try:
            http_client = get_http_client()
            async for item in self._run_llm_iterations(http_client, ctx):
                yield item

        except aiohttp.ClientError as error:
            error_msg = self._create_llm_error_message(error, ctx.workflow_messages)
            yield error_msg
            yield ([], [], error_msg)

        except Exception as error:
            error_msg = self._create_llm_error_message(error, ctx.workflow_messages)
            yield error_msg
            yield ([], [], error_msg)

    def _build_final_response_entry(
        self,
        chat_mgr,
        llm_response: str,
        batch: List[Dict[str, Any]],
        iteration: int | None = None,
    ) -> Dict[str, Any] | None:
        """Build the chat-history entry for one iteration's completed prose (#13214).

        Streamed chunks carry ``metadata.streaming = True`` (set unconditionally by
        ``StreamingMessage.to_workflow_message``) and are deliberately excluded from
        ``workflow_messages`` by both accumulators — see ``graph._run_llm_iteration``
        and ``_collect_llm_iteration_response``, whose comment states the complete
        reply "is persisted in _persist_workflow_messages". That was never true:
        ``llm_response`` arrived here and was dropped, so a conversational streamed
        reply persisted nothing and ``chat:session:*`` read back user-turns only.

        Issue #13295: *iteration* records which continuation pass produced this
        prose (1-indexed, matching ``all_llm_responses``) so a reload can be
        cross-referenced against the tool output it was interleaved with.
        The entry is built WITHOUT ``selected_model``/``rag_citations`` — Issue
        #13292's model badge/KB sources are attached retroactively by
        ``_attach_model_and_citations`` to whichever prose entry actually ends
        up LAST in the persisted batch, since the "final" iteration's own
        entry can be ``None`` (empty content, or deduped) and #13292 must not
        regress by leaving no entry carrying them at all (review F5).

        Returns None when there is nothing to add — an empty reply, or an assistant
        entry in *batch* already carrying byte-identical text. The scan is restricted
        to assistant entries so that a ``terminal_output`` or other system message
        echoing the reply cannot suppress the assistant turn.
        """
        content = strip_unparsed_tool_tags(llm_response or "").strip()
        if not content:
            return None
        assistant_texts = ((e.get("text") or "").strip() for e in batch if e.get("sender") == "assistant")
        if any(text == content for text in assistant_texts):
            return None
        return chat_mgr._build_message_dict(
            "assistant",
            content,
            "response",
            {
                "message_type": "llm_response",
                "streamed": True,
                "model": "",
                "iteration": iteration,
            },
            None,
            sources=[],
        )

    def _attach_model_and_citations(
        self,
        entry: Dict[str, Any],
        selected_model: str,
        rag_citations: List[Dict[str, Any]] | None,
        used_knowledge: bool,
    ) -> None:
        """Retroactively tag the LAST prose entry actually persisted (#13292, review F5).

        Issue #13292: the streamed chunks carried ``metadata.model`` and KB
        citations but, being streaming, were never the entries actually
        persisted. Attaching these at build time only to "the final
        iteration's" entry breaks when that entry is ``None`` (empty content
        or deduped) — no entry would carry them at all. Called once, after
        the whole batch is built, on whichever entry is actually last.
        """
        entry["metadata"]["model"] = selected_model
        entry["sources"] = _kb_sources_from_citations(rag_citations or []) if used_knowledge else []

    def _build_workflow_message_batch(self, chat_mgr, workflow_messages: List[WorkflowMessage]) -> List[Dict[str, Any]]:
        """Build the chat-history message dicts for one turn's WorkflowMessages.

        Issue #13296: extracted from ``_persist_workflow_messages`` (Extract
        Method, matching the rest of this module's convention for keeping
        functions short).
        """
        batch = []
        for wf_msg in workflow_messages:
            # Skip segment_complete markers — internal stream control
            # messages with empty content (Issue #1141).
            if wf_msg.type == "segment_complete":
                continue

            sender = "system" if wf_msg.type == "terminal_output" else "assistant"
            # #11545 (cosmetic): the persisted chat-history entry is the
            # final user-visible reply — strip any <TOOL_CALL ...> tag
            # that never matched the full grammar (genuinely unparsed)
            # so raw markup never renders. Guarded no-op otherwise.
            content = strip_unparsed_tool_tags(wf_msg.content)
            # Issue #4448: Extract KB-only citations into top-level sources list.
            # metadata.citations includes the always-appended llm_training entry —
            # filter it out so sources contains only knowledge-base references.
            raw_citations = (wf_msg.metadata or {}).get("citations", [])
            kb_citations = [c for c in raw_citations if c.get("type") == "knowledge_base"]
            batch.append(
                chat_mgr._build_message_dict(
                    sender,
                    content,
                    wf_msg.type,
                    wf_msg.metadata,
                    None,
                    sources=_kb_sources_from_citations(kb_citations),
                )
            )
        return batch

    def _iteration_persist_group(
        self,
        chat_mgr,
        workflow_messages: List[WorkflowMessage],
        response_text: str,
        iteration: int,
        batch: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], set, Dict[str, Any] | None]:
        """Build one iteration's prose + tool-message entries, in that order.

        Issue #13295: extracted from ``_build_persist_batch`` to keep it short.
        Live, ``_run_continuation_iteration`` always generates an iteration's
        prose (``_yield_llm_response_and_check_stop``) BEFORE dispatching the
        tool calls it contained (``_yield_tool_results_and_decide``) — so the
        prose entry precedes this iteration's own tool entries, not the other
        way around. Returns (this iteration's entries, ids of workflow_messages
        consumed, the prose entry actually built or None).
        """
        iter_messages = [m for m in workflow_messages if (m.metadata or {}).get("iteration") == iteration]
        consumed = {id(m) for m in iter_messages}
        # Built before the dedup check (not before the *returned* order) so a
        # same-iteration duplicate — e.g. the ``respond`` tool's own "response"
        # workflow message carrying byte-identical text — is still caught even
        # though it is placed AFTER the prose entry in the final order.
        tool_entries = self._build_workflow_message_batch(chat_mgr, iter_messages)

        final_entry = self._build_final_response_entry(
            chat_mgr,
            response_text,
            batch + tool_entries,
            iteration=iteration,
        )
        entries = [final_entry] if final_entry else []
        entries.extend(tool_entries)
        return entries, consumed, final_entry

    def _build_persist_batch(
        self,
        chat_mgr,
        workflow_messages: List[WorkflowMessage],
        all_llm_responses: List[str],
        selected_model: str,
        rag_citations: List[Dict[str, Any]] | None,
        used_knowledge: bool,
    ) -> List[Dict[str, Any]]:
        """Build the full persisted batch for one turn, in true chronological order.

        Extracted from ``_persist_workflow_messages`` (#13296 / #13303 review).

        Issue #13295: a tool-using turn normally runs 2+ continuation iterations
        (``manager.MAX_CONTINUATION_ITERATIONS`` loop); each appends its own
        prose to *all_llm_responses*, and live, an iteration's prose streams
        BEFORE the tool call it introduces executes. Reverted front-insertion
        (#13303 review) showed the whole reply — every iteration's prose
        collapsed into one string — cannot be positioned correctly with a
        single insertion point: appended-last inverts the common 2-iteration
        case (prose1 -> tool_output -> prose2 became tool_output -> combined);
        inserted-first breaks the single-iteration case.

        Fix: every point that appends a workflow message now stamps
        ``metadata.iteration`` on it (``_process_tool_results`` for the shared
        tool-dispatch path, ``_collect_llm_iteration_response`` for other LLM
        yields, and ``graph.execute_tools`` for the GH#11202 interrupt-resume
        dispatch that bypasses ``_process_tool_results`` entirely). This walks
        iterations 1..N, emitting iteration *i*'s prose (``all_llm_responses[i-1]``)
        followed by its own tool messages — matching the live order exactly,
        for any number of iterations. ``selected_model``/``rag_citations`` are
        attached after the loop (``_attach_model_and_citations``) to whichever
        prose entry actually ends up last — not necessarily the final
        iteration's, since that entry can be ``None`` (#13292 review F5).

        Messages carrying no iteration tag, or one beyond ``len(all_llm_responses)``
        (the error-turn path, which passes an empty response list — #13295
        confirmed unchanged), are appended last, preserving the pre-#13295 flat
        behaviour for that case.
        """
        batch: List[Dict[str, Any]] = []
        consumed: set = set()
        last_prose_entry: Dict[str, Any] | None = None

        for idx, response_text in enumerate(all_llm_responses):
            iteration = idx + 1
            entries, group_consumed, final_entry = self._iteration_persist_group(
                chat_mgr,
                workflow_messages,
                response_text,
                iteration,
                batch,
            )
            if final_entry is not None:
                last_prose_entry = final_entry
            batch.extend(entries)
            consumed.update(group_consumed)

        leftover = [m for m in workflow_messages if id(m) not in consumed]
        batch.extend(self._build_workflow_message_batch(chat_mgr, leftover))

        if last_prose_entry is not None:
            self._attach_model_and_citations(last_prose_entry, selected_model, rag_citations, used_knowledge)
        return batch

    async def _persist_workflow_messages(
        self,
        session_id: str,
        workflow_messages: List[WorkflowMessage],
        all_llm_responses: List[str],
        *,
        selected_model: str = "",
        rag_citations: List[Dict[str, Any]] | None = None,
        used_knowledge: bool = False,
    ) -> None:
        """Persist WorkflowMessages to chat history in a single batch.

        Issue #332: Original implementation.
        Issue #1316: Batch all messages into one load/save cycle instead
        of N individual add_message() calls.
        Issue #13214: also persist the completed streamed reply — which every
        caller already computed but which was previously ignored.
        Issue #13292: ``selected_model``/``rag_citations``/``used_knowledge`` let
        the completed-reply entry carry the same model badge and KB citations the
        (discarded) streaming chunks carried — keyword-only and defaulted so
        existing callers (incl. the error-turn path, which never has a model to
        report) are unaffected.
        Issue #13295: *all_llm_responses* replaces the pre-joined
        ``"\\n\\n".join(...)`` string — one entry per continuation iteration —
        so ``_build_persist_batch`` can interleave each iteration's prose with
        the tool output it introduced instead of appending the whole reply
        after every tool entry. The error-turn path passes ``[]`` (never had a
        completed response); see ``_build_persist_batch`` for the exact
        ordering and its unchanged fallback for that case.
        """
        from chat_history import ChatHistoryManager

        try:
            chat_mgr = ChatHistoryManager()
            batch = self._build_persist_batch(
                chat_mgr, workflow_messages, all_llm_responses, selected_model, rag_citations, used_knowledge
            )

            if batch:
                await chat_mgr.add_messages_batch(session_id, batch)

            logger.info(
                "Persisted conversation to chat history: " "session=%s, workflow_messages=%d, persisted=%d",
                session_id,
                len(workflow_messages or []),
                len(batch),
            )

        except Exception as persist_error:
            logger.error(
                "Failed to persist WorkflowMessages to chat history: %s",
                persist_error,
                exc_info=True,
            )

    async def _persist_user_message(self, session_id: str, message: str) -> None:
        """Persist user message immediately to prevent data loss on restart.

        Bug fix: de-duplicate retries. When a previous turn failed, the user
        often re-sends the same text. If the last persisted message is an
        identical, still-unanswered user message, skip writing a duplicate so
        the session does not accumulate repeated user turns with no reply.
        """
        from chat_history import ChatHistoryManager

        try:
            chat_mgr = ChatHistoryManager()

            # Read the tail for de-dup in its OWN guard: a read failure
            # (permission/corruption) must never block persisting the write.
            try:
                existing = await chat_mgr.load_session(session_id)
            except Exception:  # noqa: BLE001
                existing = []
            if existing:
                last = existing[-1]
                if last.get("sender") == "user" and (last.get("text") or "").strip() == (message or "").strip():
                    logger.debug("Skipping duplicate user message (retry) for session=%s", session_id)
                    return

            await chat_mgr.add_message(
                sender="user",
                text=message,
                message_type="default",
                session_id=session_id,
            )
            logger.debug("✅ Persisted user message immediately: session=%s", session_id)
        except Exception as persist_error:
            logger.error("Failed to persist user message immediately: %s", persist_error)

    async def _handle_exit_intent(self, session_id: str, workflow_messages: List[WorkflowMessage]):
        """Handle user exit intent. Yields exit message and persists."""
        from chat_history import ChatHistoryManager

        logger.info(
            "[ChatWorkflowManager] User explicitly requested to exit conversation: %s",
            session_id,
        )
        exit_msg = WorkflowMessage(
            type="response",
            content="Goodbye! Feel free to return anytime if you need assistance. Take care!",
            metadata={"message_type": "exit_acknowledgment", "exit_detected": True},
        )
        workflow_messages.append(exit_msg)
        yield exit_msg

        try:
            chat_mgr = ChatHistoryManager()
            await chat_mgr.add_message(
                sender="assistant",
                text=exit_msg.content,
                message_type="exit_acknowledgment",
                session_id=session_id,
            )
        except Exception as persist_error:
            logger.error("Failed to persist exit message: %s", persist_error)

    async def _handle_slash_command(self, session_id: str, message: str, workflow_messages: List[WorkflowMessage]):
        """Handle slash command execution. Yields command response and persists."""
        from chat_history import ChatHistoryManager

        slash_handler = get_slash_command_handler()
        logger.info("[ChatWorkflowManager] Processing slash command: %s", message[:50])
        result = await slash_handler.execute(message, chat_id=session_id)

        cmd_msg = WorkflowMessage(
            type="response",
            content=result.content,
            metadata={
                "message_type": "slash_command",
                "command_type": result.command_type.value,
                "success": result.success,
                "file_paths": result.file_paths,
            },
        )
        workflow_messages.append(cmd_msg)
        yield cmd_msg

        try:
            chat_mgr = ChatHistoryManager()
            await chat_mgr.add_message(
                sender="assistant",
                text=result.content,
                message_type="slash_command",
                session_id=session_id,
            )
        except Exception as persist_error:
            logger.error("Failed to persist slash command response: %s", persist_error)

    async def _prepare_llm_workflow_params(
        self, session, message: str, context: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        """
        Prepare LLM request parameters from session and message.

        Issue #620: Extracted from _execute_llm_workflow to reduce function length.
        Issue #715: Registers user message in history before building context.
        Issue MVA-1992: Determine lightweight_mode from complexity tier.

        Returns:
            Dictionary with LLM parameters. Issue #620.
        """
        self._register_user_message_in_history(session, message)

        use_knowledge = context.get("use_knowledge", True) if context else True
        # Issue #1325: Extract language from context for system prompt
        language = context.get("language") if context else None
        if language:
            session.metadata["language"] = language

        # #11261: stash caller identity so the prompt-build path can scope
        # trajectory retrieval to this user/tenant (strict isolation, #11089).
        if context:
            session.metadata["user_id"] = context.get("user_id") or ""
            session.metadata["tenant_id"] = context.get("tenant_id") or context.get("org_id") or ""
            # #11501 T2: CEO-chat path carries company_id — used to append the
            # board-tool teaching to the system prompt for this turn only.
            session.metadata["company_id"] = context.get("company_id") or ""
            # #11585: per-request model override — persisted on the session so
            # later messages in this conversation inherit the choice.
            if context.get("model"):
                session.metadata["model_override"] = str(context["model"])

        # Issue MVA-1992: Determine if query qualifies for lightweight mode.
        # Trivial tier (GH#9050, score < trivial_threshold) is the primary
        # signal; simple tier (score < complexity_threshold) is used as a
        # fallback when trivial tier is not configured.
        lightweight_mode = False
        try:
            from llm_shared.tiered_routing.complexity_router import ComplexityRouter
            from llm_shared.tiered_routing.tier_config import TierConfig

            tier_config = TierConfig.from_config()
            if tier_config.enabled:
                router = ComplexityRouter(config=tier_config)
                messages = [{"role": "user", "content": message}]
                _, complexity_result = router.route(messages)
                # Trivial tier is the canonical lightweight signal (GH#9050).
                # Fall back to simple tier when trivial is not configured.
                is_trivial = complexity_result.tier == "trivial"
                is_simple_fallback = complexity_result.tier == "simple" and not getattr(
                    tier_config.models, "trivial", ""
                )
                lightweight_mode = is_trivial or is_simple_fallback
                if lightweight_mode:
                    logger.info(
                        "[MVA-1992] Lightweight mode enabled (tier=%s, score=%.1f)",
                        complexity_result.tier,
                        complexity_result.score,
                    )
        except Exception as e:
            logger.warning("[MVA-1992] Complexity routing failed, defaulting to full mode: %s", e)

        llm_params = await self._prepare_llm_request_params(
            session, message, use_knowledge=use_knowledge, language=language, lightweight_mode=lightweight_mode
        )
        # MVA-1993: Store lightweight_mode in params for response metadata
        llm_params["lightweight_mode_used"] = lightweight_mode

        logger.info(
            "[ChatWorkflowManager] Initial prompt length: %d characters",
            len(llm_params["prompt"]),
        )

        # Issue #5073: pre-compact hook — fire-and-forget before returning so
        # the snapshot is enqueued before the next LLM call consumes the context.
        asyncio.create_task(
            self._fire_pre_compact_hook(
                session_id=session.session_id,
                conversation_history=session.conversation_history or [],
                user_id=context.get("user_id") if context else None,
                model_name=llm_params.get("model", ""),
            )
        )

        return llm_params

    def _create_llm_iteration_context(
        self,
        llm_params: Dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        message: str,
        workflow_messages: List[WorkflowMessage],
        context: Dict[str, Any] | None = None,
    ) -> LLMIterationContext:
        """
        Create LLMIterationContext from prepared parameters.

        Issue #620: Extracted from _execute_llm_workflow to reduce function length.
        Issue #375: Uses context object to reduce parameter count.
        Issue MVA-1993: Includes lightweight_mode_used in context for response metadata.

        Returns:
            Configured LLMIterationContext. Issue #620.
        """
        # MVA-1993: Merge lightweight_mode_used into context
        merged_context = {**(context or {})}
        if "lightweight_mode_used" in llm_params:
            merged_context["lightweight_mode_used"] = llm_params["lightweight_mode_used"]

        # GH#11159/#11160: lift governed identity (agent role + work item + declared
        # approval gates) from the request context so the tool-dispatch seam can
        # enforce forbidden_work and approval categories.
        agent_context, work_item_id, approval_cats = build_governed_identity(merged_context, session_id)

        return LLMIterationContext(
            ollama_endpoint=llm_params["endpoint"],
            selected_model=llm_params["model"],
            session_id=session_id,
            terminal_session_id=terminal_session_id,
            used_knowledge=llm_params.get("used_knowledge", False),
            rag_citations=llm_params.get("citations", []),
            workflow_messages=workflow_messages,
            system_prompt=llm_params.get("system_prompt", ""),
            initial_prompt=llm_params["prompt"],
            message=message,
            context=merged_context,
            agent_context=agent_context,
            work_item_id=work_item_id,
            requires_approval_before=approval_cats,
        )

    async def _execute_llm_workflow(
        self,
        session_id: str,
        session,
        message: str,
        context: Dict[str, Any] | None,
        terminal_session_id: str,
        workflow_messages: List[WorkflowMessage],
    ):
        """
        Execute the main LLM workflow.

        Issue #620: Refactored using Extract Method to reduce function length.
        Issue #1315: Yields progress indicator before RAG retrieval.
        Yields WorkflowMessages.
        """
        # Issue #1315: Emit progress before RAG so frontend shows activity
        use_knowledge = context.get("use_knowledge", True) if context else True
        if use_knowledge and self.knowledge_service:
            progress = StreamingMessage(type="progress")
            progress.update("Searching knowledge base...")
            yield progress.to_workflow_message()

        llm_params = await self._prepare_llm_workflow_params(session, message, context)

        ctx = self._create_llm_iteration_context(
            llm_params, session_id, terminal_session_id, message, workflow_messages, context
        )

        all_llm_responses = []
        async for item in self._execute_llm_continuation_loop(ctx):
            if isinstance(item, tuple) and len(item) == 3:
                all_llm_responses, _, error = item
                if error:
                    return
            else:
                yield item

        # Issue #716/#11867: strip any internal continuation prompt the LLM echoed
        # back before the response is persisted / shown to the user — per-iteration
        # (Issue #13295: _persist_workflow_messages now needs each iteration's
        # prose separately to interleave with its tool output), which is at least
        # as precise as the prior joined-then-filtered pass since each pattern is
        # matched within one iteration's own text.
        filtered_responses = [self._filter_internal_prompts(r) for r in all_llm_responses]
        combined_response = "\n\n".join(filtered_responses)
        await self._persist_conversation(session_id, session, message, combined_response)
        await self._persist_workflow_messages(
            session_id,
            workflow_messages,
            filtered_responses,
            selected_model=ctx.selected_model,
            rag_citations=ctx.rag_citations,
            used_knowledge=ctx.used_knowledge,
        )

        # Issue #5073: fire-and-forget memory tasks via stop hook (non-blocking).
        # Replaces the direct verbatim-store asyncio.create_task from #5070 with
        # a Celery-backed stop hook so writes are durable and off the hot path.
        user_id = context.get("user_id") if context else None
        tenant_id = (context.get("tenant_id") or context.get("org_id")) if context else None
        turn = len([m for m in workflow_messages if m.type == "response"])
        asyncio.create_task(self._fire_stop_hook(session_id, message, combined_response, user_id, turn, tenant_id))

    async def _fire_stop_hook(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        user_id: str | None,
        turn_number: int,
        tenant_id: str | None = None,
    ) -> None:
        """Invoke stop hook to enqueue memory tasks after turn completion.

        Issue #5073: Delegates to chat_workflow.stop_hook.on_turn_complete
        which enqueues write_verbatim + extract_facts Celery tasks.
        #11261: also passes tenant_id so trajectory capture stays scoped.
        Called via asyncio.create_task — never blocks the response stream.
        """
        from chat_workflow.stop_hook import on_turn_complete

        await on_turn_complete(
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            user_id=user_id,
            turn_number=turn_number,
            tenant_id=tenant_id,
        )

    async def _fire_pre_compact_hook(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]],
        user_id: str | None,
        model_name: str,
    ) -> None:
        """Invoke pre-compact hook to snapshot session before context overflow.

        Issue #5073: Delegates to chat_workflow.compact_hook.on_pre_compact
        which enqueues compact_snapshot_task when usage ≥ 85 %.
        Called via asyncio.create_task — never blocks the response stream.
        """
        from chat_workflow.compact_hook import on_pre_compact

        # Convert WorkflowSession history dicts to the format expected by the hook.
        messages = [
            {"role": "user", "content": entry.get("user", "")} for entry in conversation_history if entry.get("user")
        ] + [
            {"role": "assistant", "content": entry.get("assistant", "")}
            for entry in conversation_history
            if entry.get("assistant")
        ]
        await on_pre_compact(
            session_id=session_id,
            messages=messages,
            user_id=user_id,
            model_name=model_name,
        )

    @error_boundary(component="chat_workflow_manager", function="process_message")
    async def process_message(
        self, session_id: str, message: str, context: Dict[str, Any] | None = None
    ) -> List[WorkflowMessage]:
        """Process a message through the workflow system and return all messages."""
        messages = []
        async for msg in self.process_message_stream(session_id, message, context):
            messages.append(msg)
        return messages

    async def _process_special_intents(
        self,
        session_id: str,
        message: str,
        user_wants_exit: bool,
        workflow_messages: List[WorkflowMessage],
    ):
        """Handle exit intent and slash commands.

        Issue #620.

        Yields:
            WorkflowMessage if special intent handled
        Returns:
            True if special intent was handled, False otherwise
        """
        if user_wants_exit:
            async for msg in self._handle_exit_intent(session_id, workflow_messages):
                yield msg
            yield True
            return

        slash_handler = get_slash_command_handler()
        if slash_handler.is_slash_command(message):
            async for msg in self._handle_slash_command(session_id, message, workflow_messages):
                yield msg
            yield True
            return

        yield False

    def _create_processing_error_message(
        self,
        session_id: str,
        error: Exception,
        workflow_messages: List[WorkflowMessage],
    ) -> WorkflowMessage:
        """Create error message for processing failures.

        Issue #620.

        Returns:
            WorkflowMessage with error details
        """
        logger.error(
            "Error processing message for session %s: %s",
            session_id,
            error,
            exc_info=True,
        )
        error_msg = WorkflowMessage(
            type="error",
            content=f"Error processing message: {str(error)}",
            metadata={"error": True, "session_id": session_id},
        )
        workflow_messages.append(error_msg)
        return error_msg

    async def _apply_session_role(self, session_id: str, context: Dict[str, Any] | None) -> Dict[str, Any] | None:
        """Overlay the trusted per-session governance onto the chat context (GH#11186/#11202).

        A server-set session role overrides any client-supplied ``agent_id`` so the
        pinned agent's ``forbidden_work`` is enforced at the tool seam and cannot be
        lifted by the caller. GH#11202: when the approval gate flag is on and the
        session declares approval categories, they are overlaid as
        ``requires_approval_before`` so the existing ``_enforce_work_item_approval``
        seam gate holds matching tools BEFORE they execute — the correct
        pre-execution stage. Backend decides; the frontend only calls the endpoints.
        """
        from chat_workflow.session_role import CHAT_APPROVAL_GATE_ENABLED, SessionRoleService, apply_role

        svc = SessionRoleService()
        context = apply_role(context, await svc.get_role(session_id))
        if CHAT_APPROVAL_GATE_ENABLED:
            categories = await svc.get_approval_categories(session_id)
            if categories:
                context = {**(context or {}), "requires_approval_before": categories}
        return context

    async def process_message_stream(self, session_id: str, message: str, context: Dict[str, Any] | None = None):
        """Process a message via LangGraph StateGraph.

        Issue #1043: Replaced hand-rolled async generator with LangGraph graph
        invocation. The graph handles state management, checkpointing, and
        interrupt-based command approval natively.

        Falls back to legacy flow if LangGraph is unavailable.
        """
        # GH#11186: apply the trusted per-session role once here, so both the graph
        # and legacy paths carry the governed identity into the tool seam.
        context = await self._apply_session_role(session_id, context)
        try:
            async for msg in self._process_via_graph(session_id, message, context):
                yield msg
        except Exception as graph_err:
            logger.warning(
                "LangGraph flow failed, falling back to legacy: %s",
                graph_err,
            )
            async for msg in self._process_message_stream_legacy(session_id, message, context):
                yield msg

    async def _process_via_graph(
        self,
        session_id: str,
        message: str,
        context: Dict[str, Any] | None = None,
    ):
        """Run the LangGraph StateGraph for chat processing.

        Issue #1043: Graph nodes delegate to existing manager methods.
        A stream_callback + asyncio.Queue bridges graph execution to the
        SSE async generator expected by the API layer.
        """
        from .graph import get_compiled_graph

        graph = await get_compiled_graph(self)
        queue = asyncio.Queue()

        def stream_callback(data):
            """Callback invoked by graph nodes for real-time streaming."""
            queue.put_nowait(data)

        config = {
            "configurable": {
                "thread_id": session_id,
                "manager": self,
                "stream_callback": stream_callback,
            }
        }

        initial_state = {
            "session_id": session_id,
            "user_message": message,
            "context": context or {},
        }

        graph_task = asyncio.create_task(self._run_graph_task(graph, initial_state, config, queue))

        while True:
            data = await queue.get()
            if data is None:
                break
            if hasattr(data, "to_dict"):
                yield data
            else:
                # Preserve original ID to prevent poll-cycle churn (#1064)
                msg_id = data.get("id") or str(uuid.uuid4())
                yield WorkflowMessage(
                    type=data.get("type", "response"),
                    content=data.get("content", ""),
                    metadata=data.get("metadata", {}),
                    id=msg_id,
                )

        await graph_task

    async def _run_graph_task(self, graph, initial_state, config, queue):
        """Execute the graph and signal completion via queue sentinel."""
        try:
            result = await graph.ainvoke(initial_state, config=config)

            # Check for interrupt (command approval needed)
            interrupt_data = result.get("__interrupt__")
            if interrupt_data:
                for intr in interrupt_data:
                    queue.put_nowait(intr.value)
        except Exception as exc:
            logger.error("Graph execution error: %s", exc, exc_info=True)
            # Issue #1475: Delete corrupted checkpoint so the session can recover.
            session_id = initial_state.get("session_id")
            if session_id:
                from .graph import delete_thread_checkpoints

                await delete_thread_checkpoints(session_id)
            if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
                error_content = "The model is taking too long to respond. Please try again."
            else:
                # Issue #9410: Never leak exception details in SSE streams
                error_content = "An unexpected error occurred. Please try again."
            queue.put_nowait(
                {
                    "type": "error",
                    "content": error_content,
                }
            )
        finally:
            queue.put_nowait(None)

    async def _process_message_stream_legacy(
        self, session_id: str, message: str, context: Dict[str, Any] | None = None
    ):
        """Legacy message processing (pre-LangGraph fallback).

        Issue #620: Original implementation preserved as fallback.
        """
        workflow_messages = []

        try:
            (
                session,
                terminal_session_id,
                user_wants_exit,
            ) = await self._initialize_chat_session(session_id, message)
            await self._persist_user_message(session_id, message)

            async for item in self._process_special_intents(session_id, message, user_wants_exit, workflow_messages):
                if isinstance(item, bool):
                    if item:
                        return
                else:
                    yield item

            async for msg in self._execute_llm_workflow(
                session_id,
                session,
                message,
                context,
                terminal_session_id,
                workflow_messages,
            ):
                yield msg

        except Exception as e:
            yield self._create_processing_error_message(session_id, e, workflow_messages)

    async def resume_graph(
        self,
        session_id: str,
        decision: Dict[str, Any],
    ):
        """Resume a paused graph after command approval interrupt.

        Issue #1043: Called when the user approves or denies a command.
        The graph resumes from its checkpointed state with the decision.
        """
        from langgraph.types import Command

        from .graph import get_compiled_graph

        graph = await get_compiled_graph(self)
        queue = asyncio.Queue()

        def stream_callback(data):
            queue.put_nowait(data)

        config = {
            "configurable": {
                "thread_id": session_id,
                "manager": self,
                "stream_callback": stream_callback,
            }
        }

        graph_task = asyncio.create_task(self._run_graph_task(graph, Command(resume=decision), config, queue))

        while True:
            data = await queue.get()
            if data is None:
                break
            if hasattr(data, "to_dict"):
                yield data
            else:
                # Preserve original ID to prevent poll-cycle churn (#1064)
                msg_id = data.get("id") or str(uuid.uuid4())
                yield WorkflowMessage(
                    type=data.get("type", "response"),
                    content=data.get("content", ""),
                    metadata=data.get("metadata", {}),
                    id=msg_id,
                )

        await graph_task

    async def shutdown(self):
        """Shutdown the workflow manager and clean up resources."""
        try:
            async with self._lock:
                # Clear all sessions
                session_count = len(self.sessions)
                self.sessions.clear()

                # Reset state
                self.default_workflow = None
                self._initialized = False

                logger.info(
                    "✅ ChatWorkflowManager shutdown complete, cleaned up %d sessions",
                    session_count,
                )

        except Exception as e:
            logger.error("❌ Error during ChatWorkflowManager shutdown: %s", e)
