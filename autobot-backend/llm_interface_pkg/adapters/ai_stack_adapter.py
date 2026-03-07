# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI Stack Adapter - Wraps AIStackClient for the adapter registry.

Issue #1403: Routes LLM requests through AI Stack VM (.24).
"""

import logging
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


class AIStackAdapter(AdapterBase):
    """Adapter wrapping the existing AIStackClient (#1403)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("ai_stack", config)
        self._client = None

    async def _ensure_client(self):
        """Lazily get the global AIStackClient."""
        if self._client is None:
            from services.ai_stack_client import get_ai_stack_client

            self._client = await get_ai_stack_client()
        return self._client

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call via AI Stack chat agent."""
        client = await self._ensure_client()
        start = time.time()

        user_msg = ""
        chat_history = []
        for msg in request.messages:
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
            chat_history.append(msg)

        result = await client.chat_message(
            message=user_msg,
            chat_history=chat_history[:-1] if chat_history else [],
        )

        elapsed = time.time() - start
        content = result.get("response", result.get("content", ""))

        return LLMResponse(
            content=content,
            model=result.get("model", "ai_stack"),
            provider="ai_stack",
            processing_time=elapsed,
            request_id=request.request_id,
            metadata=result.get("metadata", {}),
        )

    async def test_environment(self) -> EnvironmentTestResult:
        """Test AI Stack VM connectivity."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()

        try:
            client = await self._ensure_client()
            health = await client.health_check()
            elapsed = time.time() - start

            status = health.get("status", "unknown")
            healthy = status == "healthy"

            diagnostics.append(
                DiagnosticMessage(
                    level=(DiagnosticLevel.INFO if healthy else DiagnosticLevel.ERROR),
                    message=f"AI Stack status: {status}",
                    details=health.get("ai_stack_response"),
                )
            )

            if healthy:
                agents = await client.list_available_agents()
                agent_list = agents.get("agents", [])
                diagnostics.append(
                    DiagnosticMessage(
                        level=DiagnosticLevel.INFO,
                        message=f"Available agents: {len(agent_list)}",
                    )
                )

        except Exception as e:
            elapsed = time.time() - start
            healthy = False
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message=f"Connection failed: {e}",
                )
            )

        return EnvironmentTestResult(
            healthy=healthy,
            adapter_type="ai_stack",
            diagnostics=diagnostics,
            models_available=["ai_stack_chat"],
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """AI Stack exposes agent types rather than models."""
        try:
            client = await self._ensure_client()
            agents = await client.list_available_agents()
            return agents.get("agents", ["ai_stack_chat"])
        except Exception:
            return ["ai_stack_chat"]

    async def cleanup(self) -> None:
        """Close AI Stack client connection."""
        if self._client:
            from services.ai_stack_client import close_ai_stack_client

            await close_ai_stack_client()
            self._client = None


__all__ = ["AIStackAdapter"]
