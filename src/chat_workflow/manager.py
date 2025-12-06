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
        Used to emit proper message types for frontend filtering.

        Args:
            content: Current accumulated content
            current_type: Current detected type (maintains state across chunks)

        Returns:
            Message type: 'thought', 'planning', or 'response'
        """
        # Check for [THOUGHT] tag
        if self.THOUGHT_TAG_PATTERN.search(content):
            return "thought"

        # Check for [PLANNING] tag
        if self.PLANNING_TAG_PATTERN.search(content):
            return "planning"

        # If currently in thought/planning mode and no end tag yet, maintain type
        if current_type in ("thought", "planning"):
            # Check if corresponding end tag appeared
            if current_type == "thought" and self.THOUGHT_END_PATTERN.search(content):
                return "response"  # End of thought block
            elif (
                current_type == "planning"
                and self.PLANNING_END_PATTERN.search(content)
            ):
                return "response"  # End of planning block
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

**Original User Request:** {original_message}

**Commands Already Executed:**
{history_text}

**Instructions:** Based on the execution results above, determine the next step.
- If the task is complete, provide a comprehensive summary of all results
- If more commands are needed, generate the next TOOL_CALL
- Do NOT repeat commands that have already been executed"""

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

            # Issue #352: Multi-step task continuation loop
            execution_history = []
            iteration = 0
            all_llm_responses = []

            # Debug logging
            logger.info(
                f"[ChatWorkflowManager] Initial prompt length: "
                f"{len(current_prompt)} characters"
            )

            # Stage 3: Continuation loop for multi-step tasks (Issue #352)
            try:
                import aiohttp

                from src.utils.http_client import get_http_client
                http_client = get_http_client()

                while iteration < self.MAX_CONTINUATION_ITERATIONS:
                    iteration += 1
                    logger.info(
                        f"[ChatWorkflowManager] Continuation iteration "
                        f"{iteration}/{self.MAX_CONTINUATION_ITERATIONS}"
                    )

                    async with await http_client.post(
                        ollama_endpoint,
                        json={
                            "model": selected_model,
                            "prompt": current_prompt,
                            "stream": True,
                            "options": {
                                "temperature": 0.7,
                                "top_p": 0.9,
                                "num_ctx": 2048
                            },
                        },
                        timeout=aiohttp.ClientTimeout(total=60.0),
                    ) as response:
                        logger.info(
                            f"[ChatWorkflowManager] Ollama response status: "
                            f"{response.status}"
                        )

                        # Handle non-200 responses early (guard clause)
                        if response.status != 200:
                            logger.error(
                                f"[ChatWorkflowManager] Ollama request failed: "
                                f"{response.status}"
                            )
                            error_msg = WorkflowMessage(
                                type="error",
                                content=f"LLM service error: {response.status}",
                                metadata={"error": True},
                            )
                            workflow_messages.append(error_msg)
                            yield error_msg
                            return

                        # Stream response chunks (Issue #332 - uses helpers)
                        # Issue #351 Fix: Track current message type for thought/planning
                        llm_response = ""
                        current_message_type = "response"
                        async for line in response.content:
                            line_str = line.decode("utf-8").strip()
                            if not line_str:
                                continue

                            try:
                                chunk_data = json.loads(line_str)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse stream chunk: {e}")
                                continue

                            chunk_text = chunk_data.get("response", "")
                            if chunk_text:
                                chunk_text = self._normalize_tool_call_text(chunk_text)
                                llm_response += chunk_text
                                # Issue #351: Pass accumulated content for type detection
                                chunk_msg = self._build_chunk_message(
                                    chunk_text, selected_model, terminal_session_id,
                                    used_knowledge, rag_citations,
                                    accumulated_content=llm_response,
                                    current_type=current_message_type,
                                )
                                # Update current type for next chunk
                                current_message_type = chunk_msg.type
                                yield chunk_msg

                            if chunk_data.get("done", False):
                                break

                        logger.info(
                            f"[ChatWorkflowManager] Full LLM response length: "
                            f"{len(llm_response)} characters (iteration {iteration})"
                        )
                        all_llm_responses.append(llm_response)

                        # Stage 4: Process tool calls if present
                        tool_calls = self._parse_tool_calls(llm_response)
                        logger.info(
                            f"[ChatWorkflowManager] Parsed {len(tool_calls)} "
                            f"tool calls from response"
                        )

                        # If no tool calls, LLM has completed the task
                        if not tool_calls:
                            logger.info(
                                f"[ChatWorkflowManager] No more tool calls - "
                                f"multi-step task complete after {iteration} iteration(s)"
                            )
                            break

                        # Process tool calls and collect execution results
                        new_execution_results = []
                        async for tool_msg in self._process_tool_calls(
                            tool_calls, session_id, terminal_session_id,
                            ollama_endpoint, selected_model,
                        ):
                            # Issue #352: Capture execution summary for continuation
                            if tool_msg.type == "execution_summary":
                                new_results = tool_msg.metadata.get(
                                    "execution_results", []
                                )
                                new_execution_results.extend(new_results)
                                execution_history.extend(new_results)
                                logger.info(
                                    f"[ChatWorkflowManager] Collected "
                                    f"{len(new_results)} execution results"
                                )
                                # Don't yield execution_summary to frontend
                                continue

                            if tool_msg.type in {
                                "terminal_command", "terminal_output", "error"
                            }:
                                workflow_messages.append(tool_msg)
                                logger.debug(
                                    f"Collected WorkflowMessage: type={tool_msg.type}"
                                )
                            yield tool_msg

                        # If no execution results, break to avoid infinite loop
                        if not new_execution_results:
                            logger.warning(
                                "[ChatWorkflowManager] Tool calls found but no "
                                "execution results - breaking continuation loop"
                            )
                            break

                        # Build continuation prompt for next iteration
                        current_prompt = self._build_continuation_prompt(
                            original_message=message,
                            execution_history=execution_history,
                            system_prompt=system_prompt,
                        )
                        logger.info(
                            f"[ChatWorkflowManager] Built continuation prompt: "
                            f"{len(current_prompt)} characters"
                        )

                # Log completion
                if iteration >= self.MAX_CONTINUATION_ITERATIONS:
                    logger.warning(
                        f"[ChatWorkflowManager] Reached max continuation iterations "
                        f"({self.MAX_CONTINUATION_ITERATIONS})"
                    )

                # Stage 5: Persist conversation (use combined response)
                combined_response = "\n\n".join(all_llm_responses)
                await self._persist_conversation(
                    session_id, session, message, combined_response
                )

                # Stage 6: Persist WorkflowMessages (Issue #332 - uses helper)
                await self._persist_workflow_messages(
                    session_id, workflow_messages, combined_response
                )

            except aiohttp.ClientError as llm_error:
                logger.error(
                    f"[ChatWorkflowManager] Direct LLM call failed: {llm_error}"
                )
                error_msg = WorkflowMessage(
                    type="error",
                    content=f"Failed to connect to LLM: {str(llm_error)}",
                    metadata={"error": True},
                )
                workflow_messages.append(error_msg)
                yield error_msg

            except Exception as llm_error:
                logger.error(f"[ChatWorkflowManager] Direct LLM call failed: {llm_error}")
                error_msg = WorkflowMessage(
                    type="error",
                    content=f"Failed to connect to LLM: {str(llm_error)}",
                    metadata={"error": True},
                )
                workflow_messages.append(error_msg)
                yield error_msg

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
