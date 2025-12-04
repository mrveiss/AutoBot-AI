# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM interaction handling for chat workflow.

Handles LLM request preparation, command result interpretation,
and streaming response processing.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List

from backend.dependencies import global_config_manager
from src.async_chat_workflow import WorkflowMessage
from src.constants.model_constants import ModelConstants
from src.prompt_manager import get_prompt
from src.utils.http_client import get_http_client

from .models import WorkflowSession

logger = logging.getLogger(__name__)


class LLMHandlerMixin:
    """Mixin for LLM interaction handling."""

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

    async def _prepare_llm_request_params(
        self, session: WorkflowSession, message: str, use_knowledge: bool = True
    ) -> Dict[str, Any]:
        """
        Prepare LLM request parameters including endpoint, model, and prompt.

        Args:
            session: Current workflow session
            message: User message
            use_knowledge: Whether to use knowledge base for RAG (Issue #249)

        Returns:
            Dictionary with 'endpoint', 'model', and 'prompt' keys
        """

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

        # Issue #249 Phase 3: Conversation-aware knowledge retrieval
        # Uses conversation history to enhance queries with context
        knowledge_context = ""
        citations = []
        query_intent = None
        enhanced_query = None
        if self.knowledge_service and use_knowledge:
            try:
                # Use conversation-aware retrieval
                # - Detects query intent (Phase 2)
                # - Enhances query with conversation context (Phase 3)
                # - Skips RAG for commands/greetings/short queries
                knowledge_context, citations, query_intent, enhanced_query = (
                    await self.knowledge_service.conversation_aware_retrieve(
                        query=message,
                        conversation_history=session.conversation_history or [],
                        top_k=5,
                        score_threshold=0.7,
                        force_retrieval=False,  # Allow intent-based skipping
                    )
                )
                if knowledge_context:
                    logger.info(
                        f"[RAG] Retrieved {len(citations)} knowledge facts "
                        f"(intent: {query_intent.intent.value}, "
                        f"enhanced: {enhanced_query.enhancement_applied if enhanced_query else False})"
                    )
                    # Store citations and context info in session metadata for frontend
                    session.metadata["last_citations"] = citations
                    session.metadata["used_knowledge"] = True
                    session.metadata["query_intent"] = query_intent.intent.value
                    if enhanced_query and enhanced_query.enhancement_applied:
                        session.metadata["query_enhanced"] = True
                        session.metadata["context_entities"] = enhanced_query.context_entities
                else:
                    session.metadata["used_knowledge"] = False
                    session.metadata["query_enhanced"] = False
                    if query_intent:
                        session.metadata["query_intent"] = query_intent.intent.value
                        session.metadata["rag_skipped_reason"] = query_intent.reasoning
            except Exception as kb_error:
                logger.warning(f"[RAG] Knowledge retrieval failed: {kb_error}")
                session.metadata["used_knowledge"] = False
                # Continue without knowledge - graceful degradation
        else:
            session.metadata["used_knowledge"] = False

        # Build complete prompt with optional knowledge context
        if knowledge_context:
            full_prompt = (
                system_prompt
                + "\n\n" + knowledge_context + "\n"
                + conversation_context
                + f"\n**Current user message:** {message}\n\nAssistant:"
            )
        else:
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

            selected_model = os.getenv(
                "AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL
            )

        logger.info(
            f"[ChatWorkflowManager] Making Ollama request to: {ollama_endpoint}"
        )
        logger.info(f"[ChatWorkflowManager] Using model: {selected_model}")

        return {
            "endpoint": ollama_endpoint,
            "model": selected_model,
            "prompt": full_prompt,
            "citations": citations,  # Issue #249: RAG citations for frontend
            "used_knowledge": bool(knowledge_context),
        }

    def _build_interpretation_prompt(
        self, command: str, stdout: str, stderr: str, return_code: int
    ) -> str:
        """Build the interpretation prompt for LLM (Issue #332 - extracted helper)."""
        return f"""The command `{command}` was executed successfully.

Output:
```
{stdout}
{stderr if stderr else ''}
```
Return code: {return_code}

Please interpret this output for the user in a clear, helpful way.
Explain what it means and answer their original question."""

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
        interpretation_prompt = self._build_interpretation_prompt(
            command, stdout, stderr, return_code
        )
        llm_options = {"temperature": 0.7, "top_p": 0.9, "num_ctx": 2048}
        interpretation = ""

        http_client = get_http_client()

        # Non-streaming path (Issue #332 - early return pattern)
        if not streaming:
            response_data = await http_client.post_json(
                f"{ollama_endpoint}/api/generate",
                json_data={
                    "model": selected_model,
                    "prompt": interpretation_prompt,
                    "stream": False,
                    "options": llm_options,
                },
            )
            interpretation = response_data.get("response", "")
            if interpretation:
                yield WorkflowMessage(
                    type="response",
                    content=interpretation,
                    metadata={"message_type": "command_interpretation", "streaming": False},
                )
            return

        # Streaming path (Issue #332 - refactored loop)
        import aiohttp
        async with await http_client.post(
            f"{ollama_endpoint}/api/generate",
            json={
                "model": selected_model,
                "prompt": interpretation_prompt,
                "stream": True,
                "options": llm_options,
            },
            timeout=aiohttp.ClientTimeout(total=60.0),
        ) as interp_response:
            async for line in interp_response.content:
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                chunk = data.get("response", "")
                if chunk:
                    interpretation += chunk
                    yield WorkflowMessage(
                        type="stream",
                        content=chunk,
                        metadata={"message_type": "command_interpretation", "streaming": True},
                    )

                if data.get("done"):
                    break

    async def _save_to_chat_history(
        self, session_id: str, interpretation: str
    ) -> None:
        """
        Save interpretation to chat history.

        Args:
            session_id: Chat session ID
            interpretation: Interpretation text to save

        Raises:
            Exception: If save fails (logged, not propagated)
        """
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

    async def _get_last_user_message(self, session_id: str) -> str | None:
        """
        Retrieve the last user message from Redis session data.

        Args:
            session_id: Chat session ID

        Returns:
            Last user message text, or None if not found or Redis unavailable

        Raises:
            asyncio.TimeoutError: If Redis operation times out (logged, returns None)
        """
        if self.redis_client is None:
            return None

        session_key = f"chat:session:{session_id}"
        try:
            session_data_json = await asyncio.wait_for(
                self.redis_client.get(session_key), timeout=2.0
            )
            if not session_data_json:
                return None

            session_data = json.loads(session_data_json)
            messages = session_data.get("messages", [])

            # Find the most recent user message
            for msg in reversed(messages):
                if msg.get("sender") == "user":
                    return msg.get("text", "")

            return None

        except asyncio.TimeoutError:
            logger.warning(
                f"[interpret_terminal_command] Redis timeout getting session "
                f"data for {session_id}"
            )
            return None

    async def _persist_to_conversation_history(
        self, session_id: str, interpretation: str
    ) -> None:
        """
        Persist terminal interpretation to conversation history for LLM context.

        CRITICAL FIX: This fixes the bug where terminal interpretations weren't
        being tracked in LLM context (chat:conversation).

        Args:
            session_id: Chat session ID
            interpretation: Interpretation text to persist

        Raises:
            Exception: If persistence fails (logged, not propagated)
        """
        try:
            # Get the session to access conversation_history
            session = await self.get_or_create_session(session_id)

            # Get the last user message from chat:session (most recent context)
            last_user_message = await self._get_last_user_message(session_id)

            if not last_user_message:
                logger.warning(
                    f"[interpret_terminal_command] No user message found in "
                    f"session {session_id} - skipping conversation persistence"
                )
                return

            # Persist the exchange to conversation history
            await self._persist_conversation(
                session_id=session_id,
                session=session,
                message=last_user_message,
                llm_response=interpretation,
            )
            logger.info(
                f"✅ [interpret_terminal_command] Persisted user message + "
                f"interpretation to conversation history for LLM context "
                f"(session={session_id})"
            )

        except Exception as persist_error:
            logger.error(
                f"[interpret_terminal_command] Failed to persist to conversation "
                f"history: {persist_error}",
                exc_info=True,
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

            # Early return if no session_id or interpretation to save
            if not session_id or not interpretation:
                return interpretation

            # Save interpretation to chat history
            await self._save_to_chat_history(session_id, interpretation)

            # Persist to conversation history (chat:conversation) for LLM context
            await self._persist_to_conversation_history(session_id, interpretation)

            return interpretation

        except Exception as e:
            logger.error(
                f"[interpret_terminal_command] Error interpreting command: {e}",
                exc_info=True,
            )
            # Security: Don't expose internal error details to frontend
            return "Unable to interpret command results. Please check logs for details."
