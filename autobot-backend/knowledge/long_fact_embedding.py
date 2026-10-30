# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One vector for a fact longer than the embedding model accepts (#20066).

A model rejects input past its context (`nomic-embed-text`: 2048 tokens), so such a fact never got a
vector and was retried on every pass. Its windows are embedded separately and averaged, which keeps one
vector per fact id and lets the whole text count, where cutting it would make its tail unsearchable.
The collection uses cosine distance, so the average is scaled back to unit length.
"""

from __future__ import annotations

import math
from typing import Any, Awaitable, Callable, Dict, List

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Characters per window. Dense text can run near 2 characters a token, so this stays under 2048 tokens.
WINDOW_CHARS = env_int_clamped("AUTOBOT_KB_EMBED_WINDOW_CHARS", 4000, 200, 100000)
#: Windows embedded for one fact; past this only the leading ones count, and the log says so.
MAX_WINDOWS = env_int_clamped("AUTOBOT_KB_EMBED_MAX_WINDOWS", 32, 1, 1000)


def _weighted_unit_mean(vectors: List[List[float]], weights: List[int]) -> List[float]:
    """Weighted by window length, so a short last window does not count like a full one."""
    total = sum(weights)
    mean = [sum(v * w for v, w in zip(column, weights)) / total for column in zip(*vectors)]
    norm = math.sqrt(sum(value * value for value in mean))
    return [value / norm for value in mean] if norm else mean


def _windows(text: str) -> List[str]:
    return [text[start : start + WINDOW_CHARS] for start in range(0, len(text), WINDOW_CHARS)]


def window_metadata(text: str) -> Dict[str, int]:
    """What marks a vector as an average, so a later re-embed or a changed window size can find it."""
    if len(text) <= WINDOW_CHARS:
        return {}
    return {"embedding_window_chars": WINDOW_CHARS, "embedding_windows": min(len(_windows(text)), MAX_WINDOWS)}


async def embed_in_windows(embed: Callable[..., Awaitable[List[float]]], text: str, **kwargs: Any) -> List[float]:
    """*embed*'s result for *text*, averaged over windows when it is too long; empty if any window failed."""
    if len(text) <= WINDOW_CHARS:
        return await embed(text, **kwargs)
    windows = _windows(text)
    if len(windows) > MAX_WINDOWS:
        logger.warning("Long fact: embedding %d of %d windows; the rest is not searchable", MAX_WINDOWS, len(windows))
    vectors = []
    for window in windows[:MAX_WINDOWS]:
        vector = await embed(window, **kwargs)
        if not vector:
            return []  # the caller records a retriable failure, as for any failed embedding
        vectors.append(vector)
    return _weighted_unit_mean(vectors, [len(window) for window in windows[:MAX_WINDOWS]])
