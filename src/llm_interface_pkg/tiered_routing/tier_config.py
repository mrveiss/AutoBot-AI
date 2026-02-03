# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tier Configuration - Configuration dataclasses for tiered model routing.

Issue #748: Tiered Model Distribution Implementation.
"""

from dataclasses import dataclass, field
from typing import Dict

from src.config.registry import ConfigRegistry


@dataclass
class TierModels:
    """Model definitions for each tier."""

    simple: str = "gemma2:2b"
    complex: str = "mistral:7b-instruct"


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
        complexity_threshold: Score below this uses simple tier (0-10 scale)
        models: Model names for each tier
        fallback_to_complex: If simple tier fails, try complex tier
        logging: Logging settings
    """

    enabled: bool = True
    complexity_threshold: float = 3.0
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
            complexity_threshold=float(tier_config.get("complexity_threshold", 3.0)),
            models=TierModels(
                simple=models_config.get("simple", "gemma2:2b"),
                complex=models_config.get("complex", "mistral:7b-instruct"),
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
        tier: Selected tier ("simple" or "complex")
        reasoning: Human-readable explanation of the score
    """

    score: float
    factors: Dict[str, float]
    tier: str
    reasoning: str

    @property
    def is_simple(self) -> bool:
        """Check if this result indicates simple tier."""
        return self.tier == "simple"

    @property
    def is_complex(self) -> bool:
        """Check if this result indicates complex tier."""
        return self.tier == "complex"


@dataclass
class TierMetrics:
    """
    Metrics for tiered routing monitoring.

    Issue #748: Track routing decisions for optimization.
    """

    simple_tier_requests: int = 0
    complex_tier_requests: int = 0
    total_requests: int = 0
    avg_simple_score: float = 0.0
    avg_complex_score: float = 0.0
    fallback_count: int = 0
    score_sum_simple: float = 0.0
    score_sum_complex: float = 0.0

    def record(self, result: ComplexityResult) -> None:
        """Record a routing decision."""
        self.total_requests += 1

        if result.is_simple:
            self.simple_tier_requests += 1
            self.score_sum_simple += result.score
            if self.simple_tier_requests > 0:
                self.avg_simple_score = (
                    self.score_sum_simple / self.simple_tier_requests
                )
        else:
            self.complex_tier_requests += 1
            self.score_sum_complex += result.score
            if self.complex_tier_requests > 0:
                self.avg_complex_score = (
                    self.score_sum_complex / self.complex_tier_requests
                )

    def record_fallback(self) -> None:
        """Record a fallback from simple to complex tier."""
        self.fallback_count += 1

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary for reporting."""
        return {
            "simple_tier_requests": self.simple_tier_requests,
            "complex_tier_requests": self.complex_tier_requests,
            "total_requests": self.total_requests,
            "avg_simple_score": round(self.avg_simple_score, 2),
            "avg_complex_score": round(self.avg_complex_score, 2),
            "fallback_count": self.fallback_count,
            "simple_tier_percentage": (
                round(self.simple_tier_requests / self.total_requests * 100, 1)
                if self.total_requests > 0
                else 0.0
            ),
        }


__all__ = [
    "TierConfig",
    "TierModels",
    "TierLogging",
    "ComplexityResult",
    "TierMetrics",
]
