# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Real grounding:stats counters for GET /api/kb-stats (#14981).

GroundedAgent adds one increment set per grounded response and one per resolved
conflict; the endpoint in api/knowledge_grounding.py derives its ratios from
these counters at read time. Recording is best-effort: a failed write logs a
warning and never fails the response or resolution the caller is waiting on.
"""

from typing import Any, Dict, List

from autobot_shared.env_utils import blank_to_none
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.ttl_constants import TTL_30_DAYS
from services.grounded_agent_models import VerifiedClaim
from services.knowledge_grounding_models import VerificationMethod

logger = get_logger(__name__)

_GROUNDING_STATS_KEY = "grounding:stats"


def _resolve_grounding_stats_ttl() -> int:
    """Return TTL seconds for the grounding:stats Redis hash."""
    raw = blank_to_none(config.misc.grounding_stats_ttl)
    if raw is None:
        return TTL_30_DAYS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_GROUNDING_STATS_TTL=%r is not an integer; falling back to %ds (30d)",
            raw,
            TTL_30_DAYS,
        )
        return TTL_30_DAYS
    if value <= 0:
        logger.warning(
            "AUTOBOT_GROUNDING_STATS_TTL=%d must be positive; falling back to %ds (30d)",
            value,
            TTL_30_DAYS,
        )
        return TTL_30_DAYS
    return value


_GROUNDING_STATS_TTL = _resolve_grounding_stats_ttl()

# The only two VerificationMethod members anything produces today (see the
# VerificationMethod docstring in services/knowledge_grounding_models.py).
# EXTERNAL_RESEARCH and CAUSAL_INFERENCE are reserved for tiers that don't
# exist yet -- they get no counter until something writes to it.
_PRODUCED_VERIFICATION_METHODS = (VerificationMethod.KB_LOOKUP.value, VerificationMethod.CLAIM_VERIFIER_RAG.value)


def _method_counts(verified_claims: List[VerifiedClaim]) -> Dict[str, int]:
    """Verified-claim counts per produced method; a method nobody used is absent."""
    counts: Dict[str, int] = {}
    for verified in verified_claims:
        if verified.verification_method in _PRODUCED_VERIFICATION_METHODS:
            counts[verified.verification_method] = counts.get(verified.verification_method, 0) + 1
    return counts


async def record_grounding_stats(
    redis_client: Any,
    claims_extracted: int,
    verified_claims: List[VerifiedClaim],
    conflicts_created: int,
    overall_confidence: float,
) -> None:
    """Add one grounded response to the counters GET /kb-stats reads.

    A None client (Redis disabled, or its circuit breaker open) records nothing.
    """
    if redis_client is None:
        return
    method_counts = _method_counts(verified_claims)
    try:
        async with redis_client.pipeline() as pipe:
            await pipe.hincrby(_GROUNDING_STATS_KEY, "total_responses_grounded", 1)
            await pipe.hincrby(_GROUNDING_STATS_KEY, "total_claims_extracted", claims_extracted)
            await pipe.hincrby(_GROUNDING_STATS_KEY, "claims_verified_count", len(verified_claims))
            await pipe.hincrbyfloat(_GROUNDING_STATS_KEY, "confidence_sum", overall_confidence)
            await pipe.hincrby(_GROUNDING_STATS_KEY, "conflicts_created", conflicts_created)
            for method in _PRODUCED_VERIFICATION_METHODS:
                count = method_counts.get(method, 0)
                if count:
                    await pipe.hincrby(_GROUNDING_STATS_KEY, f"claim_source_{method}", count)
            await pipe.expire(_GROUNDING_STATS_KEY, _GROUNDING_STATS_TTL)
            await pipe.execute()
    except Exception as exc:
        logger.warning("Failed to record grounding stats: %s", exc)


async def record_conflict_resolved(redis_client: Any, conflict_id: str) -> None:
    """Count one resolved conflict; the resolution itself is already persisted."""
    try:
        await redis_client.hincrby(_GROUNDING_STATS_KEY, "conflicts_resolved", 1)
        await redis_client.expire(_GROUNDING_STATS_KEY, _GROUNDING_STATS_TTL)
    except Exception as exc:
        logger.warning("Failed to record conflicts_resolved for %s: %s", conflict_id, exc)
