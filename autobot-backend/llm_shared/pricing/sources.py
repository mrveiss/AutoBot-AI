# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Abstract pricing source interface and data model (GH#6480).

Adding a new provider:
1. Create a subclass of PricingSource in a new `<provider>_source.py` file.
2. Implement `async def fetch(self) -> dict[str, ModelPricing]`.
3. Register the instance in `services/pricing_refresh.py:PRICING_SOURCES`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ModelPricing:
    """Pricing for a single model, all values in USD per 1 million tokens."""

    provider: str
    model_id: str
    input_per_1m: float
    output_per_1m: float
    cache_read_per_1m: float = 0.0
    cache_write_per_1m: float = 0.0
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "input_per_1m": self.input_per_1m,
            "output_per_1m": self.output_per_1m,
            "cache_read_per_1m": self.cache_read_per_1m,
            "cache_write_per_1m": self.cache_write_per_1m,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelPricing":
        updated_at = None
        if data.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(data["updated_at"])
            except ValueError:
                pass
        return cls(
            provider=data["provider"],
            model_id=data["model_id"],
            input_per_1m=float(data["input_per_1m"]),
            output_per_1m=float(data["output_per_1m"]),
            cache_read_per_1m=float(data.get("cache_read_per_1m", 0.0)),
            cache_write_per_1m=float(data.get("cache_write_per_1m", 0.0)),
            updated_at=updated_at,
        )

    def as_legacy_dict(self) -> dict[str, float]:
        """Return the format used by MODEL_PRICING_PER_1M_TOKENS."""
        return {"input": self.input_per_1m, "output": self.output_per_1m}


class PricingSource(ABC):
    """Abstract base for provider pricing fetchers."""

    provider: str

    @abstractmethod
    async def fetch(self) -> dict[str, ModelPricing]:
        """Fetch current pricing for all known models.

        Returns a mapping of model_id → ModelPricing. Never raises; return
        an empty dict on failure and log the error in the implementation.
        """

    def _now(self) -> datetime:
        return datetime.now(tz=timezone.utc)
