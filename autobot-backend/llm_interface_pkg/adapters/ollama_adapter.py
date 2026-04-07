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

import logging
import time
from typing import List, Optional

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.ssot_config import get_ollama_url
from constants.api_constants import PATH_OLLAMA_TAGS

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = logging.getLogger(__name__)


class OllamaAdapter(AdapterBase):
    """Adapter wrapping the canonical OllamaProvider (#1403)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("ollama", config)
        self._provider = None

    def _ensure_provider(self):
        """Lazily construct the canonical OllamaProvider."""
        if self._provider is None:
            from llm_providers.ollama_provider import OllamaProvider

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
            async with await http_client.get(
                f"{ollama_url}{PATH_OLLAMA_TAGS}", timeout=timeout
            ) as resp:
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
        except Exception:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="Connection failed",
                )
            )

        elapsed = time.time() - start
        healthy = (
            any(d.level != DiagnosticLevel.ERROR for d in diagnostics)
            and len(models) > 0
        )

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


__all__ = ["OllamaAdapter"]
