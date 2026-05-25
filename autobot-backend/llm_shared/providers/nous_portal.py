# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Nous Portal Provider - Access Nous Research's curated open-source LLM models.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

Configuration:
  - api_key: HuggingFace API token or custom endpoint key
  - base_url: Custom API base URL (e.g., for self-hosted Nous models)
  - default_model: Default model name

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from llm_shared.models import LLMRequest, LLMResponse

from ..base_provider import BaseProvider

logger = get_logger(__name__)

NOUS_MODELS = [
    "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
    "NousResearch/Nous-Hermes-2-Mistral-7B-DPO",
    "NousResearch/Nous-Hermes-2-Vision-7B",
    "NousResearch/Nous-Hermes-Llama2-7b",
    "NousResearch/Nous-Hermes-Llama2-13b",
]


class NousPortalProvider(BaseProvider):
    """
    Nous Portal provider implementation.

    Provides access to curated open-source LLM models from Nous Research.
    Requires: openai package (pip install openai)
              HF_TOKEN or custom API key in environment
    """

    provider_name = "nous"

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._client = None

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        key = self._get_setting("api_key") or config.hf_token or config.huggingface_api_token or config.nous_api_key
        self._api_key = key
        return self._api_key

    def _resolve_base_url(self) -> str:
        """Resolve base URL with defaults."""
        if self._base_url:
            return self._base_url
        url = self._get_setting("base_url") or config.nous_api_base_url or "https://api-inference.huggingface.co/v1"
        self._base_url = url
        return url

    def _ensure_client(self):
        """Lazily initialize the async OpenAI client."""
        if self._client is not None:
            return

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc

        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError("Nous API key not found. Set HF_TOKEN or provide api_key in settings.")

        base_url = self._resolve_base_url()
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info("Nous Portal client initialized with base_url: %s", base_url)

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion via Nous models."""
        try:
            self._total_requests += 1
            self._ensure_client()

            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            api_kwargs = request.metadata.get("api_kwargs", {})
            chat_kwargs = {
                "model": request.model_name or self._get_setting("default_model", NOUS_MODELS[0]),
                "messages": messages,
                "temperature": api_kwargs.get("temperature", 0.7),
                "max_tokens": api_kwargs.get("max_tokens", 2048),
                "top_p": api_kwargs.get("top_p", 0.95),
            }

            if "presence_penalty" in api_kwargs:
                chat_kwargs["presence_penalty"] = api_kwargs["presence_penalty"]
            if "frequency_penalty" in api_kwargs:
                chat_kwargs["frequency_penalty"] = api_kwargs["frequency_penalty"]
            if "stop" in api_kwargs:
                chat_kwargs["stop"] = api_kwargs["stop"]

            response = await self._client.chat.completions.create(**chat_kwargs)

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            }

            return LLMResponse(
                content=content,
                model_name=request.model_name or chat_kwargs["model"],
                provider_name=self.provider_name,
                usage=usage,
                provider_metadata=self._build_provider_metadata(
                    model_api_name=chat_kwargs["model"],
                    api_kwargs_applied=chat_kwargs,
                    total_tokens=usage["prompt_tokens"] + usage["completion_tokens"],
                ),
            )

        except Exception as exc:
            self._total_errors += 1
            error_msg = f"Nous API error: {exc}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                model_name=request.model_name or "nous-model",
                provider_name=self.provider_name,
                error=error_msg,
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from Nous models."""
        try:
            self._total_requests += 1
            self._ensure_client()

            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            api_kwargs = request.metadata.get("api_kwargs", {})
            chat_kwargs = {
                "model": request.model_name or self._get_setting("default_model", NOUS_MODELS[0]),
                "messages": messages,
                "temperature": api_kwargs.get("temperature", 0.7),
                "max_tokens": api_kwargs.get("max_tokens", 2048),
                "top_p": api_kwargs.get("top_p", 0.95),
                "stream": True,
            }

            if "stop" in api_kwargs:
                chat_kwargs["stop"] = api_kwargs["stop"]

            async with await self._client.chat.completions.create(**chat_kwargs) as stream:
                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

        except Exception as exc:
            self._total_errors += 1
            logger.error("Nous stream error: %s", exc)
            yield f"Error: {exc}"

    async def is_available(self) -> bool:
        """Check if Nous Portal is reachable and properly configured."""
        try:
            self._ensure_client()
            await self._client.models.list()
            return True
        except Exception as exc:
            logger.warning("Nous health check failed: %s", exc)
            return False

    async def list_models(self) -> List[str]:
        """List available Nous Research models."""
        try:
            self._ensure_client()
            response = await self._client.models.list()
            return [model.id for model in response.data] if response.data else NOUS_MODELS
        except Exception:
            logger.debug("Could not fetch Nous models from API; using defaults")
            return NOUS_MODELS


__all__ = ["NousPortalProvider", "NOUS_MODELS"]
