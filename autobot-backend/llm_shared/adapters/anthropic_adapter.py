# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Anthropic Adapter - Adapter for external Anthropic API (#1403).

Delegates execution to ``llm_shared.providers.anthropic.AnthropicProvider``
which owns the canonical Claude implementation (extended thinking, beta headers,
think-block stripping, OTel tracing).  This adapter's sole responsibility is the
``test_environment()`` diagnostic method used by ``api/adapters.py``.
"""

import time
from typing import List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = get_logger(__name__)


class AnthropicAdapter(AdapterBase):
    """Adapter for the Anthropic Claude API (#1403).

    All inference is delegated to ``llm_providers.AnthropicProvider`` so there
    is a single implementation of the Anthropic request/response logic.
    """

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__("anthropic_api", config)
        self._provider = None

    def _ensure_provider(self):
        """Lazily construct the canonical AnthropicProvider."""
        if self._provider is None:
            from llm_shared.providers.anthropic import AnthropicProvider

            api_key = self.config.settings.get("api_key") or config.anthropic_api_key
            self._provider = AnthropicProvider(settings={"api_key": api_key} if api_key else {})
        return self._provider

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call via AnthropicProvider."""
        provider = self._ensure_provider()
        return await provider.chat_completion(request)

    async def test_environment(self) -> EnvironmentTestResult:
        """Test Anthropic API connectivity."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()

        api_key = self.config.settings.get("api_key") or config.anthropic_api_key
        if not api_key:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="Anthropic API key not configured",
                )
            )
            return EnvironmentTestResult(
                healthy=False,
                adapter_type="anthropic_api",
                diagnostics=diagnostics,
                response_time=time.time() - start,
            )

        diagnostics.append(
            DiagnosticMessage(
                level=DiagnosticLevel.INFO,
                message="API key configured",
            )
        )

        try:
            provider = self._ensure_provider()
            available = await provider.is_available()
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.INFO if available else DiagnosticLevel.ERROR,
                    message="API authentication successful" if available else "API check failed",
                )
            )
        except Exception as exc:  # Issue #3866: log so server-side errors are visible
            logger.warning("AnthropicAdapter.test_environment() failed: %s", exc)
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="API call failed",
                )
            )

        elapsed = time.time() - start
        has_error = any(d.level == DiagnosticLevel.ERROR for d in diagnostics)

        return EnvironmentTestResult(
            healthy=not has_error,
            adapter_type="anthropic_api",
            diagnostics=diagnostics,
            models_available=await self.list_models(),
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """Return known Anthropic models (delegated to provider)."""
        try:
            provider = self._ensure_provider()
            return await provider.list_models()
        except Exception:
            from llm_shared.providers.anthropic import _ANTHROPIC_MODELS

            return list(_ANTHROPIC_MODELS)


__all__ = ["AnthropicAdapter"]
