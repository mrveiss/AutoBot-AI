# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
HuggingFace Inference API provider for the multi-provider LLM layer (#1806).

Uses the HuggingFace Inference API (https://api-inference.huggingface.co)
to run open models hosted on the Hub without local GPU resources.

API token is read (in priority order) from:
  1. ``settings["api_token"]``
  2. Environment variable ``HF_TOKEN``
  3. Environment variable ``HUGGINGFACE_API_TOKEN`` (legacy name)

API tokens are never logged.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from autobot_shared.http_client import get_http_client
from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

_HF_BASE_URL = "https://api-inference.huggingface.co"

# Popular open models that work well with the chat-completion endpoint.
_KNOWN_CHAT_MODELS: List[str] = [
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "mistralai/Mixtral-8x7B-Instruct-v0.1",
    "microsoft/Phi-3-mini-4k-instruct",
    "HuggingFaceH4/zephyr-7b-beta",
    "google/gemma-2-9b-it",
]


class HuggingFaceProvider(BaseProvider):
    """
    HuggingFace Inference API provider.

    Calls the serverless inference endpoint for text-generation models
    via the OpenAI-compatible ``/v1/chat/completions`` route introduced
    in the Inference API v3 (requires a valid HF token for gated models).
    """

    provider_name = ProviderType.HUGGINGFACE.value

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(settings)
        self._api_token: Optional[str] = None

    def _resolve_api_token(self) -> Optional[str]:
        """Resolve HF token from settings or environment."""
        if self._api_token:
            return self._api_token
        self._api_token = (
            self._get_setting("api_token")
            or os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACE_API_TOKEN")
        )
        return self._api_token

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers, injecting the HF token when available."""
        headers = {"Content-Type": "application/json"}
        token = self._resolve_api_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _build_chat_payload(self, request: LLMRequest, model: str) -> Dict[str, Any]:
        """Build the OpenAI-compatible chat completion payload."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = request.stop
        return payload

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via HuggingFace Inference API."""
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting(
            "default_model", "meta-llama/Llama-3.2-3B-Instruct"
        )
        url = f"{_HF_BASE_URL}/v1/chat/completions"
        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=request.timeout or 60)
            async with await http_client.post(
                url,
                headers=self._build_headers(),
                json=self._build_chat_payload(request, model),
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"HuggingFace API returned HTTP {resp.status}: {body}"
                    )
                data = await resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return LLMResponse(
                content=choice["message"]["content"] or "",
                model=data.get("model", model),
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                finish_reason=choice.get("finish_reason", "stop"),
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("HuggingFace chat_completion error for %s: %s", model, exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from HuggingFace, yielding text chunks."""
        self._total_requests += 1
        model = request.model_name or self._get_setting(
            "default_model", "meta-llama/Llama-3.2-3B-Instruct"
        )
        url = f"{_HF_BASE_URL}/v1/chat/completions"
        payload = self._build_chat_payload(request, model)
        payload["stream"] = True
        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=None, connect=5.0, sock_read=None)
            async with await http_client.post(
                url,
                headers=self._build_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"HuggingFace stream returned HTTP {resp.status}: {body}"
                    )
                async for line in resp.content:
                    decoded = line.decode("utf-8").strip()
                    if decoded.startswith("data: "):
                        chunk_json = decoded[6:]
                        if chunk_json == "[DONE]":
                            break
                        import json
                        chunk = json.loads(chunk_json)
                        delta = chunk["choices"][0].get("delta", {}).get("content")
                        if delta:
                            yield delta
        except Exception as exc:
            self._total_errors += 1
            logger.error("HuggingFace stream_completion error for %s: %s", model, exc)
            raise

    async def is_available(self) -> bool:
        """
        Return True if the HF Inference API is reachable.

        Sends a lightweight HEAD to the base URL; no inference is triggered.
        """
        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with await http_client.get(
                f"{_HF_BASE_URL}/status",
                timeout=timeout,
            ) as resp:
                return resp.status < 500
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Return a curated list of well-supported chat models on HuggingFace."""
        return list(_KNOWN_CHAT_MODELS)


__all__ = ["HuggingFaceProvider"]
