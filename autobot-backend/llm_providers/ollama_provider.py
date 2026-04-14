# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama provider for the multi-provider LLM layer (#1806).

Delegates chat_completion to ``llm_interface_pkg.providers.ollama.OllamaProvider``
which carries OpenTelemetry tracing (Issue #697) and circuit breaker protection.
stream_completion is implemented directly for true incremental chunk delivery
(the delegate accumulates the full stream before returning).

The base URL is read (in priority order) from:
  1. ``settings["base_url"]``
  2. SSOT config (``autobot_shared.ssot_config.get_ollama_url()``)
  3. Environment variable ``AUTOBOT_OLLAMA_ENDPOINT``
  4. Hard default: ``http://127.0.0.1:11434``
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.ssot_config import get_ollama_url
from constants.api_constants import PATH_OLLAMA_CHAT, PATH_OLLAMA_GENERATE, PATH_OLLAMA_TAGS
from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider
from .chat_template_loader import render_chat_template

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    """
    Ollama provider implementation conforming to BaseProvider.

    Delegates to the existing llm_interface_pkg OllamaProvider for actual
    inference and streaming while exposing the uniform BaseProvider interface
    required by the ProviderRegistry.
    """

    provider_name = ProviderType.OLLAMA.value

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(settings)
        self._base_url: Optional[str] = None
        self._delegate = None

    def _resolve_base_url(self) -> str:
        """Resolve the Ollama base URL from settings, SSOT config, or env."""
        if self._base_url:
            return self._base_url
        self._base_url = self._get_setting("base_url") or get_ollama_url()
        return self._base_url

    def _ensure_delegate(self):
        """
        Lazily construct the llm_interface_pkg OllamaProvider delegate.

        This avoids importing heavy modules at import time and respects the
        lazy-init pattern used elsewhere in the codebase.
        """
        if self._delegate is not None:
            return self._delegate
        from llm_interface_pkg.models import LLMSettings
        from llm_interface_pkg.providers.ollama import OllamaProvider as _OllamaProvider
        from llm_interface_pkg.streaming import StreamingManager

        settings = LLMSettings()
        streaming_manager = StreamingManager()
        self._delegate = _OllamaProvider(
            settings=settings,
            streaming_manager=streaming_manager,
        )
        # Patch the host so it respects our resolved URL
        self._delegate.ollama_host = self._resolve_base_url()
        return self._delegate

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Delegate to llm_interface_pkg OllamaProvider (carries OTel tracing + circuit breaker).

        The delegate's ``_prepare_chat_request`` calls ``get_host_from_env()``
        which reads from SSOT config; we override ``ollama_host`` immediately
        before the call so any settings["base_url"] override is honoured.

        When ``request.metadata["chat_template"]`` is set the messages are
        rendered via Jinja2 before being forwarded so local models receive a
        properly formatted prompt regardless of their native template support.
        """
        self._total_requests += 1
        try:
            chat_template = request.metadata.get("chat_template")
            if chat_template:
                # Issue #4525: when a chat_template is set, render messages to a
                # prompt string and POST to /api/generate directly.  Collapsing to a
                # single {"role":"user"} message and forwarding to /api/chat is
                # semantically wrong — it discards conversation structure.
                # stream_completion already uses this pattern correctly.
                base_url = self._resolve_base_url()
                model = request.model_name or self._get_setting("default_model", "")
                raw_messages = [
                    {"role": m["role"], "content": m["content"]}
                    if isinstance(m, dict)
                    else {"role": m.role, "content": m.content}
                    for m in request.messages
                ]
                prompt = render_chat_template(raw_messages, chat_template)
                payload: Dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": request.temperature},
                }
                if request.max_tokens:
                    payload["options"]["num_predict"] = request.max_tokens

                import json as _json
                http_client = get_http_client()
                timeout = aiohttp.ClientTimeout(total=None, connect=5.0, sock_read=None)
                async with await http_client.post(
                    f"{base_url}{PATH_OLLAMA_GENERATE}",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Ollama generate returned HTTP {resp.status}: {body}")
                    data = await resp.json()
                content = data.get("response", "")
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                }
                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.provider_name,
                    processing_time=data.get("total_duration", 0) / 1e9,
                    request_id=request.request_id,
                    usage=usage,
                    provider_metadata=self._build_provider_metadata(
                        model_api_name=model,
                        api_kwargs_applied=payload,
                        total_tokens=usage["total_tokens"],
                    ),
                )

            delegate = self._ensure_delegate()
            # Override host so settings["base_url"] is respected over SSOT env default.
            delegate.ollama_host = self._resolve_base_url()
            response = await delegate.chat_completion(request)
            if response.error:
                self._total_errors += 1
            else:
                api_kwargs = {
                    "model": response.model,
                    "messages": request.messages,
                    "options": {"temperature": request.temperature},
                }
                response.provider_metadata = self._build_provider_metadata(
                    model_api_name=response.model,
                    api_kwargs_applied=api_kwargs,
                    total_tokens=response.usage.get("total_tokens") if response.usage else None,
                )
            return response
        except Exception as exc:
            self._total_errors += 1
            logger.error("OllamaProvider delegation error: %s", exc)
            return LLMResponse(
                content="",
                model=request.model_name or "",
                provider=self.provider_name,
                processing_time=0.0,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream from Ollama by issuing an SSE-style request directly.

        The llm_interface_pkg OllamaProvider accumulates the full stream
        internally; for true incremental streaming we post directly.
        """
        self._total_requests += 1
        base_url = self._resolve_base_url()
        model = request.model_name or self._get_setting("default_model", "")
        if not model:
            raise ValueError("No model specified for Ollama streaming")
        chat_template = request.metadata.get("chat_template")
        if chat_template:
            # Render messages via Jinja2 template and use raw prompt API.
            raw_messages = [
                {"role": m["role"], "content": m["content"]}
                if isinstance(m, dict)
                else {"role": m.role, "content": m.content}
                for m in request.messages
            ]
            prompt = render_chat_template(raw_messages, chat_template)
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": True,
                "options": {"temperature": request.temperature},
            }
        else:
            payload = {
                "model": model,
                "messages": request.messages,
                "stream": True,
                "options": {"temperature": request.temperature},
            }
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens
        try:
            import json as _json

            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=None, connect=5.0, sock_read=None)
            async with await http_client.post(
                f"{base_url}{PATH_OLLAMA_CHAT}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Ollama stream returned HTTP {resp.status}: {body}"
                    )
                async for line in resp.content:
                    decoded = line.decode("utf-8").strip()
                    if not decoded:
                        continue
                    chunk = _json.loads(decoded)
                    # /api/chat returns message.content; /api/generate returns response
                    text = (
                        chunk.get("message", {}).get("content", "")
                        or chunk.get("response", "")
                    )
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
        except Exception as exc:
            self._total_errors += 1
            logger.error("Ollama stream_completion error: %s", exc)
            raise

    async def is_available(self) -> bool:
        """Return True if the Ollama /api/tags endpoint responds with HTTP 200."""
        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with await http_client.get(
                f"{self._resolve_base_url()}{PATH_OLLAMA_TAGS}",
                timeout=timeout,
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Discover locally available models via the Ollama /api/tags endpoint."""
        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=10.0)
            async with await http_client.get(
                f"{self._resolve_base_url()}{PATH_OLLAMA_TAGS}",
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Failed to list Ollama models: %s", exc)
        return []


__all__ = ["OllamaProvider"]
