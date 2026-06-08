# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLMObserver Protocol — pluggable observability hook for LLM inference (GH#6593).

Register implementations via ``llm_shared.observability.register()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from llm_shared.models import LLMRequest, LLMResponse


class LLMObserver(Protocol):
    """Observer interface for LLM inference events."""

    async def on_request(self, request: "LLMRequest", metadata: dict) -> None: ...

    async def on_response(self, response: "LLMResponse", latency_ms: float, cost: float) -> None: ...

    async def on_error(self, exc: Exception, request: "LLMRequest") -> None: ...
