# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Google Cloud Vertex AI provider for the multi-provider LLM layer (GH#9009).

Supports Gemini models (2.5 Pro/Flash, 2.0 Flash, 1.5 Pro/Flash) and Claude
models (3.x/4.x) routed through the Vertex AI endpoint.

Auth (in priority order):
  1. ``settings["service_account_json"]`` — JSON string of a GCP service account key
  2. Application Default Credentials (ADC) — used when no JSON key is provided;
     set ``GOOGLE_APPLICATION_CREDENTIALS`` or run ``gcloud auth application-default login``

Config keys (all optional with sensible defaults):
  - ``project``               — GCP project ID (falls back to ``VERTEX_AI_PROJECT``)
  - ``location``              — Region, e.g. ``us-central1`` (falls back to ``VERTEX_AI_LOCATION``)
  - ``service_account_json``  — Service account JSON string (empty → ADC)
  - ``default_model``         — Model used when request carries none

Streaming: fully supported for both Gemini and Claude on Vertex.
Cost tracking: uses the ``vertexai`` pricing source (GH#9009).
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider
from .cache_utils import sorted_for_cache

logger = get_logger(__name__)

_DEFAULT_LOCATION = "us-central1"
_DEFAULT_MODEL = "gemini-2.5-flash"

# Models routed through AnthropicVertex instead of the vertexai SDK.
_CLAUDE_MODEL_PREFIXES = ("claude-",)

_VERTEX_GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

_VERTEX_CLAUDE_MODELS = [
    "claude-opus-4@20251101",
    "claude-sonnet-4-5@20251101",
    "claude-3-5-sonnet-v2@20241022",
    "claude-3-5-haiku@20241022",
    "claude-3-opus@20240229",
]

VERTEX_MODELS = _VERTEX_GEMINI_MODELS + _VERTEX_CLAUDE_MODELS


def _is_claude_model(model: str) -> bool:
    return any(model.startswith(p) for p in _CLAUDE_MODEL_PREFIXES)


class VertexAIProvider(BaseProvider):
    """
    Google Cloud Vertex AI provider.

    Routes Gemini models through the ``google-cloud-aiplatform`` (``vertexai``)
    SDK and Claude models through the ``anthropic`` SDK's ``AnthropicVertex``
    client.  Both clients are lazily initialized on first use.

    Requires:
      - ``pip install google-cloud-aiplatform`` (for Gemini)
      - ``pip install anthropic[vertex]`` (for Claude on Vertex)
    """

    provider_name = ProviderType.VERTEX_AI.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._project: str | None = None
        self._location: str | None = None
        self._credentials = None  # google.auth credentials object
        self._vertexai_initialized = False
        self._anthropic_vertex_client = None

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    def _resolve_project(self) -> str:
        if self._project:
            return self._project
        self._project = self._get_setting("project") or config.vertex_ai_project or ""
        return self._project

    def _resolve_location(self) -> str:
        if self._location:
            return self._location
        self._location = self._get_setting("location") or config.vertex_ai_location or _DEFAULT_LOCATION
        return self._location

    def _resolve_credentials(self):
        """Return google.auth Credentials from service account JSON, or None for ADC."""
        if self._credentials is not None:
            return self._credentials

        sa_json = self._get_setting("service_account_json") or config.vertex_ai_service_account_json
        if not sa_json:
            return None  # ADC path

        try:
            from google.oauth2 import service_account  # type: ignore[import]

            info = json.loads(sa_json)
            self._credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        except Exception as exc:
            raise ValueError(f"Failed to parse VERTEX_AI_SERVICE_ACCOUNT_JSON: {exc}") from exc

        return self._credentials

    # ------------------------------------------------------------------
    # Client initialization
    # ------------------------------------------------------------------

    def _ensure_vertexai(self) -> None:
        """Initialize the vertexai SDK (idempotent)."""
        if self._vertexai_initialized:
            return
        try:
            import vertexai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-cloud-aiplatform not installed. Run: pip install google-cloud-aiplatform"
            ) from exc

        project = self._resolve_project()
        location = self._resolve_location()
        credentials = self._resolve_credentials()

        kwargs: Dict[str, Any] = {}
        if project:
            kwargs["project"] = project
        if location:
            kwargs["location"] = location
        if credentials is not None:
            kwargs["credentials"] = credentials

        vertexai.init(**kwargs)
        self._vertexai_initialized = True
        logger.debug("Vertex AI SDK initialized (project=%s, location=%s)", project, location)

    def _ensure_anthropic_vertex_client(self):
        """Lazily initialize the AnthropicVertex client for Claude-on-Vertex calls."""
        if self._anthropic_vertex_client is not None:
            return self._anthropic_vertex_client
        try:
            from anthropic import AsyncAnthropicVertex  # type: ignore[import]
        except ImportError as exc:
            raise ImportError("anthropic[vertex] not installed. Run: pip install 'anthropic[vertex]'") from exc

        project = self._resolve_project()
        location = self._resolve_location()

        if not project:
            raise ValueError(
                "VERTEX_AI_PROJECT must be set to use Claude on Vertex AI. "
                "Set vertex_ai_project in provider settings or VERTEX_AI_PROJECT env var."
            )

        self._anthropic_vertex_client = AsyncAnthropicVertex(
            project_id=project,
            region=location,
        )
        return self._anthropic_vertex_client

    # ------------------------------------------------------------------
    # Gemini completion helpers
    # ------------------------------------------------------------------

    def _build_gemini_contents(self, messages: list) -> tuple[str, list]:
        """Split messages into system instruction + Gemini contents list."""
        from vertexai.generative_models import Content, Part  # type: ignore[import]

        system_parts: list[str] = []
        contents: list[Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_parts.append(text)
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append(Content(role=gemini_role, parts=[Part.from_text(text)]))

        return "\n".join(system_parts), contents

    async def _gemini_chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming Gemini completion via vertexai SDK."""
        from vertexai.generative_models import GenerationConfig, GenerativeModel  # type: ignore[import]

        model_name = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        start = time.time()
        try:
            self._ensure_vertexai()
            system_instruction, contents = self._build_gemini_contents(request.messages)

            gen_config = GenerationConfig(
                max_output_tokens=request.max_tokens or 8192,
                temperature=request.temperature,
            )

            model_kwargs: Dict[str, Any] = {}
            if system_instruction:
                model_kwargs["system_instruction"] = system_instruction

            model = GenerativeModel(model_name, **model_kwargs)
            response = await model.generate_content_async(
                contents,
                generation_config=gen_config,
            )

            content = response.text
            usage_meta = response.usage_metadata
            prompt_tokens = getattr(usage_meta, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage_meta, "candidates_token_count", 0) or 0
            total_tokens = prompt_tokens + output_tokens

            return LLMResponse(
                content=content,
                model=model_name,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                provider_metadata=self._build_provider_metadata(
                    model_api_name=model_name,
                    api_kwargs_applied=sorted_for_cache({"model": model_name}),
                    total_tokens=total_tokens,
                ),
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("VertexAI Gemini chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model_name,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def _gemini_stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Streaming Gemini completion via vertexai SDK."""
        from vertexai.generative_models import GenerationConfig, GenerativeModel  # type: ignore[import]

        model_name = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        self._ensure_vertexai()
        system_instruction, contents = self._build_gemini_contents(request.messages)

        gen_config = GenerationConfig(
            max_output_tokens=request.max_tokens or 8192,
            temperature=request.temperature,
        )

        model_kwargs: Dict[str, Any] = {}
        if system_instruction:
            model_kwargs["system_instruction"] = system_instruction

        model = GenerativeModel(model_name, **model_kwargs)
        async for chunk in await model.generate_content_async(
            contents,
            generation_config=gen_config,
            stream=True,
        ):
            if chunk.text:
                yield chunk.text

    # ------------------------------------------------------------------
    # Claude-on-Vertex completion helpers
    # ------------------------------------------------------------------

    def _split_messages_for_anthropic(self, messages: list) -> tuple[str, list]:
        """Separate system message from conversational messages."""
        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        return system_content, chat_messages

    async def _claude_chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming Claude-on-Vertex completion via AnthropicVertex."""
        model_name = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        start = time.time()
        try:
            client = self._ensure_anthropic_vertex_client()
            system_content, chat_messages = self._split_messages_for_anthropic(request.messages)

            kwargs: Dict[str, Any] = {
                "model": model_name,
                "max_tokens": request.max_tokens or 4096,
                "messages": chat_messages,
                "temperature": request.temperature,
            }
            if system_content:
                kwargs["system"] = system_content

            api_kwargs: Dict[str, Any] = request.metadata.get("api_kwargs") or {}
            for key, value in api_kwargs.items():
                if key not in {"preserve_reasoning", "extra_headers", "betas"}:
                    kwargs[key] = value

            call_kwargs = sorted_for_cache(kwargs)
            response = await client.messages.create(**call_kwargs)

            content = ""
            tool_calls: List[ToolCall] = []
            for block in response.content:
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    content += getattr(block, "text", "")
                elif block_type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        )
                    )

            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            finish_reason = "tool_calls" if tool_calls else response.stop_reason

            return LLMResponse(
                content=content,
                model=response.model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                finish_reason=finish_reason,
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": total_tokens,
                },
                tool_calls=tool_calls or None,
                provider_metadata=self._build_provider_metadata(
                    model_api_name=response.model,
                    api_kwargs_applied=call_kwargs,
                    total_tokens=total_tokens,
                ),
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("VertexAI Claude chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model_name,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def _claude_stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Streaming Claude-on-Vertex completion via AnthropicVertex."""
        model_name = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        client = self._ensure_anthropic_vertex_client()
        system_content, chat_messages = self._split_messages_for_anthropic(request.messages)

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "max_tokens": request.max_tokens or 4096,
            "messages": chat_messages,
            "temperature": request.temperature,
        }
        if system_content:
            kwargs["system"] = system_content

        api_kwargs: Dict[str, Any] = request.metadata.get("api_kwargs") or {}
        for key, value in api_kwargs.items():
            if key not in {"preserve_reasoning", "extra_headers", "betas"}:
                kwargs[key] = value

        call_kwargs = sorted_for_cache(kwargs)
        async with client.messages.stream(**call_kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        if _is_claude_model(model):
            return await self._claude_chat_completion(request)
        return await self._gemini_chat_completion(request)

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        try:
            if _is_claude_model(model):
                async for chunk in self._claude_stream_completion(request):
                    yield chunk
            else:
                async for chunk in self._gemini_stream_completion(request):
                    yield chunk
        except Exception as exc:
            self._total_errors += 1
            logger.error("VertexAI stream_completion error: %s", exc)
            raise

    async def is_available(self) -> bool:
        """Return True when the vertexai SDK can be imported and a project is configured."""
        try:
            import vertexai  # type: ignore[import]  # noqa: F401
        except ImportError:
            return False
        project = self._resolve_project()
        if not project:
            logger.debug("VERTEX_AI_PROJECT not set — VertexAI provider unavailable")
            return False
        return True

    async def list_models(self) -> List[str]:
        return list(VERTEX_MODELS)


__all__ = [
    "VertexAIProvider",
    "VERTEX_MODELS",
    "_VERTEX_GEMINI_MODELS",
    "_VERTEX_CLAUDE_MODELS",
]
