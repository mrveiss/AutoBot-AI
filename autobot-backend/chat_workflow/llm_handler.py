# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM interaction handling for chat workflow.

Handles LLM request preparation, command result interpretation,
and streaming response processing.
"""

import asyncio
import json
from typing import Any, Dict, List

from async_chat_workflow import WorkflowMessage
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot_config
from constants.api_constants import PATH_OLLAMA_GENERATE
from constants.model_constants import ModelConstants
from dependencies import get_config
from middleware.base import HookContext
from middleware.hooks import HookPoint
from middleware.manager import get_extension_manager
from prompt_manager import get_language_instruction, get_prompt, resolve_language

from .models import WorkflowSession

logger = get_logger(__name__)

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")


async def _emit_system_prompt_ready(system_prompt: str, session: Any) -> str:
    """Emit ON_SYSTEM_PROMPT_READY to registered extensions and return result.

    Issue #3405: Fires after _get_system_prompt() so extensions can inspect or
    rewrite the system prompt before it enters prompt assembly.  If no extension
    is registered for this hook the function is a no-op and the original prompt
    is returned unchanged.

    Args:
        system_prompt: The assembled system prompt string.
        session: WorkflowSession instance (passed as data["session"]).

    Returns:
        Possibly modified system prompt string.
    """
    ctx = HookContext(
        session_id=getattr(session, "session_id", ""),
        data={"system_prompt": system_prompt, "session": session},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.SYSTEM_PROMPT_READY, ctx, "system_prompt")
    if isinstance(result, str) and result != system_prompt:
        logger.debug(
            "[#3405] SYSTEM_PROMPT_READY modified system prompt (%d -> %d chars)",
            len(system_prompt),
            len(result),
        )
        return result
    return system_prompt


async def _emit_full_prompt_ready(prompt: str, llm_params: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Emit ON_FULL_PROMPT_READY to registered extensions and return result.

    Issue #3405: Fires after _build_full_prompt() so extensions can append
    dynamic content (e.g. infrastructure telemetry hints) before the prompt
    is sent to the LLM.  If no extension is registered for this hook the
    function is a no-op and the original prompt is returned unchanged.

    Args:
        prompt: The fully assembled prompt string.
        llm_params: Dict containing model/endpoint selection.
        context: Arbitrary request-level context dict.

    Returns:
        Possibly modified full prompt string.
    """
    ctx = HookContext(
        session_id=context.get("session_id", ""),
        data={"prompt": prompt, "llm_params": llm_params, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.FULL_PROMPT_READY, ctx, "prompt")
    if isinstance(result, str) and result != prompt:
        logger.debug(
            "[#3405] FULL_PROMPT_READY modified full prompt (%d -> %d chars)",
            len(prompt),
            len(result),
        )
        return result
    return prompt


async def _emit_before_message_process(message: str, session_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Emit BEFORE_MESSAGE_PROCESS hook to registered extensions.

    Issue #4181: Fires at the start of message handling so extensions can
    inspect or modify the message and context before processing begins.

    Args:
        message: User message to process
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Dict with potentially modified message and context
    """
    ctx = HookContext(
        session_id=session_id,
        message=message,
        data={"message": message, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
    return {
        "message": ctx.get("message", message),
        "context": ctx.get("context", context),
    }


async def _emit_before_prompt_build(session_id: str, context: Dict[str, Any]) -> None:
    """Emit BEFORE_PROMPT_BUILD hook to registered extensions.

    Issue #4265: Fires before prompt building begins so extensions can
    prepare or modify context before prompt assembly starts.

    Args:
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.BEFORE_PROMPT_BUILD, ctx)


async def _emit_after_prompt_build(prompt: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit AFTER_PROMPT_BUILD hook to registered extensions.

    Issue #4265: Fires after prompt is built so extensions can
    inspect or modify the prompt before being sent to the LLM.

    Args:
        prompt: The built prompt string
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified prompt string
    """
    ctx = HookContext(
        session_id=session_id,
        data={"prompt": prompt, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.AFTER_PROMPT_BUILD, ctx, "prompt")
    return result if isinstance(result, str) else prompt


async def _emit_before_llm_call(prompt: str, llm_params: Dict[str, Any], session_id: str) -> bool:
    """Emit BEFORE_LLM_CALL hook to registered extensions.

    Issue #4181: Fires before calling the LLM so extensions can reject
    or modify the call. If any extension returns False, the call is cancelled.

    Args:
        prompt: The prompt to send to LLM
        llm_params: LLM parameters (model, endpoint, etc.)
        session_id: Session identifier

    Returns:
        False to cancel the LLM call, True otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={"prompt": prompt, "llm_params": llm_params},
    )
    results = await get_extension_manager().invoke_hook(HookPoint.BEFORE_LLM_CALL, ctx)
    # If any extension returns False, cancel
    return not any(result is False for result in results)


async def _emit_during_llm_streaming(chunk: str, session_id: str, context: Dict[str, Any]) -> None:
    """Emit DURING_LLM_STREAMING hook to registered extensions.

    Issue #4181: Fires during LLM response streaming so extensions can
    monitor or process partial responses.

    Args:
        chunk: Streamed response chunk
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"chunk": chunk, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.DURING_LLM_STREAMING, ctx)


async def _emit_after_llm_response(response: str, llm_params: Dict[str, Any], session_id: str) -> str:
    """Emit AFTER_LLM_RESPONSE hook to registered extensions.

    Issue #4181: Fires after LLM returns full response so extensions can
    inspect or modify it.

    Args:
        response: The LLM response text
        llm_params: LLM parameters used
        session_id: Session identifier

    Returns:
        Possibly modified response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"response": response, "llm_params": llm_params},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.AFTER_LLM_RESPONSE, ctx, "response")
    return result if isinstance(result, str) else response


