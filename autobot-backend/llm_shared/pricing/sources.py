# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


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


class BaselinePricingSource(PricingSource):
    """Base for providers with no live pricing API — returns a hardcoded baseline.

    Concrete subclasses set two class attributes:
        _PROVIDER: str — provider name (also assigned to `provider`).
        _BASELINE: list of (model_id, input_per_1m, output_per_1m[, cache_read_per_1m])
                   tuples. The optional 4th element defaults to 0.0 when omitted.
    """

    _PROVIDER: str = ""
    _BASELINE: list[tuple] = []

    async def fetch(self) -> dict[str, ModelPricing]:
        now = self._now()
        result: dict[str, ModelPricing] = {}
        for entry in self._BASELINE:
            model_id, inp, out = entry[0], entry[1], entry[2]
            cache_read = entry[3] if len(entry) > 3 else 0.0
            result[model_id] = ModelPricing(
                provider=self._PROVIDER,
                model_id=model_id,
                input_per_1m=inp,
                output_per_1m=out,
                cache_read_per_1m=cache_read,
                updated_at=now,
            )
        logger.debug("%s.fetch returned %d models", type(self).__name__, len(result))
        return result
