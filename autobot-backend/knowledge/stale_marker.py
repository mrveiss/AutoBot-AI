# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stale marker a man-page fact carries when the self-model says its command is gone from its host (#22299).

The marker lives in the fact's own metadata, so search results show it with no extra lookup, and
``demote_stale`` ranks a marked fact below an unmarked one. A marked fact is never deleted (#17038).
"""

from __future__ import annotations

from typing import Any, Dict

#: Metadata field: the self-model status (``absent`` or ``stale``) of the fact's command on its host; "" when current.
STALE_FIELD = "self_model_stale"

#: Score multiplier for a marked fact, so a current page for the same command outranks it.
STALE_SCORE_FACTOR = 0.5


def demote_stale(score: float, result: Dict[str, Any]) -> float:
    """*score*, scaled down when the search *result*'s fact carries the stale marker."""
    metadata = result.get("metadata") or {}
    return score * STALE_SCORE_FACTOR if metadata.get(STALE_FIELD) else score
