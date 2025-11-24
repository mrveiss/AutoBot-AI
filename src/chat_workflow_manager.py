# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Workflow Manager - Centralized Chat Workflow Orchestration

This module provides a centralized manager for chat workflows, integrating
with the existing async chat workflow system and providing a unified interface
for the FastAPI application.

Key Features:
- Integration with async_chat_workflow
- Centralized workflow state management
- Redis-backed conversation history persistence
- Error handling and recovery
- Performance monitoring
- Session management
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from backend.conversation_context import (
    ConversationContext,
    ConversationContextAnalyzer,
)
from backend.conversation_safety import (
    ConversationSafetyGuards,
    SafetyCheckResult,
)
from backend.dependencies import global_config_manager

# Import comprehensive intent classification system - Issue #159
from backend.intent_classifier import (
    ConversationIntent,
    IntentClassification,
    IntentClassifier,
)
from src.async_chat_workflow import AsyncChatWorkflow, MessageType, WorkflowMessage

# Import intent detection functions - Phase 2 Refactoring
from src.chat_intent_detector import (
    detect_exit_intent,
    detect_user_intent,
    select_context_prompt,
)
from src.constants.network_constants import NetworkConstants
from src.prompt_manager import get_prompt
from src.utils.error_boundaries import (
    ErrorCategory,
    ErrorContext,
    error_boundary,
    get_error_boundary_manager,
)
from src.utils.redis_client import get_redis_client as get_redis_manager

logger = logging.getLogger(__name__)

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class WorkflowSession:
    """Represents an active chat workflow session"""

    session_id: str
    workflow: AsyncChatWorkflow
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(
        default_factory=list
    )  # Track conversation context


