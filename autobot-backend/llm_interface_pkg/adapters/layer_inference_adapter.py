# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Layer Inference Adapter - Wraps LayerInferenceEngine for the adapter registry.

Issue #3104: Registers the layer-by-layer inference engine as a selectable
LLM provider so it can be accessed via the unified adapter API.
Issue #3140: Updated to use LayerInferencePipeline for end-to-end generation.
"""

import asyncio
import time
from typing import Any, Dict, List

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


class LayerInferenceAdapter(AdapterBase):
    """Adapter that uses LayerInferencePipeline for end-to-end generation (#3140)."""

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__("layer_inference", config)
        self._pipeline = None
        self._prepared = None

    def _get_pipeline(self):
        """Lazy-init the pipeline on first use."""
        if self._pipeline is not None:
            return self._pipeline
        try:
            from ..optimization.pipeline import LayerInferencePipeline, PipelineConfig

            model_name = self.config.settings.get(
                "model_name",
                config.layer_inference_model,
            )
            if not model_name:
                return None
            pipeline_cfg = PipelineConfig(model_name=model_name)
            self._pipeline = LayerInferencePipeline(pipeline_cfg)
            return self._pipeline
        except ImportError:
            logger.debug("Layer inference dependencies not available")
            return None

    def _get_prepared(self):
        """Lazy-init the prepared pipeline components on first use."""
        if self._prepared is not None:
            return self._prepared
        pipeline = self._get_pipeline()
        if pipeline is None:
            return None
        try:
            self._prepared = pipeline.prepare()
        except Exception:
            logger.exception("Pipeline prepare() failed")
            return None
        return self._prepared

    @staticmethod
    def _build_prompt(messages: List[Dict[str, Any]]) -> str:
        """Concatenate chat messages into a single prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append("%s: %s" % (role, content))
        return "\n".join(parts)

    async def execute(
        self,
        request: LLMRequest,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a generation request via the end-to-end LayerInferencePipeline."""
        prepared = self._get_prepared()
        if prepared is None:
            return LLMResponse(
                content="Layer inference engine not available",
                model="layer_inference",
                provider="layer_inference",
                tokens_used=0,
                processing_time=0.0,
                error="Pipeline not initialized — set LAYER_INFERENCE_MODEL",
            )

        prompt = self._build_prompt(request.messages)
        start = time.monotonic()
        max_tokens = request.max_tokens or 256

        try:
            result = await asyncio.to_thread(
                self._pipeline.execute,
                prompt,
                prepared,
                max_new_tokens=max_tokens,
            )
        except Exception:
            logger.exception("LayerInference generation failed")
            return LLMResponse(
                content="",
                model=self.config.settings.get("model_name", "layer_inference"),
                provider="layer_inference",
                tokens_used=0,
                processing_time=time.monotonic() - start,
                error="Generation failed — check logs",
            )

        return LLMResponse(
            content=result,
            model=self.config.settings.get("model_name", "layer_inference"),
            provider="layer_inference",
            tokens_used=len(result.split()) if result else 0,
            processing_time=time.monotonic() - start,
        )

    async def test_environment(self) -> EnvironmentTestResult:
        """Test if layer inference pipeline is available."""
        messages: List[DiagnosticMessage] = []
        try:
            from ..optimization.pipeline import LayerInferencePipeline  # noqa: F401

            messages.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.OK,
                    message="LayerInferencePipeline importable",
                )
            )
            pipeline = self._get_pipeline()
            if pipeline is None:
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
                    message="Import failed: %s" % exc,
                )
            )
            return EnvironmentTestResult(available=False, diagnostics=messages)

    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models for layer inference."""
        pipeline = self._get_pipeline()
        if pipeline is None:
            return []
        model_name = self.config.settings.get("model_name", "layer_inference")
        return [{"id": model_name, "name": model_name, "provider": "layer_inference"}]
