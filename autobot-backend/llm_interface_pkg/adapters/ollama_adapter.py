# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Adapter - Wraps existing OllamaProvider for the adapter registry.

Issue #1403: Delegates to OllamaProvider for execution, adds
test_environment and list_models capabilities.
"""

import logging
import time
from typing import List, Optional

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.ssot_config import get_ollama_url

from ..models import LLMRequest, LLMResponse, LLMSettings
from ..streaming import StreamingManager
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = logging.getLogger(__name__)


class OllamaAdapter(AdapterBase):
    """Adapter wrapping the existing OllamaProvider (#1403)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("ollama", config)
        self._provider = None
        self._settings = LLMSettings()
        self._streaming_manager = StreamingManager()

    def _ensure_provider(self):
        """Lazily initialize the OllamaProvider."""
        if self._provider is None:
            from ..providers.ollama import OllamaProvider

            self._provider = OllamaProvider(self._settings, self._streaming_manager)
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

        ollama_url = get_ollama_url()
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
                f"{ollama_url}/api/tags", timeout=timeout
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
        except Exception as e:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message=f"Connection failed: {e}",
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