class ChatWorkflowManager:
    """
    Centralized manager for chat workflows across the application.

    Manages workflow sessions, provides unified interface, and handles
    lifecycle management for chat workflows.
    """

    def __init__(self):
        """Initialize the chat workflow manager."""
        self.sessions: Dict[str, WorkflowSession] = {}
        self.default_workflow: Optional[AsyncChatWorkflow] = None
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

        logger.info("ChatWorkflowManager initialized")

    def _init_terminal_tool(self):
        """Initialize terminal tool for command execution."""
        try:
            import backend.api.agent_terminal as agent_terminal_api
            from src.tools.terminal_tool import TerminalTool

            # CRITICAL: Access the global singleton instance directly
            # This ensures sessions created here are visible to the approval API
            if agent_terminal_api._agent_terminal_service_instance is None:
                from backend.services.agent_terminal_service import AgentTerminalService

                # Pass self to prevent circular initialization loop
                agent_terminal_api._agent_terminal_service_instance = (
                    AgentTerminalService(chat_workflow_manager=self)
                )
                logger.info("Initialized global AgentTerminalService singleton")

            agent_service = agent_terminal_api._agent_terminal_service_instance
            self.terminal_tool = TerminalTool(agent_terminal_service=agent_service)
            logger.info("Terminal tool initialized successfully with singleton service")
        except Exception as e:
            logger.error(f"Failed to initialize terminal tool: {e}")
            self.terminal_tool = None

    def _parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response using XML-style markers.

        Supports both uppercase and lowercase tags, and handles HTML entities.

        Args:
            text: LLM response text

        Returns:
            List of tool call dictionaries
        """
        import html
        import re

        logger.debug(
            f"[_parse_tool_calls] Searching for TOOL_CALL markers in text of length {len(text)}"
        )

        # Decode HTML entities (e.g., &quot; -> ")
        text = html.unescape(text)

        has_tool_call = ('<TOOL_CALL' in text) or ('<tool_call' in text)
        logger.debug(
            f"[_parse_tool_calls] Checking if '<TOOL_CALL' or "
            f"'<tool_call' exists in text: {has_tool_call}"
        )

        tool_calls = []
        # Match both single and double quotes, and both TOOL_CALL and tool_call (case-insensitive)
        # Format: <TOOL_CALL name="..." params='...' OR params="...">...</TOOL_CALL>
        pattern = r'<tool_call\s+name="([^"]+)"\s+params=(["\'])({[^}]+})\2>([^<]*)</tool_call>'

        logger.debug(f"[_parse_tool_calls] Using regex pattern: {pattern}")

        matches = re.finditer(pattern, text, re.IGNORECASE)
        match_count = 0
        for match in matches:
            match_count += 1
            tool_name = match.group(1)
            params_str = match.group(
                3
            )  # Group 2 is the quote character, group 3 is the JSON
            description = match.group(4)

            try:
                import json

                params = json.loads(params_str)
                tool_calls.append(
                    {"name": tool_name, "params": params, "description": description}
                )
                logger.debug(
                    f"[_parse_tool_calls] Found TOOL_CALL #{match_count}: "
                    f"name={tool_name}, params={params}"
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool call params: {e}")
                logger.error(f"Params string was: {params_str}")
                continue

        logger.info(
            f"[_parse_tool_calls] Total matches found: {match_count}, "
            f"successfully parsed: {len(tool_calls)}"
        )
        return tool_calls

    async def _execute_terminal_command(
        self, session_id: str, command: str, host: str = "main", description: str = ""
    ) -> Dict[str, Any]:
        """
        Execute terminal command via terminal tool.

        Args:
            session_id: Chat session ID
            command: Command to execute
            host: Target host
            description: Command description

        Returns:
            Execution result
        """
        if not self.terminal_tool:
            return {"status": "error", "error": "Terminal tool not available"}

        # Ensure terminal session exists for this conversation
        if not self.terminal_tool.active_sessions.get(session_id):
            # Create session
            session_result = await self.terminal_tool.create_session(
                agent_id=f"chat_agent_{session_id}",
                conversation_id=session_id,
                agent_role="chat_agent",
                host=host,
            )

            if session_result.get("status") != "success":
                return session_result

        # Execute command
        result = await self.terminal_tool.execute_command(
            conversation_id=session_id, command=command, description=description
        )

        return result

    def _get_conversation_key(self, session_id: str) -> str:
        """Generate Redis key for conversation history."""
        return f"chat:conversation:{session_id}"

    async def _load_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from Redis (short-term) or file (long-term)."""
        try:
            # Try Redis first (fast access for recent conversations) with 2s timeout
            if self.redis_client is not None:
                key = self._get_conversation_key(session_id)
                try:
                    history_json = await asyncio.wait_for(
                        self.redis_client.get(key), timeout=2.0
                    )

                    if history_json:
                        logger.debug(
                            f"Loaded conversation history from Redis for session {session_id}"
                        )
                        return json.loads(history_json)

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Redis get timeout after 2s for session {session_id}, falling back to file"
                    )
                    # Fall through to file-based fallback

            # Fall back to file-based transcript (long-term storage)
            history = await self._load_transcript(session_id)
            if history:
                logger.debug(
                    f"Loaded conversation history from file for session {session_id}"
                )
                # Repopulate Redis cache (non-blocking, fire-and-forget)
                if self.redis_client is not None:
                    asyncio.create_task(
                        self._save_conversation_history(session_id, history)
                    )

            return history

        except Exception as e:
            logger.error(f"Failed to load conversation history: {e}")
            return []

    async def _save_conversation_history(
        self, session_id: str, history: List[Dict[str, str]]
    ):
        """Save conversation history to Redis with TTL."""
        try:
            if self.redis_client is None:
                return

            key = self._get_conversation_key(session_id)
            history_json = json.dumps(history)

            # Save with 24-hour expiration and 2s timeout
            try:
                await asyncio.wait_for(
                    self.redis_client.set(
                        key, history_json, ex=self.conversation_history_ttl
                    ),
                    timeout=2.0,
                )
                logger.debug(
                    f"Saved conversation history for session {session_id} to Redis"
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Redis set timeout after 2s for session {session_id} - data may not be cached"
                )

        except Exception as e:
            logger.error(f"Failed to save conversation history to Redis: {e}")

    def _get_transcript_path(self, session_id: str) -> Path:
        """Get file path for conversation transcript."""
        return Path(self.transcript_dir) / f"{session_id}.json"

    async def _append_to_transcript(
        self, session_id: str, user_message: str, assistant_message: str
    ):
        """Append message exchange to long-term transcript file (async with aiofiles)."""
        try:
            # Ensure transcript directory exists
            transcript_dir = Path(self.transcript_dir)
            transcript_dir.mkdir(parents=True, exist_ok=True)

            transcript_path = self._get_transcript_path(session_id)

            # Load existing transcript or create new (async read with timeout)
            if transcript_path.exists():
                try:
                    # Open file first, then apply timeout to read operation
                    async with aiofiles.open(
                        transcript_path, "r", encoding="utf-8"
                    ) as f:
                        content = await asyncio.wait_for(f.read(), timeout=5.0)
                        transcript = json.loads(content)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"File read timeout after 5s for {transcript_path}, creating new transcript"
                    ),
                    transcript = {
                        "session_id": session_id,
                        "created_at": datetime.now().isoformat(),
                        "messages": [],
                    }
            else:
                transcript = {
                    "session_id": session_id,
                    "created_at": datetime.now().isoformat(),
                    "messages": [],
                }

            # Append new exchange
            transcript["messages"].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "user": user_message,
                    "assistant": assistant_message,
                }
            )

            transcript["updated_at"] = datetime.now().isoformat()
            transcript["message_count"] = len(transcript["messages"])

            # Atomic write pattern: write to temp file then rename (with timeout)
            temp_path = transcript_path.with_suffix(".tmp")
            try:
                # Open file first, then apply timeout to write operation
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await asyncio.wait_for(
                        f.write(json.dumps(transcript, indent=2, ensure_ascii=False)),
                        timeout=5.0,
                    )

                # Atomic rename (sync operation, very fast)
                await asyncio.to_thread(temp_path.rename, transcript_path)

                logger.debug(
                    f"Appended to transcript for session {session_id} "
                    f"({transcript['message_count']} total messages)"
                )

            except asyncio.TimeoutError:
                logger.warning(f"File write timeout after 5s for {transcript_path}")
                # Clean up temp file if it exists
                if temp_path.exists():
                    temp_path.unlink()

        except Exception as e:
            logger.error(f"Failed to append to transcript file: {e}")

    async def _load_transcript(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from transcript file (async with aiofiles)."""
        try:
            transcript_path = self._get_transcript_path(session_id)

            if not transcript_path.exists():
                return []

            # Async file read with timeout
            try:
                # Open file first, then apply timeout to read operation
                async with aiofiles.open(transcript_path, "r", encoding="utf-8") as f:
                    content = await asyncio.wait_for(f.read(), timeout=5.0)
                    transcript = json.loads(content)

                # Convert to simple history format (last 10 messages)
                messages = transcript.get("messages", [])[-10:]
                return [
                    {"user": msg["user"], "assistant": msg["assistant"]}
                    for msg in messages
                ]

            except asyncio.TimeoutError:
                logger.warning(
                    f"File read timeout after 5s for {transcript_path}, returning empty history"
                )
                return []

        except Exception as e:
            logger.error(f"Failed to load transcript file: {e}")
            return []

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
                self.default_workflow = AsyncChatWorkflow()
                self._initialized = True

                logger.info("✅ ChatWorkflowManager initialized successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize ChatWorkflowManager: {e}")
            return False

    @error_boundary(component="chat_workflow_manager", function="get_or_create_session")
    async def get_or_create_session(self, session_id: str) -> WorkflowSession:
        """Get existing session or create new one, loading history from Redis."""
        async with self._lock:
            if session_id not in self.sessions:
                # Create new workflow for this session
                workflow = AsyncChatWorkflow()

                # Load conversation history from Redis
                conversation_history = await self._load_conversation_history(session_id)

                self.sessions[session_id] = WorkflowSession(
                    session_id=session_id,
                    workflow=workflow,
                    conversation_history=conversation_history,
                )

                logger.info(
                    f"Created new workflow session: {session_id} with "
                    f"{len(conversation_history)} messages from history"
                )

            # Update last activity
            self.sessions[session_id].last_activity = time.time()
            return self.sessions[session_id]

    @error_boundary(component="chat_workflow_manager", function="process_message")
    async def process_message(
        self, session_id: str, message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[WorkflowMessage]:
        """Process a message through the workflow system and return all messages."""
        messages = []
        async for msg in self.process_message_stream(session_id, message, context):
            messages.append(msg)
        return messages

    def _convert_conversation_history_format(
        self, history: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Convert conversation history from storage format to classification format.

        Storage format: [{"user": "msg", "assistant": "response"}, ...]
        Classification format: [{"role": "user", "content": "msg"},
                               {"role": "assistant", "content": "response"}, ...]

        Args:
            history: Conversation history in storage format

        Returns:
            List of messages in role/content format for intent classification

        Related Issue: #159 - Intent Classification System
        """
        converted = []
        for exchange in history:
            # Add user message
            if "user" in exchange:
                converted.append({"role": "user", "content": exchange["user"]})
            # Add assistant message
            if "assistant" in exchange:
                converted.append(
                    {"role": "assistant", "content": exchange["assistant"]}
                )
        return converted

    async def _initialize_chat_session(self, session_id: str, message: str) -> tuple:
        """
        Initialize session and terminal, detect exit intent.

        Args:
            session_id: Session identifier
            message: User message to check for exit intent

        Returns:
            Tuple of (session, terminal_session_id, should_exit)
        """
        logger.debug(
            f"[ChatWorkflowManager] Starting process_message_stream for session={session_id}"
        )
        logger.debug(f"[ChatWorkflowManager] Message: {message[:100]}...")

        session = await self.get_or_create_session(session_id)
        session.message_count += 1
        logger.debug(
            f"[ChatWorkflowManager] Session message_count: {session.message_count}"
        )

        # Comprehensive intent classification with safety guards (Issue #159)
        # Convert conversation history to classification format
        conversation_history_formatted = self._convert_conversation_history_format(
            session.conversation_history
        )

        # Initialize classifiers
        intent_classifier = IntentClassifier()
        context_analyzer = ConversationContextAnalyzer()
        safety_guards = ConversationSafetyGuards()

        # Classify intent
        classification: IntentClassification = intent_classifier.classify(
            message, conversation_history_formatted
        )

        # Analyze conversation context
        context: ConversationContext = context_analyzer.analyze(
            conversation_history_formatted, message
        )

        # Apply safety guards
        safety_check: SafetyCheckResult = safety_guards.check(classification, context)

        # Determine if conversation should end
        user_wants_exit = False
        if (
            classification.intent == ConversationIntent.END
            and safety_check.is_safe_to_end
        ):
            user_wants_exit = True
            logger.info(
                f"User wants to exit conversation - Intent: {classification.intent.value}, "
                f"Confidence: {classification.confidence:.2f}, Reason: {classification.reasoning}"
            )
        elif (
            classification.intent == ConversationIntent.END
            and not safety_check.is_safe_to_end
        ):
            # Safety guard overrides END intent
            user_wants_exit = False
            logger.info(
                f"Exit intent detected but blocked by safety guards - {safety_check.reason}"
            )
            logger.info(f"Violated rules: {', '.join(safety_check.violated_rules)}")
        else:
            # Not an END intent
            user_wants_exit = False
            logger.debug(
                f"Intent classified as: {classification.intent.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

        # Get or create terminal session for this conversation
        terminal_session_id = None
        if self.terminal_tool and session_id:
            if session_id not in self.terminal_tool.active_sessions:
                # Create terminal session proactively
                session_result = await self.terminal_tool.create_session(
                    agent_id=f"chat_agent_{session_id}",
                    conversation_id=session_id,
                    agent_role="chat_agent",
                    host="main",
                )
                if session_result.get("status") == "success":
                    terminal_session_id = self.terminal_tool.active_sessions.get(
                        session_id
                    )
            else:
                terminal_session_id = self.terminal_tool.active_sessions.get(session_id)

            logger.info(
                f"Terminal session ID for conversation {session_id}: {terminal_session_id}"
            )

        return session, terminal_session_id, user_wants_exit

    async def _prepare_llm_request_params(
        self, session: WorkflowSession, message: str
    ) -> Dict[str, Any]:
        """
        Prepare LLM request parameters including endpoint, model, and prompt.

        Args:
            session: Current workflow session
            message: User message

        Returns:
            Dictionary with 'endpoint', 'model', and 'prompt' keys
        """
        import httpx

        # Get Ollama endpoint from config
        try:
            ollama_endpoint = global_config_manager.get_nested(
                "backend.llm.ollama.endpoint", None
            )

            if not ollama_endpoint:
                from src.unified_config_manager import UnifiedConfigManager

                config = UnifiedConfigManager()
                ollama_host = config.get_host("ollama")
                ollama_port = config.get_port("ollama")
                ollama_endpoint = f"http://{ollama_host}:{ollama_port}/api/generate"

            # Validate endpoint format
            if not ollama_endpoint or not ollama_endpoint.startswith(
                ("http://", "https://")
            ):
                logger.error(
                    f"Invalid endpoint URL: {ollama_endpoint}, using config-based default"
                )
                from src.unified_config_manager import UnifiedConfigManager

                config = UnifiedConfigManager()
                ollama_host = config.get_host("ollama")
                ollama_port = config.get_port("ollama")
                ollama_endpoint = f"http://{ollama_host}:{ollama_port}/api/generate"

        except Exception as config_error:
            logger.error(f"Failed to load Ollama endpoint from config: {config_error}")
            from src.unified_config_manager import UnifiedConfigManager

            config = UnifiedConfigManager()
            ollama_host = config.get_host("ollama")
            ollama_port = config.get_port("ollama")
            ollama_endpoint = f"http://{ollama_host}:{ollama_port}/api/generate"

        # Load system prompt
        try:
            system_prompt = get_prompt("chat.system_prompt_simple")
            logger.debug("[ChatWorkflowManager] Loaded simplified system prompt")
        except Exception as prompt_error:
            logger.error(f"Failed to load system prompt from file: {prompt_error}")
            system_prompt = """You are AutoBot. Execute commands using:
<TOOL_CALL name="execute_command" params='{"command":"cmd"}'>desc</TOOL_CALL>

NEVER teach commands - ALWAYS execute them."""

        # Add minimal conversation history (last 2 messages only)
        conversation_context = ""
        if session.conversation_history:
            conversation_context = "\n**Recent Context:**\n"
            for msg in session.conversation_history[-2:]:
                conversation_context += (
                    f"User: {msg['user']}\nYou: {msg['assistant']}\n\n"
                )

        # Build complete prompt
        full_prompt = (
            system_prompt
            + conversation_context
            + f"\n**Current user message:** {message}\n\nAssistant:"
        )

        # Get selected model from config
        try:
            default_model = global_config_manager.get_default_llm_model()
            selected_model = global_config_manager.get_nested(
                "backend.llm.ollama.selected_model", default_model
            )

            if not selected_model or not isinstance(selected_model, str):
                logger.error(
                    f"Invalid model selection: {selected_model}, using default"
                ),
                selected_model = default_model

            logger.info(f"Using LLM model from config: {selected_model}")

        except Exception as config_error:
            logger.error(f"Failed to load model from config: {config_error}")
            import os

            selected_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "mistral:7b")

        logger.info(
            f"[ChatWorkflowManager] Making Ollama request to: {ollama_endpoint}"
        )
        logger.info(f"[ChatWorkflowManager] Using model: {selected_model}")

        return {
            "endpoint": ollama_endpoint,
            "model": selected_model,
            "prompt": full_prompt,
        }

    async def _interpret_command_results(
        self,
        command: str,
        stdout: str,
        stderr: str,
        return_code: int,
        ollama_endpoint: str,
        selected_model: str,
        streaming: bool = True,
    ):
        """
        Send command results to LLM for interpretation.

        Args:
            command: The executed command
            stdout: Standard output
            stderr: Standard error
            return_code: Command return code
            ollama_endpoint: Ollama API endpoint
            selected_model: Model to use
            streaming: Whether to stream the response

        Yields:
            WorkflowMessage chunks if streaming=True
        Returns:
            Full interpretation text
        """
        import httpx

        interpretation_prompt = f"""The command `{command}` was executed successfully.

Output:
```
{stdout}
{stderr if stderr else ''}
```
Return code: {return_code}

Please interpret this output for the user in a clear, helpful way.
Explain what it means and answer their original question."""

        interpretation = ""

        async with httpx.AsyncClient(timeout=60.0) as interp_client:
            if streaming:
                interp_response = await interp_client.post(
                    f"{ollama_endpoint}/api/generate",
                    json={
                        "model": selected_model,
                        "prompt": interpretation_prompt,
                        "stream": True,
                        "options": {
                            "temperature": 0.7,
                            "top_p": 0.9,
                            "num_ctx": 2048,
                        },
                    },
                )

                async for line in interp_response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                interpretation += chunk
                                yield WorkflowMessage(
                                    type="stream",
                                    content=chunk,
                                    metadata={
                                        "message_type": "command_interpretation",
                                        "streaming": True,
                                    },
                                )
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
            else:
                interp_response = await interp_client.post(
                    f"{ollama_endpoint}/api/generate",
                    json={
                        "model": selected_model,
                        "prompt": interpretation_prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "top_p": 0.9,
                            "num_ctx": 2048,
                        },
                    },
                )

                if interp_response.status_code == 200:
                    interp_data = interp_response.json()
                    interpretation = interp_data.get("response", "")

        # For non-streaming, yield the complete interpretation at once
        if not streaming and interpretation:
            yield WorkflowMessage(
                type="response",
                content=interpretation,
                metadata={
                    "message_type": "command_interpretation",
                    "streaming": False,
                },
            )

    async def interpret_terminal_command(
        self,
        command: str,
        stdout: str,
        stderr: str,
        return_code: int,
        session_id: str,
    ) -> str:
        """
        Public method to interpret terminal command results.

        This method is called by agent_terminal_service after command execution
        to get LLM interpretation of the command output.

        Args:
            command: The executed command
            stdout: Standard output
            stderr: Standard error
            return_code: Command return code
            session_id: Chat session ID for saving interpretation

        Returns:
            Full interpretation text from LLM
        """
        try:
            # Get Ollama configuration
            ollama_endpoint = global_config_manager.get_ollama_url()
            selected_model = global_config_manager.get_selected_model()

            logger.info(
                f"[interpret_terminal_command] Starting interpretation "
                f"for command: {command[:50]}..."
            )

            # Call the interpretation generator (non-streaming for terminal)
            interpretation = ""
            async for msg in self._interpret_command_results(
                command=command,
                stdout=stdout,
                stderr=stderr,
                return_code=return_code,
                ollama_endpoint=ollama_endpoint,
                selected_model=selected_model,
                streaming=False,  # Non-streaming for terminal
            ):
                if hasattr(msg, "content"):
                    interpretation += msg.content

            logger.info(
                f"[interpret_terminal_command] Interpretation complete, "
                f"length: {len(interpretation)}"
            )

            # Save interpretation to chat history
            if session_id and interpretation:
                try:
                    from src.chat_history_manager import ChatHistoryManager

                    chat_mgr = ChatHistoryManager()
                    await chat_mgr.add_message(
                        sender="assistant",
                        text=interpretation,
                        message_type="terminal_interpretation",
                        session_id=session_id,
                    )
                    logger.info(
                        f"[interpret_terminal_command] Saved interpretation "
                        f"to chat session {session_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"[interpret_terminal_command] Failed to save interpretation: {e}"
                    )

                # CRITICAL FIX: Persist to conversation history (chat:conversation) for LLM context
                # This fixes the bug where terminal interpretations weren't being tracked in LLM
                # context
                try:
                    # Get the session to access conversation_history
                    session = await self.get_or_create_session(session_id)

                    # Get the last user message from chat:session (most recent context)
                    if self.redis_client is not None:
                        session_key = f"chat:session:{session_id}"
                        try:
                            session_data_json = await asyncio.wait_for(
                                self.redis_client.get(session_key),
                                timeout=2.0
                            )
                            if session_data_json:
                                session_data = json.loads(session_data_json)
                                messages = session_data.get("messages", [])

                                # Find the most recent user message
                                last_user_message = None
                                for msg in reversed(messages):
                                    if msg.get("sender") == "user":
                                        last_user_message = msg.get("text", "")
                                        break

                                if last_user_message:
                                    # Persist the exchange to conversation history
                                    await self._persist_conversation(
                                        session_id=session_id,
                                        session=session,
                                        message=last_user_message,
                                        llm_response=interpretation
                                    )
                                    logger.info(
                                        f"✅ [interpret_terminal_command] Persisted user message + "
                                        f"interpretation to conversation history for LLM context "
                                        f"(session={session_id})"
                                    )
                                else:
                                    logger.warning(
                                        f"[interpret_terminal_command] No user message found in "
                                        f"session {session_id} - skipping conversation persistence"
                                    )
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"[interpret_terminal_command] Redis timeout getting session "
                                f"data for {session_id}"
                            )
                except Exception as persist_error:
                    logger.error(
                        f"[interpret_terminal_command] Failed to persist to conversation history: {persist_error}",
                        exc_info=True
                    )

            return interpretation

        except Exception as e:
            logger.error(
                f"[interpret_terminal_command] Error interpreting command: {e}",
                exc_info=True,
            )
            # Security: Don't expose internal error details to frontend
            return "Unable to interpret command results. Please check logs for details."

    async def _handle_pending_approval(
        self,
        session_id: str,
        command: str,
        result: Dict[str, Any],
        terminal_session_id: str,
        description: str,
    ):
        """
        Handle command approval workflow with polling.

        Args:
            session_id: Chat session ID
            command: Command requiring approval
            result: Result from terminal tool (contains approval request info)
            terminal_session_id: Terminal session ID for approval API
            description: Command description

        Yields:
            WorkflowMessage for approval request and status updates
        Returns:
            Approval result dict or None if timeout
        """
        # Send approval request to frontend
        approval_msg = WorkflowMessage(
            type="command_approval_request",
            content=result.get(
                "approval_ui_message",
                "Command requires approval",
            ),
            metadata={
                "command": command,
                "risk_level": result.get("risk"),
                "reasons": result.get("reasons", []),
                "description": description,
                "requires_approval": True,
                "terminal_session_id": terminal_session_id,
                "conversation_id": session_id,
            },
        )

        # Yield approval request
        yield approval_msg

        # CRITICAL: Persist approval request IMMEDIATELY to prevent data loss on restart
        # Don't wait until end of streaming - approval requests must survive backend restarts
        try:
            from src.chat_history_manager import ChatHistoryManager

            chat_mgr = ChatHistoryManager()
            await chat_mgr.add_message(
                sender="assistant",
                text=approval_msg.content,
                message_type="command_approval_request",
                raw_data=approval_msg.metadata,  # Preserve terminal_session_id!
                session_id=session_id,
            )
            logger.info(
                f"✅ Persisted approval request immediately: session={session_id}, "
                f"terminal={terminal_session_id}"
            )
        except Exception as persist_error:
            logger.error(
                f"Failed to persist approval request immediately: {persist_error}",
                exc_info=True,
            )

        # Yield waiting message
        yield WorkflowMessage(
            type="response",
            content=(
                f"\n\n⏳ Waiting for your approval to execute: `{command}`\n"
                f"Risk level: {result.get('risk')}\n"
                f"Reasons: {', '.join(result.get('reasons', []))}\n"
            ),
            metadata={
                "message_type": "approval_waiting",
                "command": command,
            },
        )

        # Wait for approval with timeout (poll terminal session)
        logger.info(f"🔍 [APPROVAL POLLING] Waiting for approval of command: {command}")
        logger.info(
            f"🔍 [APPROVAL POLLING] Chat session: {session_id}, Terminal session: {terminal_session_id}"
        )

        max_wait_time = 3600  # 1 hour timeout
        poll_interval = 0.5  # Poll every 500ms
        elapsed_time = 0
        poll_count = 0

        approval_result = None
        while elapsed_time < max_wait_time:
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval
            poll_count += 1

            # Check if approval has been processed
            try:
                session_info = (
                    await self.terminal_tool.agent_terminal_service.get_session_info(
                        terminal_session_id
                    )
                )

                # Log polling attempts every 10 seconds
                if poll_count % 20 == 0:
                    logger.info(
                        f"🔍 [APPROVAL POLLING] Still waiting... (elapsed: {elapsed_time:.1f}s, "
                        f"session: {terminal_session_id}, pending_approval: {session_info.get('pending_approval') is not None if session_info else 'NO SESSION INFO'})"
                    )

                # If pending_approval is None, command was either approved or denied
                if session_info and session_info.get("pending_approval") is None:
                    # Check session history for execution result
                    command_history = session_info.get("command_history", [])
                    if command_history:
                        last_command = command_history[-1]
                        if last_command.get("command") == command:
                            # Found the execution result
                            approval_result = last_command.get("result", {})
                            logger.info(
                                f"✅ [APPROVAL POLLING] Completion detected! "
                                f"Command: {command}, Status: {approval_result.get('status')}, "
                                f"Approved by: {last_command.get('approved_by')}"
                            )

                            # Send approval status update to frontend
                            approval_status = (
                                "approved"
                                if last_command.get("approved_by")
                                else "denied"
                            ),
                            comment = last_command.get(
                                "approval_comment"
                            ) or last_command.get("denial_reason")

                            yield WorkflowMessage(
                                type="metadata_update",
                                content="",
                                metadata={
                                    "message_type": "approval_status_update",
                                    "terminal_session_id": terminal_session_id,
                                    "approval_status": approval_status,
                                    "approval_comment": comment,
                                    "command": command,
                                },
                            )
                            break
                        else:
                            # CRITICAL FIX: Command in history doesn't match - wait a bit longer
                            # but don't poll forever (max 10 seconds after pending_approval is None)
                            if (
                                elapsed_time > max_wait_time - 3590
                            ):  # 10 seconds after approval cleared
                                logger.warning(
                                    f"⚠️ [APPROVAL POLLING] Timeout: pending_approval is None but command not found in history. "
                                    f"Expected: '{command}', Last in history: '{last_command.get('command')}'. "
                                    f"Breaking after {elapsed_time:.1f}s."
                                )
                                break
                    else:
                        # CRITICAL FIX: No command history but approval is cleared -
                        # break immediately
                        logger.warning(
                            f"⚠️ [APPROVAL POLLING] pending_approval is None but no command history. "
                            f"Breaking after {elapsed_time:.1f}s to prevent infinite loop."
                        )
                        break
            except Exception as check_error:
                logger.error(f"Error checking approval status: {check_error}")

        # Yield final result as a dict (not WorkflowMessage) for caller to process
        yield approval_result

    async def _persist_conversation(
        self,
        session_id: str,
        session: WorkflowSession,
        message: str,
        llm_response: str,
    ):
        """
        Persist conversation to Redis cache and file storage.

        Args:
            session_id: Session identifier
            session: Workflow session object
            message: User message
            llm_response: LLM response
        """
        # Store complete exchange in conversation history
        session.conversation_history.append(
            {"user": message, "assistant": llm_response}
        )

        # Keep history manageable (max 10 exchanges)
        if len(session.conversation_history) > 10:
            session.conversation_history = session.conversation_history[-10:]

        # Persist to both Redis (short-term cache) and file (long-term storage)
        await self._save_conversation_history(session_id, session.conversation_history)
        await self._append_to_transcript(session_id, message, llm_response)

    async def _process_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
    ):
        """
        Process all tool calls from LLM response.

        Args:
            tool_calls: List of parsed tool calls
            session_id: Chat session ID
            terminal_session_id: Terminal session ID
            ollama_endpoint: Ollama API endpoint
            selected_model: LLM model name

        Yields:
            WorkflowMessage for each stage of execution
        Returns:
            Additional text to append to llm_response
        """
        additional_response = ""

        for tool_call in tool_calls:
            if tool_call["name"] == "execute_command":
                command = tool_call["params"].get("command")
                host = tool_call["params"].get("host", "main")
                description = tool_call.get("description", "")

                logger.info(
                    f"[ChatWorkflowManager] Executing command: {command} on {host}"
                )

                # Execute command
                result = await self._execute_terminal_command(
                    session_id=session_id,
                    command=command,
                    host=host,
                    description=description,
                )

                # Handle different result statuses
                if result.get("status") == "pending_approval":
                    # Ensure terminal session ID is available
                    if not terminal_session_id:
                        logger.error(
                            f"No terminal session found for conversation {session_id}"
                        )
                        yield WorkflowMessage(
                            type="error",
                            content="Terminal session error - cannot request approval",
                            metadata={"error": True},
                        )
                        continue

                    # Handle approval workflow - yields messages and returns result
                    approval_result = None
                    async for approval_msg in self._handle_pending_approval(
                        session_id, command, result, terminal_session_id, description
                    ):
                        # Check if this is the final result (not a WorkflowMessage)
                        if isinstance(approval_msg, dict):
                            approval_result = approval_msg
                        else:
                            yield approval_msg

                    # Process approval result
                    if approval_result and approval_result.get("status") == "success":
                        # Yield execution confirmation
                        yield WorkflowMessage(
                            type="response",
                            content=(
                                "\n\n✅ Command approved and executed! Interpreting"
                                "results...\n\n"
                            ),
                            metadata={
                                "message_type": "command_executed",
                                "command": command,
                                "executed": True,
                                "approved": True,
                            },
                        )

                        # Stream interpretation
                        async for interp_chunk in self._interpret_command_results(
                            command,
                            approval_result.get("stdout", ""),
                            approval_result.get("stderr", ""),
                            approval_result.get("return_code", 0),
                            ollama_endpoint,
                            selected_model,
                            streaming=True,
                        ):
                            yield interp_chunk
                            if hasattr(interp_chunk, "content"):
                                additional_response += interp_chunk.content

                    elif approval_result:
                        # Command failed or denied
                        error = approval_result.get(
                            "error", "Command was denied or failed"
                        )
                        additional_response += f"\n\n❌ {error}"
                        yield WorkflowMessage(
                            type="error",
                            content=f"Command execution failed: {error}",
                            metadata={"command": command, "error": True},
                        )
                    else:
                        # Timeout
                        additional_response += (
                            f"\n\n⏱️ Approval timeout for command: {command}"
                        )
                        yield WorkflowMessage(
                            type="error",
                            content=f"Approval timeout for command: {command}",
                            metadata={"command": command, "timeout": True},
                        )

                elif result.get("status") == "success":
                    # Command executed without approval
                    # _interpret_command_results is an async generator, must iterate it
                    interpretation = ""
                    async for msg in self._interpret_command_results(
                        command,
                        result.get("stdout", ""),
                        result.get("stderr", ""),
                        result.get("return_code", 0),
                        ollama_endpoint,
                        selected_model,
                        streaming=False,
                    ):
                        if hasattr(msg, "content"):
                            interpretation += msg.content
                        # Yield the interpretation message to the caller
                        yield msg

                    # Also yield a summary message with all content
                    if interpretation:
                        yield WorkflowMessage(
                            type="response",
                            content=f"\n\n{interpretation}",
                            metadata={
                                "message_type": "command_result_interpretation",
                                "command": command,
                                "executed": True,
                            },
                        )
                    additional_response += f"\n\n{interpretation}"

                elif result.get("status") == "error":
                    # Command failed
                    error = result.get("error", "Unknown error")
                    additional_response += f"\n\n❌ Command execution failed: {error}"
                    yield WorkflowMessage(
                        type="error",
                        content=f"Command failed: {error}",
                        metadata={"command": command, "error": True},
                    )

        # Can't use return in generator - caller will aggregate chunks instead
        # Return value would be: additional_response

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
        from src.chat_history_manager import ChatHistoryManager

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
                    f"[ChatWorkflowManager] User explicitly requested to exit conversation: {session_id}"
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

            # Stage 2: Prepare LLM request parameters
            llm_params = await self._prepare_llm_request_params(session, message)
            ollama_endpoint = llm_params["endpoint"]
            selected_model = llm_params["model"]
            full_prompt = llm_params["prompt"]

            # Debug logging
            logger.info(
                f"[ChatWorkflowManager] Prompt length: {len(full_prompt)} characters"
            )
            print("\n" + "=" * 80, flush=True)
            print("=== OLLAMA REQUEST DEBUG ===", flush=True)
            print(f"Endpoint: {ollama_endpoint}", flush=True)
            print(f"Model: {selected_model}", flush=True)
            print(f"Prompt length: {len(full_prompt)} characters", flush=True)
            print("=" * 80 + "\n", flush=True)

            # Stage 3: Stream LLM response and handle tool calls
            try:
                import httpx

                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        ollama_endpoint,
                        json={
                            "model": selected_model,
                            "prompt": full_prompt,
                            "stream": True,
                            "options": {
                                "temperature": 0.7,
                                "top_p": 0.9,
                                "num_ctx": 2048,
                            },
                        },
                    ) as response:
                        logger.info(
                            f"[ChatWorkflowManager] Ollama response status: {response.status_code}"
                        )
                        if response.status_code == 200:
                            llm_response = ""

                            # Stream response chunks
                            async for line in response.aiter_lines():
                                if line:
                                    try:
                                        chunk_data = json.loads(line)
                                        chunk_text = chunk_data.get("response", "")

                                        if chunk_text:
                                            # Normalize TOOL_CALL spacing
                                            chunk_text = re.sub(
                                                r"<TOOL_\s+CALL",
                                                "<TOOL_CALL",
                                                chunk_text,
                                            ),
                                            chunk_text = re.sub(
                                                r"</TOOL_\s+CALL>",
                                                "</TOOL_CALL>",
                                                chunk_text,
                                            )

                                            llm_response += chunk_text

                                            chunk_msg = WorkflowMessage(
                                                type="response",
                                                content=chunk_text,
                                                metadata={
                                                    "message_type": (
                                                        "llm_response_chunk"
                                                    ),
                                                    "model": selected_model,
                                                    "streaming": True,
                                                    "terminal_session_id": (
                                                        terminal_session_id
                                                    ),
                                                },
                                            )
                                            # Don't collect streaming chunks -
                                            # only collect complete messages
                                            yield chunk_msg

                                        if chunk_data.get("done", False):
                                            break

                                    except json.JSONDecodeError as e:
                                        logger.error(
                                            f"Failed to parse stream chunk: {e}"
                                        )
                                        continue

                            logger.info(
                                f"[ChatWorkflowManager] Full LLM response length: {len(llm_response)} characters"
                            )

                            # Stage 4: Process tool calls if present
                            tool_calls = self._parse_tool_calls(llm_response)
                            logger.info(
                                f"[ChatWorkflowManager] Parsed {len(tool_calls)} tool calls from response"
                            )

                            if tool_calls:
                                # Delegate all tool call processing to helper method
                                async for tool_msg in self._process_tool_calls(
                                    tool_calls,
                                    session_id,
                                    terminal_session_id,
                                    ollama_endpoint,
                                    selected_model,
                                ):
                                    # Collect important WorkflowMessages for persistence
                                    # NOTE: command_approval_request is persisted immediately,
                                    # don't collect it here
                                    # Collect terminal commands, terminal output,
                                    # and errors for end-of-stream persistence
                                    if tool_msg.type in [
                                        "terminal_command",
                                        "terminal_output",
                                        "error",
                                    ]:
                                        workflow_messages.append(tool_msg)
                                        logger.debug(
                                            f"Collected WorkflowMessage for persistence: type={tool_msg.type}"
                                        )

                                    yield tool_msg

                            # Stage 5: Persist conversation (OLD METHOD -
                            # keeps for conversation_history)
                            await self._persist_conversation(
                                session_id, session, message, llm_response
                            )

                            # Stage 6: NEW - Persist WorkflowMessages and assistant response to chat
                            # history
                            # (User message already persisted immediately at start)
                            try:
                                chat_mgr = ChatHistoryManager()

                                # Persist all collected WorkflowMessages
                                for wf_msg in workflow_messages:
                                    # Map WorkflowMessage type to chat message type
                                    message_type = (
                                        wf_msg.type
                                    )  # e.g., "command_approval_request", "terminal_command"

                                    # Determine sender based on message type
                                    sender = (
                                        "assistant"  # Most messages are from assistant
                                    )
                                    if message_type == "terminal_output":
                                        sender = "system"

                                    await chat_mgr.add_message(
                                        sender=sender,
                                        text=wf_msg.content,
                                        message_type=message_type,
                                        raw_data=wf_msg.metadata,  # Include metadata as rawData
                                        session_id=session_id,
                                    )
                                    logger.debug(
                                        f"Persisted WorkflowMessage to chat history: type={message_type}, session={session_id}"
                                    )

                                # Persist final assistant response
                                await chat_mgr.add_message(
                                    sender="assistant",
                                    text=llm_response,
                                    message_type="llm_response",
                                    session_id=session_id,
                                )
                                logger.info(
                                    f"✅ Persisted complete conversation to chat history: session={session_id}, workflow_messages={len(workflow_messages)}"
                                )

                            except Exception as persist_error:
                                logger.error(
                                    f"Failed to persist WorkflowMessages to chat history: {persist_error}",
                                    exc_info=True,
                                )
                        else:
                            logger.error(
                                f"[ChatWorkflowManager] Ollama request failed: {response.status_code}"
                            )

                            error_msg = WorkflowMessage(
                                type="error",
                                content=f"LLM service error: {response.status_code}",
                                metadata={"error": True},
                            )
                            workflow_messages.append(error_msg)
                            yield error_msg

            except Exception as llm_error:
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

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session."""
        async with self._lock:
            if session_id not in self.sessions:
                return None

            session = self.sessions[session_id]
            return {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "message_count": session.message_count,
                "uptime": time.time() - session.created_at,
                "metadata": session.metadata,
            }

    async def cleanup_inactive_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up inactive sessions older than max_age_seconds."""
        current_time = time.time()
        removed_count = 0

        async with self._lock:
            sessions_to_remove = []

            for session_id, session in self.sessions.items():
                if current_time - session.last_activity > max_age_seconds:
                    sessions_to_remove.append(session_id)

            for session_id in sessions_to_remove:
                del self.sessions[session_id]
                removed_count += 1
                logger.info(f"Cleaned up inactive session: {session_id}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} inactive sessions")

        return removed_count

    async def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        async with self._lock:
            return len(self.sessions)

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


# Global instance for easy access
_workflow_manager: Optional[ChatWorkflowManager] = None


def get_chat_workflow_manager() -> ChatWorkflowManager:
    """Get the global chat workflow manager instance."""
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = ChatWorkflowManager()
    return _workflow_manager


async def initialize_chat_workflow_manager() -> bool:
    """Initialize the global chat workflow manager."""
    manager = get_chat_workflow_manager()
    return await manager.initialize()


# Export main classes and functions
__all__ = [
    "ChatWorkflowManager",
    "WorkflowSession",
    "get_chat_workflow_manager",
    "initialize_chat_workflow_manager",
]