async def _emit_before_tool_parse(llm_response: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit BEFORE_TOOL_PARSE hook to registered extensions.

    Issue #4181: Fires before parsing tool calls from LLM response so
    extensions can inspect or modify the raw response.

    Args:
        llm_response: Raw LLM response text
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"llm_response": llm_response, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.BEFORE_TOOL_PARSE, ctx, "llm_response")
    return result if isinstance(result, str) else llm_response


async def _emit_before_tool_execute(tool_name: str, tool_params: Dict[str, Any], session_id: str) -> bool:
    """Emit BEFORE_TOOL_EXECUTE hook to registered extensions.

    Issue #4181: Fires before executing a tool so extensions can reject
    or validate the execution.

    Args:
        tool_name: Name of tool to execute
        tool_params: Tool parameters
        session_id: Session identifier

    Returns:
        False to cancel tool execution, True otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={"tool_name": tool_name, "tool_params": tool_params},
    )
    results = await get_extension_manager().invoke_hook(HookPoint.BEFORE_TOOL_EXECUTE, ctx)
    return not any(result is False for result in results)


async def _emit_after_tool_execute(tool_name: str, tool_result: Any, session_id: str, context: Dict[str, Any]) -> Any:
    """Emit AFTER_TOOL_EXECUTE hook to registered extensions.

    Issue #4181: Fires after tool execution so extensions can inspect
    or modify the result.

    Args:
        tool_name: Name of executed tool
        tool_result: Result returned by tool
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified tool result
    """
    ctx = HookContext(
        session_id=session_id,
        data={
            "tool_name": tool_name,
            "tool_result": tool_result,
            "context": context,
        },
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.AFTER_TOOL_EXECUTE, ctx, "tool_result")
    return result if result is not None else tool_result


async def _emit_tool_error(tool_name: str, error: Exception, session_id: str, context: Dict[str, Any]) -> None:
    """Emit TOOL_ERROR hook to registered extensions.

    Issue #4181: Fires when tool execution fails so extensions can
    log, monitor, or attempt recovery.

    Args:
        tool_name: Name of tool that failed
        error: Exception raised by tool
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={
            "tool_name": tool_name,
            "error": str(error),
            "error_type": type(error).__name__,
            "context": context,
        },
    )
    await get_extension_manager().invoke_hook(HookPoint.TOOL_ERROR, ctx)


