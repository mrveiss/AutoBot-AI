# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anthropic Adapter - Adapter for external Anthropic API.

Issue #1403: Provides Claude model access via the Anthropic SDK.
"""

import logging
import os
import time
from typing import List, Optional

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = logging.getLogger(__name__)

ANTHROPIC_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-20250514",
    "claude-3-5-haiku-20241022",
]


class AnthropicAdapter(AdapterBase):
    """Adapter for the Anthropic Claude API (#1403)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("anthropic_api", config)
        self._api_key: Optional[str] = None
        self._client = None

    def _get_api_key(self) -> Optional[str]:
        """Resolve API key from config or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self.config.settings.get("api_key") or os.getenv(
            "ANTHROPIC_API_KEY", ""
        )
        return self._api_key

    def _ensure_client(self):
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            import anthropic

            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("Anthropic API key not configured")
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call via Anthropic API."""
        client = self._ensure_client()
        start = time.time()

        system_msg = ""
        messages = []
        for msg in request.messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                messages.append(
                    {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    }
                )

        kwargs = {
            "model": request.model_name or "claude-sonnet-4-6",
            "max_tokens": request.max_tokens or 4096,
            "messages": messages,
            "temperature": request.temperature,
        }
        if system_msg:
            kwargs["system"] = system_msg

        response = await client.messages.create(**kwargs)
        elapsed = time.time() - start

        content = ""
        if response.content:
            content = response.content[0].text

        return LLMResponse(
            content=content,
            model=response.model,
            provider="anthropic",
            processing_time=elapsed,
            request_id=request.request_id,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": (
                    response.usage.input_tokens + response.usage.output_tokens
                ),
            },
        )

    async def test_environment(self) -> EnvironmentTestResult:
        """Test Anthropic API connectivity."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()

        api_key = self._get_api_key()
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
            client = self._ensure_client()
            resp = await client.messages.count_tokens(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "test"}],
            )
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.INFO,
                    message="API authentication successful",
                    details={"input_tokens": resp.input_tokens},
                )
            )
        except Exception as e:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message=f"API call failed: {e}",
                )
            )

        elapsed = time.time() - start
        has_error = any(d.level == DiagnosticLevel.ERROR for d in diagnostics)

        return EnvironmentTestResult(
            healthy=not has_error,
            adapter_type="anthropic_api",
            diagnostics=diagnostics,
            models_available=ANTHROPIC_MODELS,
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """Return known Anthropic models."""
        return ANTHROPIC_MODELS


__all__ = ["AnthropicAdapter"]
