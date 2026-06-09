# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Experiment Tracker — structured logging for performance experiments.

Inspired by flash-moe's 58-experiment results.tsv pattern.
Stores experiments in Redis for cross-session persistence.

Usage:
    tracker = ExperimentTracker()
    await tracker.log(
        name="FMA dequant kernel",
        hypothesis="Rearranging math enables GPU FMA units",
        area="inference",
        measurement={"tok_per_sec_before": 3.90, "tok_per_sec_after": 4.36},
        result="kept",
        rationale="12% throughput improvement",
    )
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

REDIS_KEY = "autobot:experiments"


@dataclass
class ExperimentRecord:
    """A single performance experiment record."""

    experiment_id: str
    name: str
    hypothesis: str
    area: str
    measurement: Dict[str, Any]
    result: str  # kept, discarded, inconclusive
    rationale: str
    timestamp: float = field(default_factory=time.time)
    related_issue: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for Redis storage."""
        return asdict(self)


class ExperimentTracker:
    """Track performance experiments in Redis."""

    async def log(
        self,
        name: str,
        hypothesis: str,
        area: str,
        measurement: Dict[str, Any],
        result: str,
        rationale: str,
        related_issue: str | None = None,
    ) -> ExperimentRecord:
        """Log a new experiment."""
        record = ExperimentRecord(
            experiment_id=f"exp-{uuid.uuid4().hex[:8]}",
            name=name,
            hypothesis=hypothesis,
            area=area,
            measurement=measurement,
            result=result,
            rationale=rationale,
            related_issue=related_issue,
        )
        redis_client = await get_async_redis_client(database="analytics")
        if redis_client:
            await redis_client.rpush(REDIS_KEY, json.dumps(record.to_dict()))
            await redis_client.ltrim(REDIS_KEY, -10000, -1)  # Cap at 10k (#2031)
        logger.info("Experiment logged: %s -> %s", name, result)
        return record

    async def list_experiments(self, area: str | None = None) -> List[Dict[str, Any]]:
        """List all experiments, optionally filtered by area."""
        redis_client = await get_async_redis_client(database="analytics")
        if not redis_client:
            return []
        raw = await redis_client.lrange(REDIS_KEY, 0, -1)
        records = [json.loads(r) for r in raw]
        if area:
            records = [r for r in records if r.get("area") == area]
        return records
