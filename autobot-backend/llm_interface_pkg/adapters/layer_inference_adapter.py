# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Layer Inference Adapter - Wraps LayerInferenceEngine for the adapter registry.

Issue #3104: Registers the layer-by-layer inference engine as a selectable
LLM provider so it can be accessed via the unified adapter API.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = logging.getLogger(__name__)


class LayerInferenceAdapter(AdapterBase):
    """Adapter that wraps LayerInferenceEngine for the registry (#3104)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("layer_inference", config)
        self._engine = None

    def _get_engine(self):
        """Lazy-init the engine on first use."""
        if self._engine is not None:
            return self._engine
        try:
            from ..optimization.layer_inference import (
                LayerInferenceConfig,
                LayerInferenceEngine,
            )

            model_name = self.config.settings.get(
                "model_name",
                os.environ.get("LAYER_INFERENCE_MODEL", ""),
            )
            if not model_name:
                return None
            engine_config = LayerInferenceConfig(model_name=model_name)
            self._engine = LayerInferenceEngine(engine_config)
            return self._engine
        except ImportError:
            logger.debug("Layer inference dependencies not available")
            return None

    async def execute(
        self,
        request: LLMRequest,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a generation request via LayerInferenceEngine."""
        engine = self._get_engine()
        if engine is None:
            return LLMResponse(
                content="Layer inference engine not available",
                model="layer_inference",
                provider="layer_inference",
                tokens_used=0,
                latency_ms=0,
                error="Engine not initialized — set LAYER_INFERENCE_MODEL",
            )

        prompt = ""
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt += f"{role}: {content}\n"

        start = time.monotonic()
        max_tokens = request.max_tokens or 256
        result = engine.generate(prompt, max_new_tokens=max_tokens)
        latency = (time.monotonic() - start) * 1000

        return LLMResponse(
            content=result,
            model=self.config.settings.get("model_name", "layer_inference"),
            provider="layer_inference",
            tokens_used=max_tokens,
            latency_ms=latency,
        )

    async def test_environment(self) -> EnvironmentTestResult:
        """Test if layer inference is available."""
        messages: List[DiagnosticMessage] = []
        try:
            from ..optimization.layer_inference import LayerInferenceEngine  # noqa: F401

            messages.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.OK,
                    message="LayerInferenceEngine importable",
                )
            )
            engine = self._get_engine()
            if engine is None:
                messages.append(
                    DiagnosticMessage(
                        level=DiagnosticLevel.WARNING,
                        message="No model configured — set LAYER_INFERENCE_MODEL",
                    )
                )
                return EnvironmentTestResult(available=False, diagnostics=messages)
            return EnvironmentTestResult(available=True, diagnostics=messages)
        except ImportError as exc:
            messages.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message=f"Import failed: {exc}",
                )
            )
            return EnvironmentTestResult(available=False, diagnostics=messages)

    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models for layer inference."""
        engine = self._get_engine()
        if engine is None:
            return []
        model_name = self.config.settings.get("model_name", "layer_inference")
        return [{"id": model_name, "name": model_name, "provider": "layer_inference"}]
