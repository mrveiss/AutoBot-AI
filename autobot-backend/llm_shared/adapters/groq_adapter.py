# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Groq Adapter - Adapter for the Groq inference API (#4096).

Delegates execution to ``llm_providers.GroqProvider`` which owns the canonical
Groq implementation (async client, streaming, fallback model list).  This
adapter's sole responsibility is the ``test_environment()`` diagnostic method
used by ``api/adapters.py``.
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


class GroqAdapter(AdapterBase):
    """Adapter for the Groq inference API (#4096).

    All inference is delegated to ``llm_providers.GroqProvider`` so there is a
    single implementation of the Groq request/response logic.
    """

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__("groq_api", config)
        self._provider = None

    def _ensure_provider(self):
        """Lazily construct the canonical GroqProvider."""
        if self._provider is None:
            from llm_shared.providers.groq import GroqProvider

            api_key = self.config.settings.get("api_key") or config.groq_api_key
            self._provider = GroqProvider(settings={"api_key": api_key} if api_key else {})
        return self._provider

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call via GroqProvider."""
        provider = self._ensure_provider()
        return await provider.chat_completion(request)

    async def test_environment(self) -> EnvironmentTestResult:
        """Test Groq API connectivity."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()

        api_key = self.config.settings.get("api_key") or config.groq_api_key
        if not api_key:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="Groq API key not configured",
                )
            )
            return EnvironmentTestResult(
                healthy=False,
                adapter_type="groq_api",
                diagnostics=diagnostics,
                response_time=time.time() - start,
            )

        diagnostics.append(
            DiagnosticMessage(
                level=DiagnosticLevel.INFO,
                message="API key configured",
            )
        )

        models: List[str] = []
        try:
            provider = self._ensure_provider()
            models = await provider.list_models()
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.INFO,
                    message=f"Found {len(models)} models",
                )
            )
        except Exception as exc:
            logger.warning("GroqAdapter.test_environment() failed: %s", exc)
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
            adapter_type="groq_api",
            diagnostics=diagnostics,
            models_available=models or await self.list_models(),
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """Return known Groq models, discovering live models when the key is set."""
        try:
            provider = self._ensure_provider()
            return await provider.list_models()
        except Exception:
            from llm_shared.providers.groq import GROQ_MODELS

            return list(GROQ_MODELS)


__all__ = ["GroqAdapter"]