async def _emit_before_continuation(iteration: int, session_id: str, context: Dict[str, Any]) -> bool:
    """Emit BEFORE_CONTINUATION hook to registered extensions.

    Issue #4181: Fires before starting next iteration of continuation loop
    so extensions can inspect state or cancel continuation.

    Args:
        iteration: Current iteration number
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        False to cancel continuation, True otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={"iteration": iteration, "context": context},
    )
    results = await get_extension_manager().invoke_hook(HookPoint.BEFORE_CONTINUATION, ctx)
    return not any(result is False for result in results)


async def _emit_after_continuation(iteration: int, response: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit AFTER_CONTINUATION hook to registered extensions.

    Issue #4181: Fires after continuation iteration completes so extensions
    can inspect or modify the response.

    Args:
        iteration: Completed iteration number
        response: Response from this iteration
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"iteration": iteration, "response": response, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.AFTER_CONTINUATION, ctx, "response")
    return result if isinstance(result, str) else response


async def _emit_loop_complete(total_iterations: int, final_response: str, session_id: str) -> str:
    """Emit LOOP_COMPLETE hook to registered extensions.

    Issue #4181: Fires when continuation loop completes so extensions
    can finalize or modify the final response.

    Args:
        total_iterations: Total iterations completed
        final_response: Final response from loop
        session_id: Session identifier

    Returns:
        Possibly modified final response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"total_iterations": total_iterations, "final_response": final_response},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.LOOP_COMPLETE, ctx, "final_response")
    return result if isinstance(result, str) else final_response


async def _emit_repairable_error(error: Exception, session_id: str, context: Dict[str, Any]) -> bool:
    """Emit REPAIRABLE_ERROR hook to registered extensions.

    Issue #4181: Fires when a repairable error occurs so extensions
    can attempt recovery or take corrective action.

    Args:
        error: The repairable exception
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        True if error was handled, False otherwise
    """
    ctx = HookContext(
        session_id=session_id,
        data={
            "error": str(error),
            "error_type": type(error).__name__,
            "context": context,
        },
    )
    result = await get_extension_manager().invoke_until_handled(HookPoint.REPAIRABLE_ERROR, ctx)
    return result is not None


