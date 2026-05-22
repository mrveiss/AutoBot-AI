# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Adapter - Adapter wrapping llm_providers.OllamaProvider (#1403).

Delegates execution to ``llm_providers.OllamaProvider`` which owns the
canonical Ollama implementation (OTel tracing via delegate, circuit breaker,
streaming).  This adapter's sole responsibility is the ``test_environment()``
diagnostic method used by ``api/adapters.py``.
"""

import json
import time
from typing import AsyncIterator, List

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_ollama_url
from constants.api_constants import PATH_OLLAMA_PULL, PATH_OLLAMA_TAGS

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = get_logger(__name__)


class OllamaAdapter(AdapterBase):
    """Adapter wrapping the canonical OllamaProvider (#1403)."""

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__("ollama", config)
        self._provider = None

    def _ensure_provider(self):
        """Lazily construct the canonical OllamaProvider."""
        if self._provider is None:
            from llm_shared.providers.ollama_provider import OllamaProvider

            base_url = self.config.settings.get("base_url")
            settings = {"base_url": base_url} if base_url else {}
            self._provider = OllamaProvider(settings=settings)
        return self._provider

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call via OllamaProvider."""
        provider = self._ensure_provider()
        return await provider.chat_completion(request)

    async def test_environment(self) -> EnvironmentTestResult:
        """Test Ollama connectivity and model availability."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()
        models: List[str] = []

        ollama_url = self.config.settings.get("base_url") or get_ollama_url()
        diagnostics.append(
            DiagnosticMessage(
                level=DiagnosticLevel.INFO,
                message=f"Ollama URL: {ollama_url}",
            )
        )

        try:
            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with await http_client.get(f"{ollama_url}{PATH_OLLAMA_TAGS}", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    diagnostics.append(
                        DiagnosticMessage(
                            level=DiagnosticLevel.INFO,
                            message=f"Found {len(models)} models",
                        )
                    )
                else:
                    diagnostics.append(
                        DiagnosticMessage(
                            level=DiagnosticLevel.ERROR,
                            message=f"HTTP {resp.status} from Ollama",
                        )
                    )
        except Exception as exc:  # Issue #3866: log so server-side errors are visible
            logger.warning("OllamaAdapter.test_environment() failed: %s", exc)
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="Connection failed",
                )
            )

        elapsed = time.time() - start
        healthy = any(d.level != DiagnosticLevel.ERROR for d in diagnostics) and len(models) > 0

        return EnvironmentTestResult(
            healthy=healthy,
            adapter_type="ollama",
            diagnostics=diagnostics,
            models_available=models,
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """Discover available Ollama models."""
        result = await self.test_environment()
        return result.models_available

    async def pull_model(self, model: str) -> AsyncIterator[dict]:
        """Pull an Ollama model with streaming progress events.

        Yields dicts with keys: status, digest (optional), total (optional),
        completed (optional), error (optional).
        """
        ollama_url = self.config.settings.get("base_url") or get_ollama_url()
        http_client = get_http_client()
        payload = {"model": model, "stream": True}
        try:
            async with await http_client.post(
                f"{ollama_url}{PATH_OLLAMA_PULL}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=None),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    yield {"status": "error", "error": f"HTTP {resp.status}: {body}"}
                    return
                async for raw_line in resp.content:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("OllamaAdapter.pull_model: non-JSON line: %s", line)
        except Exception as exc:
            logger.warning("OllamaAdapter.pull_model failed: %s", exc)
            yield {"status": "error", "error": str(exc)}


__all__ = ["OllamaAdapter"]
