# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import re
import uuid
from typing import Any, Dict, FrozenSet, List, Optional

from async_chat_workflow import WorkflowMessage
from slash_command_handler import get_slash_command_handler

from autobot_shared.error_boundaries import error_boundary, get_error_boundary_manager
from autobot_shared.redis_client import get_redis_client as get_redis_manager

from .conversation import ConversationHandlerMixin
from .llm_handler import LLMHandlerMixin
from .models import LLMIterationContext, StreamingMessage, WorkflowSession
from .session_handler import SessionHandlerMixin
from .tool_handler import ToolHandlerMixin

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for terminal message types
_TERMINAL_MESSAGE_TYPES: FrozenSet[str] = frozenset(
    {"terminal_command", "terminal_output", "error"}
)

# Issue #380: Module-level frozenset for block content types
_BLOCK_CONTENT_TYPES: FrozenSet[str] = frozenset({"thought", "planning"})

# Issue #380: Pre-compiled regex for tool call normalization
_TOOL_CALL_OPEN_RE = re.compile(r"<TOOL_\s+CALL")
_TOOL_CALL_CLOSE_RE = re.compile(r"</TOOL_\s+CALL>")

# Issue #727: Pattern to detect completed tool call tags (for hallucination prevention)
# Matches </tool_call>, </TOOL_CALL>, and </TOOL_ CALL> (underscore variant) with optional whitespace
_TOOL_CALL_COMPLETE_RE = re.compile(r"</\s*tool_?\s*call\s*>", re.IGNORECASE)