async def _emit_critical_error(error: Exception, session_id: str, context: Dict[str, Any]) -> None:
    """Emit CRITICAL_ERROR hook to registered extensions.

    Issue #4181: Fires when a critical unrecoverable error occurs so
    extensions can log, alert, or perform cleanup.

    Args:
        error: The critical exception
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={
            "error": str(error),
            "error_type": type(error).__name__,
            "context": context,
        },
    )
    await get_extension_manager().invoke_hook(HookPoint.CRITICAL_ERROR, ctx)


async def _emit_before_response_send(response: str, session_id: str, context: Dict[str, Any]) -> str:
    """Emit BEFORE_RESPONSE_SEND hook to registered extensions.

    Issue #4181: Fires before sending response to user so extensions
    can inspect, filter, or modify the response.

    Args:
        response: Response to be sent
        session_id: Session identifier
        context: Request-level context dict

    Returns:
        Possibly modified response
    """
    ctx = HookContext(
        session_id=session_id,
        data={"response": response, "context": context},
    )
    result = await get_extension_manager().invoke_with_transform(HookPoint.BEFORE_RESPONSE_SEND, ctx, "response")
    return result if isinstance(result, str) else response


async def _emit_after_response_send(response: str, session_id: str, context: Dict[str, Any]) -> None:
    """Emit AFTER_RESPONSE_SEND hook to registered extensions.

    Issue #4181: Fires after response is sent to user so extensions
    can perform post-processing or logging.

    Args:
        response: Response that was sent
        session_id: Session identifier
        context: Request-level context dict
    """
    ctx = HookContext(
        session_id=session_id,
        data={"response": response, "context": context},
    )
    await get_extension_manager().invoke_hook(HookPoint.AFTER_RESPONSE_SEND, ctx)


class LLMHandlerMixin:
    """Mixin for LLM interaction handling."""

    def _convert_conversation_history_format(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
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
                converted.append({"role": "assistant", "content": exchange["assistant"]})
        return converted

    def _get_ollama_endpoint_fallback(self) -> str:
        """Get Ollama endpoint from ssot_config as fallback (Issue #3829)."""
        # _ssot_config is already imported at module level
        return f"{_ssot_config.ollama_url}{PATH_OLLAMA_GENERATE}"

    def _get_ollama_endpoint(self) -> str:
        """Get Ollama endpoint from config with fallbacks.

        Returns the Ollama API endpoint URL including /api/generate path.
        Config may store just the base URL, so we ensure the path is appended.
        """
        try:
            endpoint = get_config().get_nested("backend.llm.ollama.endpoint", None)
            if endpoint and endpoint.startswith(_VALID_URL_SCHEMES):  # Issue #380
                # Ensure /api/generate path is included
                if not endpoint.endswith(PATH_OLLAMA_GENERATE):
                    endpoint = endpoint.rstrip("/") + PATH_OLLAMA_GENERATE
                return endpoint
            logger.error(
                "Invalid endpoint URL: %s, using config-based default", endpoint
            )  # codeql[py/clear-text-logging-sensitive-data]
            return self._get_ollama_endpoint_fallback()
        except Exception as e:
            logger.error("Failed to load Ollama endpoint from config: %s", e)
            return self._get_ollama_endpoint_fallback()

    def _get_ollama_endpoint_for_model(self, model_name: str) -> str:
        """Get Ollama endpoint routed by model name (#1070).

        GPU models are sent to gpu_endpoint; others to the default.
        Returns URL with /api/generate suffix.
        """
        try:
            base_url = get_config().get_ollama_endpoint_for_model(model_name)
            if base_url and base_url.startswith(_VALID_URL_SCHEMES):
                if not base_url.endswith(PATH_OLLAMA_GENERATE):
                    base_url = base_url.rstrip("/") + PATH_OLLAMA_GENERATE
                return base_url
        except Exception as e:
            logger.warning("Model endpoint routing failed: %s", e)
        return self._get_ollama_endpoint()

    async def _discover_ollama_from_slm(self) -> str | None:
        """Try to discover Ollama endpoint from SLM service discovery (#1214).

        Uses the SLM /api/discover/ollama endpoint (cached with 60s TTL).
        Returns base URL (no /api/generate suffix) or None if unavailable.
        """
        try:
            from services.slm_client import discover_service

            url = await discover_service("ollama")
            if url and url.startswith(_VALID_URL_SCHEMES):
                logger.info("Ollama endpoint from SLM discovery: %s", url)
                return url
        except Exception as e:
            logger.debug("SLM service discovery unavailable: %s", e)
        return None

    def _get_personality_preamble(self) -> str:
        """Return personality block if enabled, else empty string.

        Issue #964: Personality profile injection.
        """
        try:
            from services.personality_service import get_personality_manager

            profile = get_personality_manager().get_active_profile()
            if profile is None:
                return ""
            return profile.to_prompt_block() + "\n\n---\n\n"
        except Exception as exc:
            logger.warning("Personality profile load failed: %s", exc)
            return ""

    def _resolve_language(self, request_language=None):
        """Resolve response language. Delegates to prompt_manager.

        Issue #1327: Moved to shared utility in prompt_manager.
        """
        return resolve_language(request_language)

    def _get_language_instruction(self, language_code):
        """Build language instruction. Delegates to prompt_manager.

        Issue #1327: Moved to shared utility in prompt_manager.
        """
        return get_language_instruction(language_code)

    def _get_system_prompt(self, language=None) -> str:
        """Get system prompt with optional personality preamble.

        Issue #964: Personality preamble prepended when a profile is active.
        Issue #1325: Appends language instruction when non-English.
        """
        preamble = self._get_personality_preamble()
        resolved_lang = self._resolve_language(language)
        lang_instruction = self._get_language_instruction(resolved_lang)
        try:
            prompt = get_prompt("chat.system_prompt_simple")
            logger.debug("[ChatWorkflowManager] Loaded simplified system prompt")
            return preamble + prompt + lang_instruction
        except Exception as e:
            logger.error("Failed to load system prompt from file: %s", e)
            return preamble + """You are AutoBot. Execute commands using:
<TOOL_CALL name="execute_command" params='{"command":"cmd"}'>desc</TOOL_CALL>

NEVER teach commands - ALWAYS execute them.""" + lang_instruction

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
            msg
            for msg in session.conversation_history
            if msg.get("assistant")  # Only include if assistant response exists
        ]

        if not complete_messages:
            return ""

        context_parts = ["\n**Recent Context:**\n"]
        context_parts.extend(f"User: {msg['user']}\nYou: {msg['assistant']}\n\n" for msg in complete_messages[-2:])
        return "".join(context_parts)

    async def _retrieve_knowledge_context(self, message: str, session: WorkflowSession) -> tuple:
        """Retrieve knowledge context for RAG. Returns (context, citations)."""
        try:
            (
                knowledge_context,
                citations,
                query_intent,
                enhanced_query,
            ) = await self.knowledge_service.conversation_aware_retrieve(
                query=message,
                conversation_history=session.conversation_history or [],
                top_k=5,
                score_threshold=0.3,  # Issue #1526: lowered from 0.7
                force_retrieval=False,
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
        self,
        knowledge_context: str,
        conversation_context: str,
        message: str,
    ) -> str:
        """Build full prompt with optional knowledge context.

        system_prompt is sent via the Ollama ``system`` field — not embedded here
        to avoid double-injection and context-window waste.
        """
        if knowledge_context:
            return (
                knowledge_context + "\n" + conversation_context + f"\n**Current user message:** {message}\n\nAssistant:"
            )
        return conversation_context + f"\n**Current user message:** {message}\n\nAssistant:"

    def _get_selected_model(self) -> str:
        """Get selected LLM model from config with fallback."""
        try:
            default_model = get_config().get_default_llm_model()
            selected = get_config().get_nested("backend.llm.ollama.selected_model", default_model)
            if selected and isinstance(selected, str):
                logger.info("Using LLM model from config: %s", selected)  # codeql[py/clear-text-logging-sensitive-data]
                return selected
            logger.error(
                "Invalid model selection: %s, using default", selected
            )  # codeql[py/clear-text-logging-sensitive-data]
            return default_model
        except Exception as e:
            logger.error("Failed to load model from config: %s", e)

            return _ssot_config.default_llm_model

    async def _prepare_llm_request_params(
        self,
        session: WorkflowSession,
        message: str,
        use_knowledge: bool = True,
        language: str = None,
        lightweight_mode: bool = False,
    ) -> Dict[str, Any]:
        """Prepare LLM request parameters including endpoint, model, and prompt.

        Issue #1325: Accepts language for system prompt resolution.
        Issue MVA-1992: lightweight_mode bypasses RAG/memory for trivial queries.
        """
        selected_model = self._get_selected_model()
        # Issue #1214: Try SLM service discovery first (fleet-managed endpoint),
        # then fall back to local config-based resolution (#1070 model routing).
        slm_base = await self._discover_ollama_from_slm()
        if slm_base:
            if not slm_base.endswith(PATH_OLLAMA_GENERATE):
                slm_base = slm_base.rstrip("/") + PATH_OLLAMA_GENERATE
            ollama_endpoint = slm_base
        else:
            ollama_endpoint = self._get_ollama_endpoint_for_model(selected_model)

        # Issue #4265: Emit BEFORE_PROMPT_BUILD hook before building prompts
        await _emit_before_prompt_build(
            session.session_id,
            {"message": message, "use_knowledge": use_knowledge, "language": language},
        )

        system_prompt = self._get_system_prompt(language=language)
        # Issue #5066: Tiered L0-L3 context wake-up (A/B against legacy path).
        # When TIERED_CONTEXT_ENABLED=true the TieredContextBuilder owns all
        # context prepending (L0 identity + L1 essential story + L2/L3 on-demand).
        # When false the pre-existing unconditional EssentialStory path is used.
        # Issue MVA-1992: Skip memory graph lookup when lightweight_mode=True.
        if not lightweight_mode:
            try:
                from chat_history.layers import TIERED_CONTEXT_ENABLED, TieredContextBuilder

                if TIERED_CONTEXT_ENABLED:
                    tiered_ctx = await TieredContextBuilder().build(
                        user_message=message,
                        model_name=selected_model,
                        session_id=session.session_id,
                        memory_graph=getattr(self, "memory_graph", None),
                        knowledge_service=self.knowledge_service if use_knowledge else None,
                    )
                    if tiered_ctx:
                        system_prompt = tiered_ctx + "\n\n" + system_prompt
                else:
                    # Issue #3787: legacy always-loaded compact memory summary.
                    from memory.essential_story import EssentialStoryGenerator

                    story = await EssentialStoryGenerator().generate(model_name=selected_model)
                    if story:
                        system_prompt = story + "\n\n" + system_prompt
            except Exception as _ctx_exc:
                logger.warning("Context injection failed: %s", _ctx_exc)
        system_prompt = await _emit_system_prompt_ready(system_prompt, session)
        conversation_context = self._build_conversation_context(session)

        # Knowledge retrieval for RAG
        # Issue MVA-1992: Skip RAG when lightweight_mode=True
        knowledge_context, citations = "", []
        if self.knowledge_service and use_knowledge and not lightweight_mode:
            knowledge_context, citations = await self._retrieve_knowledge_context(message, session)
            # Issue #3770: compress KB results when context exceeds model budget
            if knowledge_context and citations:
                from context_window_manager import ContextWindowManager
                from services.memory.compression import ContextCompressionService

                cwm = ContextWindowManager()
                cwm.set_model(selected_model)
                kc_tokens = cwm.estimate_tokens(knowledge_context)
                max_kb_tokens = cwm.get_max_history_tokens()
                if await cwm.async_should_compress(content_tokens=kc_tokens, model_name=selected_model):
                    svc = ContextCompressionService(
                        model_thresholds={
                            name: spec.get("compression_threshold", 8192)
                            for name, spec in cwm.config.get("models", {}).items()
                            if isinstance(spec, dict)
                        }
                    )
                    citations = await svc.compress_kb_results(citations, max_tokens=max_kb_tokens)
                    # Rebuild knowledge context from trimmed citations
                    if citations:
                        lines = ["KNOWLEDGE CONTEXT:"]
                        for i, c in enumerate(citations, 1):
                            score = c.get("score", 0.0)
                            content = c.get("content", "").strip()
                            lines.append(f"{i}. [score: {score:.2f}] {content}")
                        knowledge_context = "\n".join(lines)
                        logger.info(
                            "[#3770] KB compressed to %d citations (%d tokens)",
                            len(citations),
                            cwm.estimate_tokens(knowledge_context),
                        )
                    else:
                        knowledge_context = ""
        else:
            session.metadata["used_knowledge"] = False

        full_prompt = self._build_full_prompt(knowledge_context, conversation_context, message)

        # Issue #4265: Emit AFTER_PROMPT_BUILD hook after full prompt is built
        full_prompt = await _emit_after_prompt_build(
            full_prompt,
            session.session_id,
            {"message": message, "use_knowledge": use_knowledge},
        )

        full_prompt = await _emit_full_prompt_ready(
            full_prompt,
            {"endpoint": ollama_endpoint, "model": selected_model},
            {"session_id": session.session_id, "message": message},
        )

        logger.info(
            "[ChatWorkflowManager] Making Ollama request to: %s", ollama_endpoint
        )  # codeql[py/clear-text-logging-sensitive-data]
        logger.info(
            "[ChatWorkflowManager] Using model: %s", selected_model
        )  # codeql[py/clear-text-logging-sensitive-data]

        return {
            "endpoint": ollama_endpoint,
            "model": selected_model,
            "prompt": full_prompt,
            "system_prompt": system_prompt,
            "citations": citations,
            "used_knowledge": bool(knowledge_context),
        }

    def _build_interpretation_prompt(self, command: str, stdout: str, stderr: str, return_code: int) -> str:
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
        return {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_ctx": ModelConstants.DEFAULT_NUM_CTX,
        }

    async def _interpret_non_streaming(
        self,
        ollama_endpoint: str,
        selected_model: str,
        interpretation_prompt: str,
        llm_options: Dict[str, Any],
        session_id: str = "",
    ):
        """Handle non-streaming interpretation request (Issue #332)."""
        # Issue #4259: Wire BEFORE_LLM_CALL hook
        llm_params = {"model": selected_model, "endpoint": ollama_endpoint}
        should_proceed = await _emit_before_llm_call(interpretation_prompt, llm_params, session_id)
        if not should_proceed:
            logger.info("[Issue #4259] LLM call cancelled by BEFORE_LLM_CALL hook")
            return

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

        # Issue #4259: Wire AFTER_LLM_RESPONSE hook
        if interpretation:
            interpretation = await _emit_after_llm_response(interpretation, llm_params, session_id)

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
        session_id: str = "",
    ):
        """Handle streaming interpretation request (Issue #332)."""
        import aiohttp

        # Issue #4259: Wire BEFORE_LLM_CALL hook
        llm_params = {"model": selected_model, "endpoint": ollama_endpoint}
        should_proceed = await _emit_before_llm_call(interpretation_prompt, llm_params, session_id)
        if not should_proceed:
            logger.info("[Issue #4259] LLM call cancelled by BEFORE_LLM_CALL hook")
            return

        http_client = get_http_client()
        full_response = ""
        try:
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
                        # Issue #4259: Wire DURING_LLM_STREAMING hook
                        await _emit_during_llm_streaming(chunk, session_id, {"endpoint": ollama_endpoint})
                        full_response += chunk
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
        finally:
            # Issue #4259: Wire AFTER_LLM_RESPONSE hook after streaming completes
            if full_response:
                full_response = await _emit_after_llm_response(full_response, llm_params, session_id)

    async def _interpret_command_results(
        self,
        command: str,
        stdout: str,
        stderr: str,
        return_code: int,
        ollama_endpoint: str,
        selected_model: str,
        streaming: bool = True,
        session_id: str = "",
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
            session_id: Session identifier for hooks

        Yields:
            WorkflowMessage chunks
        """
        interpretation_prompt = self._build_interpretation_prompt(command, stdout, stderr, return_code)
        llm_options = self._get_interpretation_llm_options()

        if not streaming:
            async for msg in self._interpret_non_streaming(
                ollama_endpoint,
                selected_model,
                interpretation_prompt,
                llm_options,
                session_id,
            ):
                yield msg
            return

        async for msg in self._interpret_streaming(
            ollama_endpoint,
            selected_model,
            interpretation_prompt,
            llm_options,
            session_id,
        ):
            yield msg

    async def _save_to_chat_history(self, session_id: str, interpretation: str) -> None:
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
            logger.info(f"[interpret_terminal_command] Saved interpretation " f"to chat session {session_id}")
        except Exception as e:
            logger.error(f"[interpret_terminal_command] Failed to save interpretation: {e}")

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
                self.redis_client.get(session_key),
                timeout=_ssot_config.timeout.redis_op,
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
            logger.warning(f"[interpret_terminal_command] Redis timeout getting session " f"data for {session_id}")
            return None

    async def _persist_to_conversation_history(self, session_id: str, interpretation: str) -> None:
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
                f"[interpret_terminal_command] Failed to persist to conversation " f"history: {persist_error}",
                exc_info=True,
            )

    async def _get_interpretation_from_llm(
        self,
        command: str,
        stdout: str,
        stderr: str,
        return_code: int,
        session_id: str = "",
    ) -> str:
        """Get LLM interpretation for command results (non-streaming)."""
        selected_model = get_config().get_selected_model()
        # Issue #1214: Try SLM discovery first, then config-based routing
        slm_base = await self._discover_ollama_from_slm()
        if slm_base:
            ollama_endpoint = slm_base
        else:
            ollama_endpoint = get_config().get_ollama_url_for_model(selected_model)

        logger.info(f"[interpret_terminal_command] Starting interpretation " f"for command: {command[:50]}...")

        interpretation = ""
        async for msg in self._interpret_command_results(
            command=command,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            ollama_endpoint=ollama_endpoint,
            selected_model=selected_model,
            streaming=False,
            session_id=session_id,
        ):
            if hasattr(msg, "content"):
                interpretation += msg.content

        logger.info(f"[interpret_terminal_command] Interpretation complete, " f"length: {len(interpretation)}")
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
            interpretation = await self._get_interpretation_from_llm(command, stdout, stderr, return_code, session_id)

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
