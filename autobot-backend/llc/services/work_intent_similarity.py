# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Work-intent cosine-similarity helper (GH#9532).

Compares a free-text ``work_intent`` against a work-item title using the
project's existing embedding infrastructure (``services.npu_client``).

The check is strictly non-blocking and advisory:
- score >= 0.7   → no action
- 0.5 <= score < 0.7 → WARNING log (low alignment)
- score < 0.5    → WARNING log (very low alignment)
- embedding unavailable / error → DEBUG log, return None silently

No exception propagates out of ``check_similarity``; callers must never
fail a checkout because of this module.
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_WARN_THRESHOLD = 0.7
_ALERT_THRESHOLD = 0.5


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Return cosine similarity in [-1, 1] for two 1-D float32 arrays."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def _embed(text: str) -> Optional[np.ndarray]:
    """Return a unit-normalised embedding vector, or None on any failure."""
    try:
        from services.npu_client import generate_embedding_with_fallback

        raw = await generate_embedding_with_fallback(text)
        if raw is None:
            return None
        vec = np.asarray(raw, dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec
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