# Issue #716: Patterns for internal prompts that should not be shown to users
# These are continuation instructions that LLM sometimes echoes back
_INTERNAL_PROMPT_PATTERNS = [
    re.compile(
        r"\*\*CRITICAL MULTI-STEP TASK INSTRUCTIONS.*?\*\*YOUR RESPONSE:\*\*",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r"User is in the middle of a multi-step task\. \d+ step\(s\) have been completed\."
    ),
    re.compile(r"\*\*ORIGINAL USER REQUEST \(analyze this.*?\)\:\*\*"),
    re.compile(
        r"\*\*DECISION PROCESS:\*\*.*?\*\*IF TASK IS COMPLETE\*\*.*?TOOL_CALL",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"\*\*IF MORE STEPS NEEDED\*\*.*?`<TOOL_CALL", re.DOTALL),
]


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
        self.default_workflow: Optional[Any] = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self.redis_manager = None  # Async Redis manager
        self.redis_client = None  # Main database connection
        self.conversation_history_ttl = 86400  # 24 hours in seconds
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
            self.redis_client = await get_redis_manager(
                async_client=True, database="main"
            )
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
            from backend.knowledge_factory import get_knowledge_base_async
            from backend.services.chat_knowledge_service import ChatKnowledgeService
            from backend.services.rag_service import RAGService

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

        The LLM sometimes echoes the continuation instructions we send it, which
        should never be shown to the user. This filters those out.

        Args:
            text: LLM response text that may contain echoed internal prompts

        Returns:
            Text with internal prompts removed
        """
        filtered = text
        for pattern in _INTERNAL_PROMPT_PATTERNS:
            filtered = pattern.sub("", filtered)

        # Also clean up any resulting multiple newlines
        filtered = re.sub(r"\n{3,}", "\n\n", filtered)

        if filtered != text:
            logger.debug(
                "[Issue #716] Filtered internal prompts from LLM response "
                "(original: %d chars, filtered: %d chars)",
                len(text),
                len(filtered),
            )

        return filtered.strip()

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
                "citations": rag_citations if used_knowledge else [],
            },
        )

    def _parse_stream_chunk(self, line: bytes) -> Optional[Dict[str, Any]]:
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
            new_segment_start = self._find_new_segment_start(
                llm_response, new_type, previous_type=current_message_type
            )
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
            new_segment_start = self._find_new_segment_start(
                llm_response, new_type, previous_type=current_message_type
            )
            return (None, str(uuid.uuid4()), new_segment_start, new_type)

        return (None, current_message_id, None, current_message_type)

    def _find_new_segment_start(
        self, llm_response: str, new_type: str, previous_type: str = "response"
    ) -> str:
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
                "citations": rag_citations if used_knowledge else [],
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
    ) -> StreamingMessage:
        """
        Initialize a StreamingMessage with metadata.

        Issue #665: Extracted from _stream_llm_response to reduce function length.
        """
        streaming_msg = StreamingMessage(type=message_type)
        streaming_msg.merge_metadata(
            {
                "model": selected_model,
                "terminal_session_id": terminal_session_id,
                "used_knowledge": used_knowledge,
                "citations": rag_citations if used_knowledge else [],
            }
        )
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

        Returns:
            Tuple of (chunk_text, new_llm_response, new_current_segment, new_type)
        """
        chunk_text = chunk_data.get("response", "")
        if not chunk_text:
            return (None, llm_response, current_segment, current_message_type)

        chunk_text = self._normalize_tool_call_text(chunk_text)
        new_llm_response = llm_response + chunk_text
        new_current_segment = current_segment + chunk_text
        new_type = self._detect_content_type(new_llm_response, current_message_type)

        return (chunk_text, new_llm_response, new_current_segment, new_type)

    def _apply_type_transition(
        self,
        complete_msg: Optional[WorkflowMessage],
        new_segment: Optional[str],
        new_type: str,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ) -> tuple:
        """
        Apply type transition and create new StreamingMessage if needed.

        Issue #665: Extracted from _stream_llm_response to reduce function length.

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
            )
            return (streaming_msg, new_segment, new_type, True, new_segment)
        return (None, None, new_type, False, None)

    def _check_tool_call_completion(
        self, llm_response: str, tool_call_completed: bool
    ) -> bool:
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
        if not tool_call_completed and _TOOL_CALL_COMPLETE_RE.search(llm_response):
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
        transition_content: Optional[str],
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
        tool_call_completed = self._check_tool_call_completion(
            llm_response, tool_call_completed
        )
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
    ) -> tuple:
        """Initialize state for streaming LLM response.

        Issue #620.
        """
        streaming_msg = self._init_streaming_message(
            "response",
            selected_model,
            terminal_session_id,
            used_knowledge,
            rag_citations,
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
        ) = self._process_chunk_and_detect_type(
            chunk_data, llm_response, current_segment, current_message_type
        )
        (
            done_result,
            should_break,
            tool_call_completed,
        ) = self._handle_tool_call_completion_check(
            chunk_data, llm_response, tool_call_completed
        )
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
    ):
        """Stream LLM response chunks. Issue #620."""
        state = self._initialize_stream_state(
            selected_model, terminal_session_id, used_knowledge, rag_citations
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
            async for should_return, should_break, yields, updated in self._iterate_chunk_results(
                params, current_state
            ):
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

        # Issue #650: Increased from 500 to 2000 for better continuation context
        max_output_len = 2000
        if len(output_text) > max_output_len:
            output_text = output_text[:max_output_len] + "\n... (output truncated)"

        return f"**Step {step_num}:** `{cmd}`\n- Status: {status}\n- Output:\n```\n{output_text}\n```"

    def _get_continuation_instructions(
        self, original_message: str, steps_completed: int
    ) -> str:
        """Get the critical instructions for continuation prompts.

        Issue #651: Enhanced instructions to prevent premature task completion.
        """
        return f"""**CRITICAL MULTI-STEP TASK INSTRUCTIONS - READ CAREFULLY:**

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
        system_prompt: str,
    ) -> str:
        """Build continuation prompt with execution results for multi-step tasks.

        Issue #651: Enhanced prompt structure for better multi-step task handling.
        """
        history_parts = [
            self._format_execution_step(i, result)
            for i, result in enumerate(execution_history, 1)
        ]
        history_text = "\n\n".join(history_parts)
        steps_completed = len(execution_history)
        instructions = self._get_continuation_instructions(
            original_message, steps_completed
        )

        return f"""{system_prompt}

---
## MULTI-STEP TASK CONTINUATION (Step {steps_completed + 1})

**Commands Already Executed ({steps_completed} step(s) completed so far):**
{history_text}

---
{instructions}"""

    def _get_llm_request_payload(
        self, selected_model: str, current_prompt: str
    ) -> dict:
        """Build LLM request payload."""
        return {
            "model": selected_model,
            "prompt": current_prompt,
            "stream": True,
            "options": {"temperature": 0.7, "top_p": 0.9, "num_ctx": 2048},
        }

    def _log_and_parse_tool_calls(
        self, llm_response: str, iteration: int
    ) -> List[Dict[str, Any]]:
        """
        Log response details and parse tool calls.

        Issue #620: Extracted from _process_single_llm_iteration.
        """
        has_tool_call_tag = "<TOOL_CALL" in llm_response or "<tool_call" in llm_response
        logger.info(
            "[Issue #651] Iteration %d: Response has TOOL_CALL tag: %s, snippet: %s",
            iteration,
            has_tool_call_tag,
            llm_response[:500].replace("\n", " "),
        )

        # Issue #716: On first iteration, defer tool execution for plan-first
        is_first_iteration = iteration == 1
        tool_calls = self._parse_tool_calls(
            llm_response, is_first_iteration=is_first_iteration
        )
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
    ):
        """Process a single LLM iteration. Yields chunks, then (llm_response, tool_calls). Issue #620."""
        import aiohttp

        payload = self._get_llm_request_payload(selected_model, current_prompt)
        llm_response = ""

        try:
            async with await http_client.post(
                ollama_endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60.0)
            ) as response:
                logger.info(
                    "[ChatWorkflowManager] Ollama response status: %s", response.status
                )
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

        tool_calls = self._log_and_parse_tool_calls(llm_response, iteration)
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
                logger.info(
                    "[Issue #654] break_loop=True signal received from respond tool"
                )
            return (True, break_loop_requested)
        return (False, False)

    def _validate_tool_message(self, tool_msg: Any) -> bool:
        """Issue #665: Extracted from _process_tool_results to reduce function length.

        Validate that tool_msg is valid and has required attributes.

        Returns:
            True if valid, False if should skip
        """
        if tool_msg is None:
            logger.warning(
                "[Issue #680] Received None from _process_tool_calls - skipping"
            )
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
            logger.info(
                "[Issue #651] Command requires approval - will wait for resolution"
            )

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
    ):
        """Issue #665: Refactored - Process tool calls and collect results.

        Issue #651: Fixed logic that incorrectly broke continuation loop.
        Issue #654: Added support for 'respond' tool with break_loop pattern.

        Yields:
            WorkflowMessage items, then (results, has_pending_approval, should_break, break_loop_requested)
        """
        new_execution_results = []
        has_pending_approval = False
        break_loop_requested = False

        async for tool_msg in self._process_tool_calls(
            tool_calls, session_id, terminal_session_id, ollama_endpoint, selected_model
        ):
            is_tuple, loop_requested = self._handle_break_loop_tuple(tool_msg)
            if is_tuple:
                break_loop_requested = loop_requested or break_loop_requested
                continue

            if not self._validate_tool_message(tool_msg):
                continue

            if self._handle_execution_summary(
                tool_msg, new_execution_results, execution_history
            ):
                continue

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

        async for item in self._process_single_llm_iteration(
            http_client,
            ctx.ollama_endpoint,
            ctx.selected_model,
            current_prompt,
            ctx.terminal_session_id,
            ctx.used_knowledge,
            ctx.rag_citations,
            iteration,
        ):
            if isinstance(item, tuple):
                llm_response, tool_calls = item
            else:
                # Don't persist streaming chunks - they're for live display only
                # The final complete response is persisted in _persist_workflow_messages
                is_streaming_chunk = hasattr(item, "metadata") and item.metadata.get(
                    "streaming", False
                )
                if not is_streaming_chunk:
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

        async for item in self._collect_llm_iteration_response(
            http_client, current_prompt, iteration, ctx
        ):
            if isinstance(item, tuple):
                llm_response, tool_calls = item
            else:
                yield item

        if llm_response is None:
            logger.warning(
                "[Issue #651] Iteration %d: No LLM response - stopping", iteration
            )
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

        async for item in self._collect_and_validate_llm_response(
            http_client, current_prompt, iteration, ctx
        ):
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

        async for item in self._collect_tool_execution_results(
            tool_calls, iteration, ctx
        ):
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

        async for item in self._yield_llm_response_and_check_stop(
            http_client, current_prompt, iteration, ctx
        ):
            if isinstance(item, tuple) and len(item) == 3:
                llm_response, tool_calls, should_stop = item
            else:
                yield item

        if should_stop:
            yield (llm_response, tool_calls, False)
            return

        should_continue = False
        async for item in self._yield_tool_results_and_decide(
            tool_calls, iteration, ctx
        ):
            if isinstance(item, bool):
                should_continue = item
            else:
                yield item

        yield (llm_response, tool_calls, should_continue)

    def _create_llm_error_message(
        self, error: Exception, workflow_messages: List[WorkflowMessage]
    ) -> WorkflowMessage:
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
        """
        logger.info(
            "[ChatWorkflowManager] Continuation iteration %d/%d",
            iteration,
            self.MAX_CONTINUATION_ITERATIONS,
        )

        llm_response = None
        should_continue = False

        async for item in self._run_continuation_iteration(
            http_client, current_prompt, iteration, ctx
        ):
            if isinstance(item, tuple) and len(item) == 3:
                llm_response, _, should_continue = item
            else:
                yield item

        yield (llm_response, should_continue)

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
            ctx.message, execution_history, ctx.system_prompt
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
                current_prompt[instructions_start : instructions_start + 1500].replace(
                    "\n", " | "
                ),
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
            llm_response, should_continue = None, False

            async for item in self._run_continuation_loop_iteration(
                http_client, current_prompt, iteration, ctx
            ):
                if isinstance(item, tuple) and len(item) == 2:
                    llm_response, should_continue = item
                else:
                    yield item

            if llm_response is None:
                logger.warning(
                    "[Issue #651] No LLM response in iteration %d - aborting", iteration
                )
                yield ([], [], None)
                return

            all_llm_responses.append(llm_response)
            self._log_iteration_complete(
                iteration,
                should_continue,
                len(all_llm_responses),
                len(execution_history),
            )

            if not should_continue:
                self._log_task_complete(iteration, len(execution_history))
                break

            current_prompt = self._build_and_log_continuation_prompt(
                ctx, execution_history
            )

        self._log_max_iterations_warning(iteration)
        yield (all_llm_responses, execution_history, None)

    async def _execute_llm_continuation_loop(
        self,
        ctx: LLMIterationContext,
    ):
        """
        Execute the multi-step LLM continuation loop.

        Issue #375: Uses LLMIterationContext to reduce parameter count from 10 to 1.
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

    async def _persist_workflow_messages(
        self,
        session_id: str,
        workflow_messages: List[WorkflowMessage],
        llm_response: str,
    ) -> None:
        """Persist WorkflowMessages and assistant response to chat history (Issue #332)."""
        from chat_history import ChatHistoryManager

        try:
            chat_mgr = ChatHistoryManager()

            # Persist all collected WorkflowMessages
            for wf_msg in workflow_messages:
                message_type = wf_msg.type

                # Skip segment_complete markers — internal stream control messages
                # with empty content that pollute history and share message_id
                # with the content message they terminate (Issue #1141).
                if message_type == "segment_complete":
                    continue

                sender = "system" if message_type == "terminal_output" else "assistant"

                await chat_mgr.add_message(
                    sender=sender,
                    text=wf_msg.content,
                    message_type=message_type,
                    raw_data=wf_msg.metadata,
                    session_id=session_id,
                )
                logger.debug(
                    "Persisted WorkflowMessage to chat history: type=%s, session=%s",
                    message_type,
                    session_id,
                )

            # NOTE: Removed duplicate llm_response persistence (#1064).
            # The per-message loop above already persists the final
            # response; a second add_message with type="llm_response"
            # created a duplicate that survived content-based dedup.
            logger.info(
                "Persisted conversation to chat history: "
                "session=%s, workflow_messages=%d",
                session_id,
                len(workflow_messages),
            )

        except Exception as persist_error:
            logger.error(
                "Failed to persist WorkflowMessages to chat history: %s",
                persist_error,
                exc_info=True,
            )

    async def _persist_user_message(self, session_id: str, message: str) -> None:
        """Persist user message immediately to prevent data loss on restart."""
        from chat_history import ChatHistoryManager

        try:
            chat_mgr = ChatHistoryManager()
            await chat_mgr.add_message(
                sender="user",
                text=message,
                message_type="default",
                session_id=session_id,
            )
            logger.debug("✅ Persisted user message immediately: session=%s", session_id)
        except Exception as persist_error:
            logger.error(
                "Failed to persist user message immediately: %s", persist_error
            )

    async def _handle_exit_intent(
        self, session_id: str, workflow_messages: List[WorkflowMessage]
    ):
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

    async def _handle_slash_command(
        self, session_id: str, message: str, workflow_messages: List[WorkflowMessage]
    ):
        """Handle slash command execution. Yields command response and persists."""
        from chat_history import ChatHistoryManager

        slash_handler = get_slash_command_handler()
        logger.info("[ChatWorkflowManager] Processing slash command: %s", message[:50])
        result = await slash_handler.execute(message)

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
        self, session, message: str, context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Prepare LLM request parameters from session and message.

        Issue #620: Extracted from _execute_llm_workflow to reduce function length.
        Issue #715: Registers user message in history before building context.

        Returns:
            Dictionary with LLM parameters. Issue #620.
        """
        self._register_user_message_in_history(session, message)

        use_knowledge = context.get("use_knowledge", True) if context else True
        llm_params = await self._prepare_llm_request_params(
            session, message, use_knowledge=use_knowledge
        )

        logger.info(
            "[ChatWorkflowManager] Initial prompt length: %d characters",
            len(llm_params["prompt"]),
        )
        return llm_params

    def _create_llm_iteration_context(
        self,
        llm_params: Dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        message: str,
        workflow_messages: List[WorkflowMessage],
    ) -> LLMIterationContext:
        """
        Create LLMIterationContext from prepared parameters.

        Issue #620: Extracted from _execute_llm_workflow to reduce function length.
        Issue #375: Uses context object to reduce parameter count.

        Returns:
            Configured LLMIterationContext. Issue #620.
        """
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
        )

    async def _execute_llm_workflow(
        self,
        session_id: str,
        session,
        message: str,
        context: Optional[Dict[str, Any]],
        terminal_session_id: str,
        workflow_messages: List[WorkflowMessage],
    ):
        """
        Execute the main LLM workflow.

        Issue #620: Refactored using Extract Method to reduce function length.
        Yields WorkflowMessages.
        """
        llm_params = await self._prepare_llm_workflow_params(session, message, context)

        ctx = self._create_llm_iteration_context(
            llm_params, session_id, terminal_session_id, message, workflow_messages
        )

        all_llm_responses = []
        async for item in self._execute_llm_continuation_loop(ctx):
            if isinstance(item, tuple) and len(item) == 3:
                all_llm_responses, _, error = item
                if error:
                    return
            else:
                yield item

        combined_response = "\n\n".join(all_llm_responses)
        await self._persist_conversation(
            session_id, session, message, combined_response
        )
        await self._persist_workflow_messages(
            session_id, workflow_messages, combined_response
        )

    @error_boundary(component="chat_workflow_manager", function="process_message")
    async def process_message(
        self, session_id: str, message: str, context: Optional[Dict[str, Any]] = None
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
            async for msg in self._handle_slash_command(
                session_id, message, workflow_messages
            ):
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

    async def process_message_stream(
        self, session_id: str, message: str, context: Optional[Dict[str, Any]] = None
    ):
        """Process a message via LangGraph StateGraph.

        Issue #1043: Replaced hand-rolled async generator with LangGraph graph
        invocation. The graph handles state management, checkpointing, and
        interrupt-based command approval natively.

        Falls back to legacy flow if LangGraph is unavailable.
        """
        try:
            async for msg in self._process_via_graph(session_id, message, context):
                yield msg
        except Exception as graph_err:
            logger.warning(
                "LangGraph flow failed, falling back to legacy: %s",
                graph_err,
            )
            async for msg in self._process_message_stream_legacy(
                session_id, message, context
            ):
                yield msg

    async def _process_via_graph(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
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

        graph_task = asyncio.create_task(
            self._run_graph_task(graph, initial_state, config, queue)
        )

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
            queue.put_nowait(
                {
                    "type": "error",
                    "content": f"Error: {exc}",
                }
            )
        finally:
            queue.put_nowait(None)

    async def _process_message_stream_legacy(
        self, session_id: str, message: str, context: Optional[Dict[str, Any]] = None
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

            async for item in self._process_special_intents(
                session_id, message, user_wants_exit, workflow_messages
            ):
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
            yield self._create_processing_error_message(
                session_id, e, workflow_messages
            )

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

        graph_task = asyncio.create_task(
            self._run_graph_task(graph, Command(resume=decision), config, queue)
        )

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
