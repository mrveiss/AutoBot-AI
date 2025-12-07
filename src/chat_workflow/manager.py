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
from typing import Any, Dict, List, Optional

from src.async_chat_workflow import WorkflowMessage
from src.slash_command_handler import get_slash_command_handler
from src.utils.error_boundaries import (
    error_boundary,
    get_error_boundary_manager,
)
from src.utils.redis_client import get_redis_client as get_redis_manager

from .conversation import ConversationHandlerMixin
from .llm_handler import LLMHandlerMixin
from .models import WorkflowSession
from .session_handler import SessionHandlerMixin
from .tool_handler import ToolHandlerMixin

logger = logging.getLogger(__name__)


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

    @error_boundary(component="chat_workflow_manager", function="initialize")
    async def initialize(self) -> bool:
        """Initialize the workflow manager with default workflow and async Redis."""
        try:
            async with self._lock:
                if self._initialized:
                    return True

                # Initialize Redis client for conversation history
                try:
                    self.redis_client = await get_redis_manager(
                        async_client=True, database="main"
                    )
                    logger.info("✅ Redis client initialized for conversation history")
                except Exception as redis_error:
                    logger.warning(
                        f"⚠️ Redis initialization failed: {redis_error} - "
                        f"continuing without persistence"
                    )
                    self.redis_client = None

                # Create default workflow instance
                from src.async_chat_workflow import AsyncChatWorkflow
                self.default_workflow = AsyncChatWorkflow()

                # Initialize knowledge service for RAG (Issue #249)
                try:
                    from backend.knowledge_factory import get_knowledge_base_async
                    from backend.services.rag_service import RAGService
                    from src.services.chat_knowledge_service import ChatKnowledgeService

                    # Get knowledge base instance (async version)
                    kb = await get_knowledge_base_async()
                    if kb:
                        rag_service = RAGService(kb)
                        await rag_service.initialize()
                        self.knowledge_service = ChatKnowledgeService(rag_service)
                        logger.info("✅ Knowledge service initialized for RAG")
                    else:
                        logger.warning(
                            "⚠️ Knowledge base not available - RAG disabled"
                        )
                except Exception as kb_error:
                    logger.warning(
                        f"⚠️ Knowledge service initialization failed: {kb_error} - "
                        f"continuing without RAG"
                    )
                    self.knowledge_service = None

                self._initialized = True

                logger.info("✅ ChatWorkflowManager initialized successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize ChatWorkflowManager: {e}")
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
        text = re.sub(r"<TOOL_\s+CALL", "<TOOL_CALL", text)
        text = re.sub(r"</TOOL_\s+CALL>", "</TOOL_CALL>", text)
        return text

    def _detect_content_type(
        self, content: str, current_type: str = "response"
    ) -> str:
        """
        Detect message type from content tags (Issue #351 Fix).

        Checks for [THOUGHT] and [PLANNING] tags to determine message type.
        Uses position-based detection to correctly identify when blocks are
        opened vs closed (e.g., [THOUGHT]...[/THOUGHT] means block is closed).

        Args:
            content: Current accumulated content
            current_type: Current detected type (maintains state across chunks)

        Returns:
            Message type: 'thought', 'planning', or 'response'
        """
        # Find positions of all tags (use last occurrence for each)
        thought_start = -1
        thought_end = -1
        planning_start = -1
        planning_end = -1

        # Find last occurrence of each tag
        for match in self.THOUGHT_TAG_PATTERN.finditer(content):
            thought_start = match.start()
        for match in self.THOUGHT_END_PATTERN.finditer(content):
            thought_end = match.start()
        for match in self.PLANNING_TAG_PATTERN.finditer(content):
            planning_start = match.start()
        for match in self.PLANNING_END_PATTERN.finditer(content):
            planning_end = match.start()

        # Check thought block status
        if thought_start >= 0:
            # Has [THOUGHT] tag
            if thought_end > thought_start:
                # Block is closed: [THOUGHT]...[/THOUGHT]
                # Check if we're inside a planning block after thought closed
                if planning_start > thought_end and planning_end < planning_start:
                    return "planning"
                return "response"
            else:
                # Block is open: [THOUGHT]... (no closing tag yet)
                return "thought"

        # Check planning block status
        if planning_start >= 0:
            # Has [PLANNING] tag
            if planning_end > planning_start:
                # Block is closed: [PLANNING]...[/PLANNING]
                return "response"
            else:
                # Block is open: [PLANNING]... (no closing tag yet)
                return "planning"

        # No tags found - maintain current type if in block, else response
        if current_type in ("thought", "planning"):
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
        if detected_type in ("thought", "planning"):
            logger.info(
                f"[Issue #352] Detected message type: {detected_type} "
                f"(accumulated len: {len(accumulated_content)})"
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
            logger.error(f"Failed to parse stream chunk: {e}")
            return None

    async def _stream_llm_response(
        self,
        response,
        selected_model: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
    ):
        """Stream LLM response chunks and yield WorkflowMessages (Issue #315).

        Issue #352: Now splits stream into separate messages when type changes
        (thought → planning → response), enabling proper UI filtering.

        Args:
            response: aiohttp response object with streaming content
            selected_model: Model name for metadata
            terminal_session_id: Terminal session ID
            used_knowledge: Whether knowledge base was used
            rag_citations: RAG citations if any

        Yields:
            Tuple of (chunk_message, accumulated_response, is_done, is_segment_complete)
        """
        llm_response = ""  # Full response for tool parsing
        current_segment = ""  # Current message segment content
        current_message_type = "response"
        import uuid
        current_message_id = str(uuid.uuid4())  # Unique ID for message grouping

        async for line in response.content:
            chunk_data = self._parse_stream_chunk(line)
            if not chunk_data:
                continue

            chunk_text = chunk_data.get("response", "")
            if chunk_text:
                chunk_text = self._normalize_tool_call_text(chunk_text)
                llm_response += chunk_text
                current_segment += chunk_text

                # Detect new type based on accumulated content
                new_type = self._detect_content_type(llm_response, current_message_type)

                # Issue #352: When type changes, complete current segment and start new one
                if new_type != current_message_type and current_message_type != "response":
                    # Signal that current segment is complete
                    logger.info(
                        f"[Issue #352] Message type transition: {current_message_type} → {new_type}"
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
                    yield (complete_msg, llm_response, False, True)

                    # Start new segment with new ID
                    current_message_id = str(uuid.uuid4())
                    current_segment = ""
                    current_message_type = new_type

                elif new_type != current_message_type:
                    # Type changed from response to thought/planning
                    current_message_type = new_type
                    current_message_id = str(uuid.uuid4())
                    current_segment = chunk_text  # Start fresh segment

                # Build chunk message with segment tracking
                chunk_msg = WorkflowMessage(
                    type=current_message_type,
                    content=chunk_text,
                    metadata={
                        "message_type": "llm_response_chunk",
                        "model": selected_model,
                        "streaming": True,
                        "terminal_session_id": terminal_session_id,
                        "used_knowledge": used_knowledge,
                        "citations": rag_citations if used_knowledge else [],
                        "message_id": current_message_id,  # Issue #352: Track which message this belongs to
                    },
                )
                yield (chunk_msg, llm_response, False, False)

            if chunk_data.get("done", False):
                # Issue #352: Log if thought/planning tags were detected in full response
                has_thought = "[THOUGHT]" in llm_response
                has_planning = "[PLANNING]" in llm_response
                if has_thought or has_planning:
                    logger.info(
                        f"[Issue #352] LLM response contains: "
                        f"THOUGHT={has_thought}, PLANNING={has_planning}"
                    )
                else:
                    logger.debug(
                        f"[Issue #352] LLM response (no thought/planning tags): "
                        f"{llm_response[:200]}..."
                    )
                yield (None, llm_response, True, False)
                break

    def _build_continuation_prompt(
        self,
        original_message: str,
        execution_history: List[Dict[str, Any]],
        system_prompt: str,
    ) -> str:
        """
        Build continuation prompt with execution results for multi-step tasks.

        Issue #352: This enables the LLM to continue multi-step tasks by
        providing context about what commands have already been executed.

        Args:
            original_message: User's original request
            execution_history: List of execution results from previous steps
            system_prompt: Original system prompt

        Returns:
            Formatted continuation prompt
        """
        history_parts = []
        for i, result in enumerate(execution_history, 1):
            cmd = result.get("command", "unknown")
            stdout = result.get("stdout", "").strip()
            stderr = result.get("stderr", "").strip()
            status = result.get("status", "unknown")

            output_text = stdout if stdout else "(no output)"
            if stderr:
                output_text += f"\nStderr: {stderr}"

            history_parts.append(
                f"**Step {i}:** `{cmd}`\n"
                f"- Status: {status}\n"
                f"- Output:\n```\n{output_text[:500]}\n```"
            )

        history_text = "\n\n".join(history_parts)

        return f"""{system_prompt}

---
## MULTI-STEP TASK CONTINUATION

**Original User Request:** {original_message}

**Commands Already Executed ({len(execution_history)} step(s) completed):**
{history_text}

---
**CRITICAL INSTRUCTIONS - You MUST follow these exactly:**

1. **Analyze the original request**: Does "{original_message}" require more commands to be fully satisfied?

2. **If MORE commands are needed** (task NOT complete):
   - Generate the NEXT `<TOOL_CALL>` immediately
   - Do NOT summarize yet - continue executing
   - Do NOT repeat commands already executed above

3. **If task IS complete** (all steps done):
   - Provide a comprehensive summary of ALL results
   - Do NOT generate any TOOL_CALL
   - Explain what was accomplished

**Remember**: You're in a continuation loop. Either generate the next TOOL_CALL or provide the final summary. Nothing else."""

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
        """Process a single LLM iteration (Issue #315: extracted for depth reduction).

        Yields:
            WorkflowMessage chunks, then final tuple (llm_response, tool_calls)
        """
        import aiohttp

        async with await http_client.post(
            ollama_endpoint,
            json={
                "model": selected_model,
                "prompt": current_prompt,
                "stream": True,
                "options": {"temperature": 0.7, "top_p": 0.9, "num_ctx": 2048},
            },
            timeout=aiohttp.ClientTimeout(total=60.0),
        ) as response:
            logger.info(f"[ChatWorkflowManager] Ollama response status: {response.status}")

            if response.status != 200:
                logger.error(f"[ChatWorkflowManager] Ollama request failed: {response.status}")
                yield WorkflowMessage(
                    type="error",
                    content=f"LLM service error: {response.status}",
                    metadata={"error": True},
                )
                yield (None, None)  # Signal error
                return

            llm_response = ""
            # Issue #352: Now yields 4 values - (chunk_msg, llm_response, is_done, is_segment_complete)
            async for chunk_msg, llm_response, is_done, is_segment_complete in self._stream_llm_response(
                response, selected_model, terminal_session_id, used_knowledge, rag_citations
            ):
                if chunk_msg:
                    yield chunk_msg
                    # Issue #352: Signal segment complete to frontend for message splitting
                    if is_segment_complete:
                        logger.debug(f"[Issue #352] Segment complete signal sent")
                if is_done:
                    break

            logger.info(
                f"[ChatWorkflowManager] Full LLM response length: "
                f"{len(llm_response)} characters (iteration {iteration})"
            )

            tool_calls = self._parse_tool_calls(llm_response)
            logger.info(
                f"[Issue #352] Iteration {iteration}: Parsed {len(tool_calls)} tool calls"
            )

            yield (llm_response, tool_calls)

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
        """Process tool calls and collect results (Issue #315: extracted).

        Yields:
            WorkflowMessage items

        Returns:
            Tuple of (new_execution_results, should_break)
        """
        new_execution_results = []

        async for tool_msg in self._process_tool_calls(
            tool_calls, session_id, terminal_session_id, ollama_endpoint, selected_model
        ):
            if tool_msg.type == "execution_summary":
                new_results = tool_msg.metadata.get("execution_results", [])
                new_execution_results.extend(new_results)
                execution_history.extend(new_results)
                logger.info(f"[ChatWorkflowManager] Collected {len(new_results)} execution results")
                continue

            if tool_msg.type in {"terminal_command", "terminal_output", "error"}:
                workflow_messages.append(tool_msg)
            yield tool_msg

        yield (new_execution_results, not new_execution_results)

    async def _run_continuation_iteration(
        self,
        http_client,
        ollama_endpoint: str,
        selected_model: str,
        current_prompt: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        iteration: int,
        session_id: str,
        execution_history: List[Dict[str, Any]],
        workflow_messages: List[WorkflowMessage],
    ):
        """Run a single continuation iteration (Issue #315: extracted for depth reduction).

        This helper processes one LLM call and any resulting tool calls,
        keeping the main loop at lower nesting depth.

        Yields:
            WorkflowMessage items for streaming

        Returns (via final tuple yield):
            (llm_response, tool_calls, should_continue)
            - llm_response: The LLM response text (None on error)
            - tool_calls: Parsed tool calls list
            - should_continue: Whether to continue the loop
        """
        # Process LLM iteration
        llm_response = None
        tool_calls = None

        async for item in self._process_single_llm_iteration(
            http_client, ollama_endpoint, selected_model, current_prompt,
            terminal_session_id, used_knowledge, rag_citations, iteration
        ):
            if isinstance(item, tuple):
                llm_response, tool_calls = item
            else:
                workflow_messages.append(item)
                yield item

        # Check for error condition
        if llm_response is None:
            yield (None, None, False)
            return

        # If no tool calls, task is complete
        if not tool_calls:
            logger.info(
                f"[Issue #352] No more tool calls - task complete "
                f"after {iteration} iteration(s)"
            )
            yield (llm_response, tool_calls, False)
            return

        # Process tool calls
        should_break = False
        async for item in self._process_tool_results(
            tool_calls, session_id, terminal_session_id,
            ollama_endpoint, selected_model,
            execution_history, workflow_messages
        ):
            if isinstance(item, tuple):
                _, should_break = item
            else:
                yield item

        if should_break:
            logger.warning("[Issue #352] No execution results - stopping continuation")
            yield (llm_response, tool_calls, False)
            return

        # Continue with next iteration
        yield (llm_response, tool_calls, True)

    async def _execute_llm_continuation_loop(
        self,
        ollama_endpoint: str,
        selected_model: str,
        initial_prompt: str,
        system_prompt: str,
        terminal_session_id: str,
        used_knowledge: bool,
        rag_citations: List[Dict[str, Any]],
        session_id: str,
        message: str,
        workflow_messages: List[WorkflowMessage],
    ):
        """Execute the multi-step LLM continuation loop (Issue #315: depth reduction).

        This helper encapsulates the entire Stage 3 continuation loop, keeping
        the main process_message_stream at reduced nesting depth.

        Yields:
            WorkflowMessage items for streaming

        Returns (via final tuple yield):
            (all_llm_responses, execution_history, error_message or None)
        """
        import aiohttp

        from src.utils.http_client import get_http_client

        execution_history = []
        all_llm_responses = []
        current_prompt = initial_prompt
        iteration = 0

        try:
            http_client = get_http_client()

            while iteration < self.MAX_CONTINUATION_ITERATIONS:
                iteration += 1
                logger.info(
                    f"[ChatWorkflowManager] Continuation iteration "
                    f"{iteration}/{self.MAX_CONTINUATION_ITERATIONS}"
                )

                # Use helper for single iteration
                llm_response = None
                should_continue = False

                async for item in self._run_continuation_iteration(
                    http_client, ollama_endpoint, selected_model, current_prompt,
                    terminal_session_id, used_knowledge, rag_citations, iteration,
                    session_id, execution_history, workflow_messages
                ):
                    if isinstance(item, tuple) and len(item) == 3:
                        llm_response, _, should_continue = item
                    else:
                        yield item

                if llm_response is None:
                    yield ([], [], None)  # Error occurred
                    return

                all_llm_responses.append(llm_response)

                if not should_continue:
                    break

                # Build continuation prompt for next iteration
                current_prompt = self._build_continuation_prompt(
                    original_message=message,
                    execution_history=execution_history,
                    system_prompt=system_prompt,
                )
                logger.info(
                    f"[Issue #352] Continuation prompt built: {len(current_prompt)} chars"
                )

            # Log completion
            if iteration >= self.MAX_CONTINUATION_ITERATIONS:
                logger.warning(
                    f"[ChatWorkflowManager] Reached max continuation iterations "
                    f"({self.MAX_CONTINUATION_ITERATIONS})"
                )

            yield (all_llm_responses, execution_history, None)

        except aiohttp.ClientError as llm_error:
            logger.error(f"[ChatWorkflowManager] Direct LLM call failed: {llm_error}")
            error_msg = WorkflowMessage(
                type="error",
                content=f"Failed to connect to LLM: {str(llm_error)}",
                metadata={"error": True},
            )
            workflow_messages.append(error_msg)
            yield error_msg
            yield (all_llm_responses, execution_history, error_msg)

        except Exception as llm_error:
            logger.error(f"[ChatWorkflowManager] Direct LLM call failed: {llm_error}")
            error_msg = WorkflowMessage(
                type="error",
                content=f"Failed to connect to LLM: {str(llm_error)}",
                metadata={"error": True},
            )
            workflow_messages.append(error_msg)
            yield error_msg
            yield (all_llm_responses, execution_history, error_msg)

    async def _persist_workflow_messages(
        self,
        session_id: str,
        workflow_messages: List[WorkflowMessage],
        llm_response: str,
    ) -> None:
        """Persist WorkflowMessages and assistant response to chat history (Issue #332)."""
        from src.chat_history import ChatHistoryManager

        try:
            chat_mgr = ChatHistoryManager()

            # Persist all collected WorkflowMessages
            for wf_msg in workflow_messages:
                message_type = wf_msg.type
                sender = "system" if message_type == "terminal_output" else "assistant"

                await chat_mgr.add_message(
                    sender=sender,
                    text=wf_msg.content,
                    message_type=message_type,
                    raw_data=wf_msg.metadata,
                    session_id=session_id,
                )
                logger.debug(
                    f"Persisted WorkflowMessage to chat history: "
                    f"type={message_type}, session={session_id}"
                )

            # Persist final assistant response
            await chat_mgr.add_message(
                sender="assistant",
                text=llm_response,
                message_type="llm_response",
                session_id=session_id,
            )
            logger.info(
                f"✅ Persisted complete conversation to chat history: "
                f"session={session_id}, workflow_messages={len(workflow_messages)}"
            )

        except Exception as persist_error:
            logger.error(
                f"Failed to persist WorkflowMessages to chat history: {persist_error}",
                exc_info=True,
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

    async def process_message_stream(
        self, session_id: str, message: str, context: Optional[Dict[str, Any]] = None
    ):
        """
        Process a message through the workflow system as an async generator (for streaming).

        This refactored version delegates to specialized helper methods for each stage
        of the workflow, improving maintainability and testability.

        Now also persists WorkflowMessages to chat history to fix approval workflow persistence.
        """
        # Import ChatHistoryManager for message persistence
        from src.chat_history import ChatHistoryManager

        # Collect all workflow messages for persistence
        workflow_messages = []

        try:
            # Stage 1: Initialize session and check for exit intent
            session, terminal_session_id, user_wants_exit = (
                await self._initialize_chat_session(session_id, message)
            )

            # CRITICAL: Persist user message IMMEDIATELY at start to prevent data loss on restart
            # This ensures user's question is saved even if backend crashes during processing
            try:
                chat_mgr = ChatHistoryManager()
                await chat_mgr.add_message(
                    sender="user",
                    text=message,
                    message_type="default",
                    session_id=session_id,
                )
                logger.debug(
                    f"✅ Persisted user message immediately: session={session_id}"
                )
            except Exception as persist_error:
                logger.error(
                    f"Failed to persist user message immediately: {persist_error}"
                )

            if user_wants_exit:
                logger.info(
                    f"[ChatWorkflowManager] User explicitly requested to exit "
                    f"conversation: {session_id}"
                ),
                exit_msg = WorkflowMessage(
                    type="response",
                    content=(
                        "Goodbye! Feel free to return anytime if you need assistance. Take"
                        "care!"
                    ),
                    metadata={
                        "message_type": "exit_acknowledgment",
                        "exit_detected": True,
                    },
                )
                workflow_messages.append(exit_msg)
                yield exit_msg

                # Persist exit response (user message already persisted above)
                try:
                    chat_mgr = ChatHistoryManager()
                    await chat_mgr.add_message(
                        sender="assistant",
                        text=exit_msg.content,
                        message_type="exit_acknowledgment",
                        session_id=session_id,
                    )
                except Exception as persist_error:
                    logger.error(f"Failed to persist exit message: {persist_error}")

                return

            # Stage 1.5: Check for slash commands (/docs, /help, /status) - Issue #166
            slash_handler = get_slash_command_handler()
            if slash_handler.is_slash_command(message):
                logger.info(
                    f"[ChatWorkflowManager] Processing slash command: {message[:50]}"
                )
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

                # Persist slash command response
                try:
                    chat_mgr = ChatHistoryManager()
                    await chat_mgr.add_message(
                        sender="assistant",
                        text=result.content,
                        message_type="slash_command",
                        session_id=session_id,
                    )
                except Exception as persist_error:
                    logger.error(
                        f"Failed to persist slash command response: {persist_error}"
                    )

                return

            # Stage 2: Prepare LLM request parameters (includes RAG knowledge retrieval)
            # Issue #249: Extract use_knowledge from context (frontend toggle)
            use_knowledge = context.get("use_knowledge", True) if context else True
            llm_params = await self._prepare_llm_request_params(
                session, message, use_knowledge=use_knowledge
            )
            ollama_endpoint = llm_params["endpoint"]
            selected_model = llm_params["model"]
            current_prompt = llm_params["prompt"]
            system_prompt = llm_params.get("system_prompt", "")  # Issue #352
            rag_citations = llm_params.get("citations", [])  # Issue #249: RAG citations
            used_knowledge = llm_params.get("used_knowledge", False)

            # Debug logging
            logger.info(
                f"[ChatWorkflowManager] Initial prompt length: "
                f"{len(current_prompt)} characters"
            )

            # Stage 3: Continuation loop for multi-step tasks (Issue #352)
            # Issue #315: Extracted to helper for reduced nesting depth
            all_llm_responses = []
            async for item in self._execute_llm_continuation_loop(
                ollama_endpoint, selected_model, current_prompt, system_prompt,
                terminal_session_id, used_knowledge, rag_citations,
                session_id, message, workflow_messages
            ):
                if isinstance(item, tuple) and len(item) == 3:
                    all_llm_responses, _, error = item
                    if error:
                        return  # Error was already yielded by helper
                else:
                    yield item

            # Stage 5: Persist conversation (use combined response)
            combined_response = "\n\n".join(all_llm_responses)
            await self._persist_conversation(
                session_id, session, message, combined_response
            )

            # Stage 6: Persist WorkflowMessages (Issue #332 - uses helper)
            await self._persist_workflow_messages(
                session_id, workflow_messages, combined_response
            )

        except Exception as e:
            logger.error(
                f"❌ Error processing message for session {session_id}: {e}",
                exc_info=True,
            )
            # Yield error message

            error_msg = WorkflowMessage(
                type="error",
                content=f"Error processing message: {str(e)}",
                metadata={"error": True, "session_id": session_id},
            )
            workflow_messages.append(error_msg)
            yield error_msg

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
                    f"✅ ChatWorkflowManager shutdown complete, cleaned up {session_count} sessions"
                )

        except Exception as e:
            logger.error(f"❌ Error during ChatWorkflowManager shutdown: {e}")
