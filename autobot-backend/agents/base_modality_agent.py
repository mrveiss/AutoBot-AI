# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Base Modality Agent - Shared template for single-modality LLM agents.

Issue #12658: `process_query`/`_extract_content` were copy-pasted, byte-for-byte
identical (except for a handful of per-agent constants), across seven agents:
``audio_processing``, ``code_generation``, ``data_analysis``, ``image_analysis``,
``sentiment_analysis``, ``summarization``, and ``translation``.

This module owns the shared flow (call the vLLM-optimised chat API, extract the
response text, shape the success/error dict) as a template method. Each
subclass configures the handful of genuinely per-modality values via class
attributes (``QUERY_TEMPERATURE``, ``QUERY_MAX_TOKENS``, ``QUERY_ERROR_MESSAGE``,
``_LOGGER``) and may override the ``_after_success`` hook for post-processing
side effects (e.g. ``SentimentAnalysisAgent`` persists a diary entry).

Named ``base_modality_agent.py`` (not ``base_agent.py``) because
``agents/base_agent.py`` already exists as the framework-level ``BaseAgent``
that every agent (not just modality agents) inherits from.
"""

import uuid
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import LLMDefaults
from llm_shared.models import LLMResponse

from .standardized_agent import StandardizedAgent

logger = get_logger(__name__)


class BaseModalityAgent(StandardizedAgent):
    """Template-method base for single-modality query agents.

    Subclasses MUST set:
    - ``AGENT_ID``: str (already required by ``StandardizedAgent`` convention)
    - ``QUERY_TEMPERATURE``: float — LLM sampling temperature for this modality
    - ``QUERY_MAX_TOKENS``: int — LLM max_tokens for this modality
    - ``QUERY_ERROR_MESSAGE``: str — user-facing message returned on failure
    - ``_LOGGER``: the subclass module's own ``get_logger(__name__)`` instance,
      so log lines keep their original per-module logger name.

    Subclasses MAY override:
    - ``_after_success``: async hook called with the built success ``result``
      dict just before it is returned; default is a no-op passthrough.
    """

    QUERY_TEMPERATURE: float = 0.3
    QUERY_MAX_TOKENS: int = LLMDefaults.SYNTHESIS_MAX_TOKENS
    QUERY_ERROR_MESSAGE: str = "Error processing request. Please try again."
    _LOGGER = logger

    async def process_query(self, request_text: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Process a query using the vLLM-optimised API (Issue #3389)."""
        label = self.AGENT_ID.replace("_", " ").title()
        try:
            self._LOGGER.info("%s Agent processing: %s...", label, request_text[:50])
            session_id = (context or {}).get("session_id") or str(uuid.uuid4())
            response = await self.llm_interface.chat_optimized(
                agent_type=self.AGENT_ID,
                user_message=request_text,
                session_id=session_id,
                user_name=(context or {}).get("user_name"),
                user_role=(context or {}).get("user_role"),
                temperature=self.QUERY_TEMPERATURE,
                max_tokens=self.QUERY_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            result = {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": self.AGENT_ID,
                "model_used": self.model_name,
                "token_usage": self._extract_token_usage(response),
            }
            return await self._after_success(result, context or {}, session_id)
        except Exception as e:
            self._LOGGER.error("%s Agent error: %s", label, e)
            return {
                "status": "error",
                "response": self.QUERY_ERROR_MESSAGE,
                "response_text": str(e),
                "agent_type": self.AGENT_ID,
                "model_used": self.model_name,
            }

    async def _after_success(self, result: Dict[str, Any], context: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Hook for post-success side effects. Default is a no-op passthrough.

        Override to persist agent-specific state (e.g. SentimentAnalysisAgent's
        diary write) before the result is returned to the caller.
        """
        return result

    def _extract_content(self, response: Any) -> str:
        """Extract text content from LLM response.

        Issue #14559: ``chat_optimized`` — the only thing ``process_query``
        calls — always returns an ``LLMResponse`` dataclass, on every one of
        its return paths (cache hit, provider-missing error, request
        exception, and the normal success path). It is neither a ``str`` nor
        a ``dict``, so that branch is added here rather than replacing the
        pre-existing ones, which stay for any caller that still hands this
        method a raw provider payload.
        """
        if isinstance(response, str):
            return response.strip()
        if isinstance(response, LLMResponse):
            return (response.content or "").strip()
        if isinstance(response, dict):
            msg = response.get("message", {})
            if isinstance(msg, dict) and msg.get("content"):
                return msg["content"].strip()
            choices = response.get("choices", [])
            if choices and isinstance(choices[0], dict):
                choice_msg = choices[0].get("message", {})
                if isinstance(choice_msg, dict) and choice_msg.get("content"):
                    return choice_msg["content"].strip()
            if "content" in response:
                return str(response["content"]).strip()
            return str(response)
        # Issue #14559: a genuinely unrecognized shape used to fall through to
        # `str(response)`, which always succeeds and hides the defect behind a
        # plausible-looking string (e.g. a dataclass repr). Fail loudly instead;
        # `process_query`'s `except Exception` turns this into a proper error
        # result rather than a silent content leak.
        raise TypeError(
            f"{self.AGENT_ID}: _extract_content got an unrecognized LLM response "
            f"type {type(response).__name__!r}; expected str, dict, or LLMResponse"
        )

    def _extract_token_usage(self, response: Any) -> Dict[str, Any]:
        """Extract token usage accounting from an LLM response.

        Mirrors `_extract_content`'s shape handling: `LLMResponse.usage` is
        the real producer shape (Issue #14559); the dict branch is kept for
        any raw provider payload still passed through.
        """
        if isinstance(response, LLMResponse):
            return response.usage or {}
        if isinstance(response, dict):
            return response.get("usage", {})
        return {}
