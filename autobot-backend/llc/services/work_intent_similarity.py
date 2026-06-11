# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Work-intent cosine-similarity helper (GH#9532).

Compares a free-text ``work_intent`` against a work-item title using the
project's existing embedding infrastructure (``services.npu_client``).

The check is strictly non-blocking and advisory:
- score >= 0.7   → no action
- 0.5 <= score < 0.7 → INFO log (low alignment)
- score < 0.5    → WARNING log (very low alignment)
- embedding unavailable / error → DEBUG log, return None silently

No exception propagates out of ``check_similarity``; callers must never
fail a checkout because of this module.
"""

import logging
import math
from typing import List, Optional

logger = logging.getLogger(__name__)

_WARN_THRESHOLD = 0.7
_ALERT_THRESHOLD = 0.5


def _cosine(a: List[float], b: List[float]) -> float:
    """Return cosine similarity in [-1, 1] for two equal-length float lists.

    Returns 0.0 when either vector has zero norm.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed(text: str) -> Optional[List[float]]:
    """Return a unit-normalised embedding vector, or None on any failure."""
    try:
        from services.npu_client import generate_embedding_with_fallback

        raw = await generate_embedding_with_fallback(text)
        if raw is None:
            return None
        norm = math.sqrt(sum(x * x for x in raw))
        return [x / norm for x in raw] if norm > 0 else list(raw)
    except Exception as exc:
        logger.debug("work_intent_similarity: embedding failed (non-critical): %s", exc)
        return None


async def check_similarity(
    work_intent: str,
    item_title: str,
    work_item_id: str,
) -> Optional[float]:
    """Compute cosine similarity between *work_intent* and *item_title*.

    Logs warnings when similarity is below threshold.  Never raises.
    Returns the similarity score (float) or None when embeddings are
    unavailable.
    """
    try:
        intent_vec, title_vec = await _embed(work_intent), await _embed(item_title)
        if intent_vec is None or title_vec is None:
            logger.debug(
                "work_intent_similarity: skipping similarity for work_item=%s — embedding unavailable",
                work_item_id,
            )
            return None

        score = _cosine(intent_vec, title_vec)

        if score < _ALERT_THRESHOLD:
            logger.warning(
                "work_intent_similarity: very low alignment for work_item=%s "
                "(score=%.3f<%.1f); intent=%r title=%r",
                work_item_id,
                score,
                _ALERT_THRESHOLD,
                work_intent,
                item_title,
            )
        elif score < _WARN_THRESHOLD:
            logger.info(
                "work_intent_similarity: low alignment for work_item=%s "
                "(score=%.3f<%.1f); intent=%r title=%r",
                work_item_id,
                score,
                _WARN_THRESHOLD,
                work_intent,
                item_title,
            )

        return score
    except Exception as exc:
        logger.debug("work_intent_similarity: unexpected error (non-critical): %s", exc)
        return None
