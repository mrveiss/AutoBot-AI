# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM client the planner module talks through (#21023, part of #20846).

``planner.LLMPlannerModule`` duck-types ``llm.generate(prompt=, temperature=)``. This adapter is that
object: it sends the planning prompt to the model the turn already selected, through the provider
registry -- the route ``llm_failover`` uses -- so planning needs no second model, endpoint or credential.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import CategoryDefaults
from llm_shared import get_provider_registry
from llm_shared.models import LLMRequest
from llm_shared.types import LLMType, ProviderType

logger = get_logger(__name__)


class PlannerLLMClient:
    """``generate(prompt, temperature)`` over the turn's selected model."""

    def __init__(self, model_name: str, session_id: str):
        self.model_name = model_name
        self.session_id = session_id

    async def generate(self, prompt: str, temperature: float) -> str:
        """Return the model's text; raise on an error response so the planner falls back visibly."""
        request = LLMRequest(
            messages=[{"role": CategoryDefaults.ROLE_USER, "content": prompt}],
            llm_type=LLMType.CHAT,
            provider=ProviderType.OLLAMA,
            model_name=self.model_name,
            temperature=temperature,
            metadata={"conversation_id": self.session_id, "purpose": "chat_planner"},
        )
        registry = get_provider_registry()
        provider = await registry.get_provider_for_request(provider_name=request.provider.value, request=request)
        if provider is None:
            raise RuntimeError("no provider available for planning")
        response = await provider.chat_completion(request)
        if response.error or not response.content:
            raise RuntimeError(f"planner model returned no plan: {response.error or 'empty'}")
        return response.content
