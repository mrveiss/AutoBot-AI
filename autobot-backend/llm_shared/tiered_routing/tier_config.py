# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tier Configuration - Configuration dataclasses for tiered model routing.

Issue #748: Tiered Model Distribution Implementation.
"""

from dataclasses import dataclass, field
from typing import Dict

from autobot_shared.ssot_config import CLASSIFICATION_MODEL, DEFAULT_LLM_MODEL, TRIVIAL_MODEL
from config.registry import ConfigRegistry


@dataclass
class TierModels:
    """Model definitions for each tier.

    trivial: Lightweight model for simple queries with no tool injection,
    RAG, or memory. Optimized for speed and cost (GH#9050).

    ssm: SSM/linear-attention model (e.g. mamba, rwkv) preferred for
    decode-bound workloads with high expected_output_tokens.  Empty string
    means no SSM model is registered; the router falls back to the
    transformer (complex) tier in that case.
    """

    trivial: str = TRIVIAL_MODEL  # GH#9050: llama3.2:1b for lightweight inference
    simple: str = CLASSIFICATION_MODEL
    complex: str = DEFAULT_LLM_MODEL
    long_context: str = DEFAULT_LLM_MODEL
    # SSM/linear-attention tier: leave empty if no non-transformer model is
    # available.  ComplexityRouter checks this before routing decode-heavy
    # requests here (GH#7353).
    ssm: str = ""


@dataclass
class TierLogging:
    """Logging configuration for tiered routing."""

    log_scores: bool = True
    log_routing_decisions: bool = True


@dataclass
class TierConfig:
    """
    Configuration for tiered model routing.

    Issue #748: Loads from SSOT config with sensible defaults.

    Attributes:
        enabled: Whether tiered routing is active
        trivial_threshold: Score below this uses trivial tier (GH#9050, 0-10 scale)
        complexity_threshold: Score below this uses simple tier (0-10 scale)
        long_context_threshold: Input-token count above which long_context tier is used
        ssm_output_token_threshold: expected_output_tokens value at or above which
            decode-heavy requests are steered toward the SSM/linear-attention tier
            (GH#7353).  Defaults to 2000.
        models: Model names for each tier (trivial, simple, complex, long_context, ssm)
        fallback_to_complex: If simple tier fails, try complex tier
        logging: Logging settings
    """

    enabled: bool = True
    trivial_threshold: float = 1.0  # GH#9050: lightweight mode for scores < 1.0
    complexity_threshold: float = 3.0
    long_context_threshold: int = 16000
    # Output-token threshold above which a decode-heavy request is steered
    # toward the SSM/linear-attention tier (GH#7353).  SSM models scale
    # linearly with sequence length during decode, unlike transformers which
    # are O(n²) in KV-cache memory.  Requests with expected_output_tokens ≥
    # this value are routed to models.ssm when one is registered, otherwise
    # they fall through to the transformer (complex) tier.
    ssm_output_token_threshold: int = 2000
    models: TierModels = field(default_factory=TierModels)
    fallback_to_complex: bool = True
    logging: TierLogging = field(default_factory=TierLogging)

    @classmethod
    def from_config(cls) -> "TierConfig":
        """
        Load configuration from SSOT ConfigRegistry.

        Returns:
            TierConfig instance with values from config or defaults
        """
        tier_config = ConfigRegistry.get("llm.tiered_routing", {})

        if not tier_config:
            return cls()

        models_config = tier_config.get("models", {})
        logging_config = tier_config.get("logging", {})

        return cls(
            enabled=tier_config.get("enabled", True),
            trivial_threshold=float(tier_config.get("trivial_threshold", 1.0)),
            complexity_threshold=float(tier_config.get("complexity_threshold", 3.0)),
            long_context_threshold=int(tier_config.get("long_context_threshold", 16000)),
            ssm_output_token_threshold=int(tier_config.get("ssm_output_token_threshold", 2000)),
            models=TierModels(
                trivial=models_config.get("trivial", TRIVIAL_MODEL),
                simple=models_config.get("simple", CLASSIFICATION_MODEL),
                complex=models_config.get("complex", DEFAULT_LLM_MODEL),
                long_context=models_config.get("long_context", DEFAULT_LLM_MODEL),
                ssm=models_config.get("ssm", ""),
            ),
            fallback_to_complex=tier_config.get("fallback_to_complex", True),
            logging=TierLogging(
                log_scores=logging_config.get("log_scores", True),
                log_routing_decisions=logging_config.get("log_routing_decisions", True),
            ),
        )


@dataclass
class ComplexityResult:
    """
    Result of complexity scoring.

    Attributes:
        score: Normalized complexity score (0-10)
        factors: Individual factor scores for debugging
        tier: Selected tier ("trivial", "simple", "complex", "long_context", or "ssm")
        reasoning: Human-readable explanation of the score
        input_tokens: Estimated input token count (used for long_context routing)
    """

    score: float
    factors: Dict[str, float]
    tier: str
    reasoning: str
    input_tokens: int = 0

    @property
    def is_trivial(self) -> bool:
        """Check if this result indicates trivial tier (GH#9050)."""
        return self.tier == "trivial"

    @property
    def is_simple(self) -> bool:
        """Check if this result indicates simple tier."""
        return self.tier == "simple"

    @property
    def is_complex(self) -> bool:
        """Check if this result indicates complex tier."""
        return self.tier == "complex"

    @property
    def is_long_context(self) -> bool:
        """Check if this result indicates long_context tier."""
        return self.tier == "long_context"

    @property
    def is_ssm(self) -> bool:
        """Check if this result indicates SSM/linear-attention tier (GH#7353)."""
        return self.tier == "ssm"


@dataclass
class TierMetrics:
    """
    Metrics for tiered routing monitoring.

    Issue #748: Track routing decisions for optimization.
    """

    trivial_tier_requests: int = 0
    simple_tier_requests: int = 0
    complex_tier_requests: int = 0
    long_context_tier_requests: int = 0
    ssm_tier_requests: int = 0
    total_requests: int = 0
    avg_trivial_score: float = 0.0
    avg_simple_score: float = 0.0
    avg_complex_score: float = 0.0
    fallback_count: int = 0
    score_sum_trivial: float = 0.0
    score_sum_simple: float = 0.0
    score_sum_complex: float = 0.0

    def record(self, result: ComplexityResult) -> None:
        """Record a routing decision."""
        self.total_requests += 1

        if result.is_trivial:
            self.trivial_tier_requests += 1
            self.score_sum_trivial += result.score
            if self.trivial_tier_requests > 0:
                self.avg_trivial_score = self.score_sum_trivial / self.trivial_tier_requests
        elif result.is_simple:
            self.simple_tier_requests += 1
            self.score_sum_simple += result.score
            if self.simple_tier_requests > 0:
                self.avg_simple_score = self.score_sum_simple / self.simple_tier_requests
        elif result.is_long_context:
            self.long_context_tier_requests += 1
        elif result.is_ssm:
            self.ssm_tier_requests += 1
        else:
            self.complex_tier_requests += 1
            self.score_sum_complex += result.score
            if self.complex_tier_requests > 0:
                self.avg_complex_score = self.score_sum_complex / self.complex_tier_requests

    def record_fallback(self) -> None:
        """Record a fallback from simple to complex tier."""
        self.fallback_count += 1

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary for reporting."""
        return {
            "trivial_tier_requests": self.trivial_tier_requests,
            "simple_tier_requests": self.simple_tier_requests,
            "complex_tier_requests": self.complex_tier_requests,
            "long_context_tier_requests": self.long_context_tier_requests,
            "ssm_tier_requests": self.ssm_tier_requests,
            "total_requests": self.total_requests,
            "avg_trivial_score": round(self.avg_trivial_score, 2),
            "avg_simple_score": round(self.avg_simple_score, 2),
            "avg_complex_score": round(self.avg_complex_score, 2),
            "fallback_count": self.fallback_count,
            "trivial_tier_percentage": (
                round(self.trivial_tier_requests / self.total_requests * 100, 1) if self.total_requests > 0 else 0.0
            ),
            "simple_tier_percentage": (
                round(self.simple_tier_requests / self.total_requests * 100, 1) if self.total_requests > 0 else 0.0
            ),
        }


__all__ = [
    "TierConfig",
    "TierModels",
    "TierLogging",
    "ComplexityResult",
    "TierMetrics",
]
