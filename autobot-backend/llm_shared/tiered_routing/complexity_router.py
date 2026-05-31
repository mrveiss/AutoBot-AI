# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ComplexityRouter — routes by task-complexity score (original TieredModelRouter logic).

Issue #6595: Extracted from tier_router.py so it can be one pluggable strategy
alongside CostRouter and LatencyRouter.  tier_router.py retains backward-compat
aliases pointing here.
"""

from typing import Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config

from ..models import LLMRequest, LLMResponse
from ..optimization.model_inspector import inspect_model
from .complexity_scorer import TaskComplexityScorer
from .tier_config import ComplexityResult, TierConfig, TierMetrics

logger = get_logger(__name__)


class ComplexityRouter:
    """Routes requests to model tiers based on complexity score (0-10 scale)."""

    def __init__(
        self,
        config: TierConfig | None = None,
        scorer: TaskComplexityScorer | None = None,
    ) -> None:
        self.config = config or TierConfig.from_config()
        self.scorer = scorer or TaskComplexityScorer(self.config)
        self._metrics = TierMetrics()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def route(
        self,
        messages: List[Dict],
        requested_model: str | None = None,
        expected_output_tokens: int | None = None,
    ) -> Tuple[str, ComplexityResult]:
        if not self.config.enabled:
            return self.config.models.complex, ComplexityResult(
                score=0.0,
                factors={},
                tier="complex",
                reasoning="Tiered routing disabled",
            )

        result = self.scorer.score(messages)

        # SSM/linear-attention tier: decode-bound workloads with high
        # expected_output_tokens scale better on SSM models (O(1) per decode
        # step vs O(n) KV-cache growth for transformers).  Check this before
        # long_context so a decode-heavy request isn't mis-routed to the
        # long_context transformer tier (GH#7353).
        if (
            expected_output_tokens is not None
            and expected_output_tokens >= self.config.ssm_output_token_threshold
            and self.config.models.ssm
        ):
            result = ComplexityResult(
                score=result.score,
                factors=result.factors,
                tier="ssm",
                reasoning=(
                    f"expected_output_tokens ({expected_output_tokens}) >= "
                    f"ssm_output_token_threshold ({self.config.ssm_output_token_threshold})"
                    f" and SSM model is registered"
                ),
                input_tokens=result.input_tokens,
            )
            selected_model = self.config.models.ssm
        # Long-context check takes precedence over complexity score.
        elif result.input_tokens > self.config.long_context_threshold:
            result = ComplexityResult(
                score=result.score,
                factors=result.factors,
                tier="long_context",
                reasoning=(
                    f"Input tokens ({result.input_tokens}) exceed"
                    f" long_context_threshold ({self.config.long_context_threshold})"
                ),
                input_tokens=result.input_tokens,
            )
            selected_model = self.config.models.long_context
        elif result.is_simple:
            selected_model = self.config.models.simple
        else:
            selected_model = self.config.models.complex

        self._metrics.record(result)

        if self.config.logging.log_routing_decisions:
            self._log_decision(requested_model, selected_model, result)

        return selected_model, result

    async def route_with_escalation(
        self,
        request: LLMRequest,
    ) -> Optional[LLMResponse]:
        """Attempt Claude escalation when complexity_score >= threshold (#8171).

        Returns an LLMResponse if Claude was used, or None if the request
        should fall through to the local provider.  Claude errors are caught
        and logged so the caller can always fall back safely.

        Args:
            request: The incoming LLM request.

        Returns:
            LLMResponse from Claude on success, None otherwise.
        """
        if not ssot_config.llm.claude_escalation_enabled:
            return None

        result = self.scorer.score(request.messages)
        if result.score < ssot_config.llm.claude_escalation_threshold:
            return None

        logger.info(
            "ComplexityRouter: escalating to Claude (score=%.1f >= threshold=%.1f)",
            result.score,
            ssot_config.llm.claude_escalation_threshold,
        )

        try:
            # Enable prompt caching when a system message is present.
            escalation_request = LLMRequest(
                messages=request.messages,
                llm_type=request.llm_type,
                provider=request.provider,
                model_name=request.model_name,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                frequency_penalty=request.frequency_penalty,
                presence_penalty=request.presence_penalty,
                stop=request.stop,
                stream=request.stream,
                structured_output=request.structured_output,
                timeout=request.timeout,
                retry_count=request.retry_count,
                fallback_enabled=False,
                metadata=dict(request.metadata),
                request_id=request.request_id,
                tools=request.tools,
                tool_choice=request.tool_choice,
            )
            has_system = any(m.get("role") == "system" for m in request.messages)
            if has_system:
                escalation_request.metadata["enable_prompt_cache"] = True

            from ..provider_registry import get_provider_registry

            registry = get_provider_registry()
            claude = await registry.get_provider("anthropic")
            if claude is None:
                logger.warning("ComplexityRouter: Anthropic provider not available; falling through")
                return None
            response = await claude.chat_completion(escalation_request)
            if response.error:
                logger.warning(
                    "ComplexityRouter: Claude escalation returned error=%s; falling through",
                    response.error,
                )
                return None
            return response
        except Exception as exc:
            logger.warning(
                "ComplexityRouter: Claude escalation failed (%s); falling through",
                exc,
            )
            return None

    def _log_decision(
        self,
        requested_model: str | None,
        selected_model: str,
        result: ComplexityResult,
    ) -> None:
        if requested_model and requested_model != selected_model:
            logger.info(
                "ComplexityRouter: %s -> %s (score=%.1f, tier=%s, reason=%s)",
                requested_model,
                selected_model,
                result.score,
                result.tier,
                result.reasoning,
            )
        else:
            logger.debug(
                "ComplexityRouter: selected %s (score=%.1f, tier=%s)",
                selected_model,
                result.score,
                result.tier,
            )

    def record_fallback(self) -> None:
        self._metrics.record_fallback()
        logger.warning("ComplexityRouter fallback triggered: simple -> complex tier")

    def get_metrics(self) -> Dict:
        return self._metrics.to_dict()

    def reset_metrics(self) -> None:
        self._metrics = TierMetrics()

    def get_model_for_tier(self, tier: str) -> str:
        if tier == "simple":
            return self.config.models.simple
        if tier == "complex":
            return self.config.models.complex
        if tier == "long_context":
            return self.config.models.long_context
        if tier == "ssm":
            return self.config.models.ssm
        raise ValueError(f"Unknown tier: {tier}")

    def should_fallback(self, tier: str) -> bool:
        return tier == "simple" and self.config.fallback_to_complex

    def model_fits_in_vram(self, model_name: str, available_vram_gb: float) -> bool:
        info = inspect_model(model_name)
        if info is None:
            return True
        fits = info.estimated_size_gb <= available_vram_gb
        if not fits:
            logger.warning(
                "VRAM check: %s needs ~%.1f GB, %.1f GB available",
                model_name,
                info.estimated_size_gb,
                available_vram_gb,
            )
        return fits


__all__ = ["ComplexityRouter"]
