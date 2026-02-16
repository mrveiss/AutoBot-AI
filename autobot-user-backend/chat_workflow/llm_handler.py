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
from async_chat_workflow import WorkflowMessage
from backend.constants.model_constants import ModelConstants
from prompt_manager import get_prompt
from autobot_shared.http_client import get_http_client

from .models import WorkflowSession

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")


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

    def _get_ollama_endpoint_fallback(self) -> str:
        """Get Ollama endpoint from UnifiedConfigManager as fallback."""
        from config import UnifiedConfigManager
        config = UnifiedConfigManager()
        ollama_host = config.get_host("ollama")
        ollama_port = config.get_port("ollama")
        return f"http://{ollama_host}:{ollama_port}/api/generate"

    def _get_ollama_endpoint(self) -> str:
        """Get Ollama endpoint from config with fallbacks.

        Returns the Ollama API endpoint URL including /api/generate path.
        Config may store just the base URL, so we ensure the path is appended.
        """
        try:
            endpoint = global_config_manager.get_nested("backend.llm.ollama.endpoint", None)
            if endpoint and endpoint.startswith(_VALID_URL_SCHEMES):  # Issue #380
                # Ensure /api/generate path is included
                if not endpoint.endswith("/api/generate"):
                    endpoint = endpoint.rstrip("/") + "/api/generate"
                return endpoint
            logger.error("Invalid endpoint URL: %s, using config-based default", endpoint)
            return self._get_ollama_endpoint_fallback()
        except Exception as e:
            logger.error("Failed to load Ollama endpoint from config: %s", e)
            return self._get_ollama_endpoint_fallback()

    def _get_system_prompt(self) -> str:
        """Get system prompt with fallback."""
        try:
            prompt = get_prompt("chat.system_prompt_simple")
            logger.debug("[ChatWorkflowManager] Loaded simplified system prompt")
            return prompt
        except Exception as e:
            logger.error("Failed to load system prompt from file: %s", e)
            return """You are AutoBot. Execute commands using:
<TOOL_CALL name="execute_command" params='{"command":"cmd"}'>desc</TOOL_CALL>

NEVER teach commands - ALWAYS execute them."""

    def _build_conversation_context(self, session: WorkflowSession) -> str:
        """Build conversation context from recent history.

        Issue #715: Now handles incomplete entries (empty assistant response)
        that are registered before LLM call to fix race conditions.
        """
        if not session.conversation_history:
            return ""

        # Filter out incomplete entries (where assistant response is empty placeholder)
        # These are messages currently being processed
        complete_messages = [
            msg for msg in session.conversation_history
            if msg.get("assistant")  # Only include if assistant response exists
        ]

        if not complete_messages:
            return ""

        context_parts = ["\n**Recent Context:**\n"]
        context_parts.extend(
            f"User: {msg['user']}\nYou: {msg['assistant']}\n\n"
            for msg in complete_messages[-2:]
        )
        return "".join(context_parts)

    async def _retrieve_knowledge_context(
        self, message: str, session: WorkflowSession
    ) -> tuple:
        """Retrieve knowledge context for RAG. Returns (context, citations)."""
        try:
            knowledge_context, citations, query_intent, enhanced_query = (
                await self.knowledge_service.conversation_aware_retrieve(
                    query=message,
                    conversation_history=session.conversation_history or [],
                    top_k=5, score_threshold=0.7, force_retrieval=False,
                )
            )
            if knowledge_context:
                logger.info(
                    f"[RAG] Retrieved {len(citations)} knowledge facts "
                    f"(intent: {query_intent.intent.value}, "
                    f"enhanced: {enhanced_query.enhancement_applied if enhanced_query else False})"
                )
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
            return knowledge_context, citations
        except Exception as e:
            logger.warning("[RAG] Knowledge retrieval failed: %s", e)
            session.metadata["used_knowledge"] = False
            return "", []

    def _build_full_prompt(
        self, system_prompt: str, knowledge_context: str, conversation_context: str, message: str
    ) -> str:
        """Build full prompt with optional knowledge context."""
        if knowledge_context:
            return (
                system_prompt + "\n\n" + knowledge_context + "\n"
                + conversation_context + f"\n**Current user message:** {message}\n\nAssistant:"
            )
        return system_prompt + conversation_context + f"\n**Current user message:** {message}\n\nAssistant:"

    def _get_selected_model(self) -> str:
        """Get selected LLM model from config with fallback."""
        try:
            default_model = global_config_manager.get_default_llm_model()
            selected = global_config_manager.get_nested("backend.llm.ollama.selected_model", default_model)
            if selected and isinstance(selected, str):
                logger.info("Using LLM model from config: %s", selected)
                return selected
            logger.error("Invalid model selection: %s, using default", selected)
            return default_model
        except Exception as e:
            logger.error("Failed to load model from config: %s", e)
            import os
            return os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL)

    async def _prepare_llm_request_params(
        self, session: WorkflowSession, message: str, use_knowledge: bool = True
    ) -> Dict[str, Any]:
        """Prepare LLM request parameters including endpoint, model, and prompt."""
        ollama_endpoint = self._get_ollama_endpoint()
        system_prompt = self._get_system_prompt()
        conversation_context = self._build_conversation_context(session)

        # Knowledge retrieval for RAG
        knowledge_context, citations = "", []
        if self.knowledge_service and use_knowledge:
            knowledge_context, citations = await self._retrieve_knowledge_context(message, session)
        else:
            session.metadata["used_knowledge"] = False

        full_prompt = self._build_full_prompt(system_prompt, knowledge_context, conversation_context, message)
        selected_model = self._get_selected_model()

        logger.info("[ChatWorkflowManager] Making Ollama request to: %s", ollama_endpoint)
        logger.info("[ChatWorkflowManager] Using model: %s", selected_model)

        return {
            "endpoint": ollama_endpoint,
            "model": selected_model,
            "prompt": full_prompt,
            "system_prompt": system_prompt,
            "citations": citations,
            "used_knowledge": bool(knowledge_context),
        }

    def _build_interpretation_prompt(
        self, command: str, stdout: str, stderr: str, return_code: int
    ) -> str:
        """Build the interpretation prompt for LLM (Issue #332 - extracted helper)."""
        # Issue #352: Modified to not imply task completion - just explain this step's results
        return f"""The command `{command}` was executed.

Output:
```
{stdout}
{stderr if stderr else ''}
```
Return code: {return_code}

Briefly explain what this output shows. Keep it concise (2-3 sentences max).
Do NOT conclude the task or provide a final summary - just explain this specific result."""

    def _get_interpretation_llm_options(self) -> Dict[str, Any]:
        """Get LLM options for command interpretation."""
        return {"temperature": 0.7, "top_p": 0.9, "num_ctx": 2048}

    async def _interpret_non_streaming(
        self,
        ollama_endpoint: str,
        selected_model: str,
        interpretation_prompt: str,
        llm_options: Dict[str, Any],
    ):
        """Handle non-streaming interpretation request (Issue #332)."""
        http_client = get_http_client()
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

    async def _interpret_streaming(
        self,
        ollama_endpoint: str,
        selected_model: str,
        interpretation_prompt: str,
        llm_options: Dict[str, Any],
    ):
        """Handle streaming interpretation request (Issue #332)."""
        import aiohttp

        http_client = get_http_client()
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
                    yield WorkflowMessage(
                        type="stream",
                        content=chunk,
                        metadata={"message_type": "command_interpretation", "streaming": True},
                    )

                if data.get("done"):
                    break

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
            WorkflowMessage chunks
        """
        interpretation_prompt = self._build_interpretation_prompt(
            command, stdout, stderr, return_code
        )
        llm_options = self._get_interpretation_llm_options()

        if not streaming:
            async for msg in self._interpret_non_streaming(
                ollama_endpoint, selected_model, interpretation_prompt, llm_options
            ):
                yield msg
            return

        async for msg in self._interpret_streaming(
            ollama_endpoint, selected_model, interpretation_prompt, llm_options
        ):
            yield msg

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
            from chat_history import ChatHistoryManager

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

    async def _get_interpretation_from_llm(
        self, command: str, stdout: str, stderr: str, return_code: int
    ) -> str:
        """Get LLM interpretation for command results (non-streaming)."""
        ollama_endpoint = global_config_manager.get_ollama_url()
        selected_model = global_config_manager.get_selected_model()

        logger.info(
            f"[interpret_terminal_command] Starting interpretation "
            f"for command: {command[:50]}..."
        )

        interpretation = ""
        async for msg in self._interpret_command_results(
            command=command,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            ollama_endpoint=ollama_endpoint,
            selected_model=selected_model,
            streaming=False,
        ):
            if hasattr(msg, "content"):
                interpretation += msg.content

        logger.info(
            f"[interpret_terminal_command] Interpretation complete, "
            f"length: {len(interpretation)}"
        )
        return interpretation

    async def interpret_terminal_command(
        self, command: str, stdout: str, stderr: str, return_code: int, session_id: str
    ) -> str:
        """
        Public method to interpret terminal command results.

        Called by agent_terminal_service after command execution.

        Returns:
            Full interpretation text from LLM
        """
        try:
            interpretation = await self._get_interpretation_from_llm(
                command, stdout, stderr, return_code
            )

            if not session_id or not interpretation:
                return interpretation

            await self._save_to_chat_history(session_id, interpretation)
            await self._persist_to_conversation_history(session_id, interpretation)

            return interpretation

        except Exception as e:
            logger.error(
                f"[interpret_terminal_command] Error interpreting command: {e}",
                exc_info=True,
            )
            return "Unable to interpret command results. Please check logs for details."
