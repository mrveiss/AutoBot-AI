# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Completed-analysis checkpoints for the pattern-analysis task (GH#8439, #12384, #20513)."""

import hashlib
import json

_PATTERN_CHECKPOINT_PREFIX = "pattern_complete_checkpoint:"
_CHECKPOINT_TTL = 3600  # 1 h — recent-enough to resume from


def path_checkpoint_key(path: str, source_id: str | None = None, options: str = "") -> str:
    """Issue #12384: fold source_id into the checkpoint key. Without this, two
    different sources resolving to the same scan path (e.g. both default to
    AutoBot's own PATH.PROJECT_ROOT) would return each other's cached
    analysis result -- bypassing the ChromaDB source_id tag entirely on a
    checkpoint-hit retry. *options* folds in the detection settings, so a scan with a
    detector disabled never receives a report built with it enabled (#20513).
    """
    tag = source_id or "default"
    return f"{_PATTERN_CHECKPOINT_PREFIX}{hashlib.sha256(f'{tag}:{path}:{options}'.encode()).hexdigest()[:16]}"


def checkpoint_options(request) -> str:
    """The detection settings that change what a report contains."""
    return json.dumps(
        [
            request.enable_clone_detection,
            request.enable_anti_pattern_detection,
            request.enable_regex_detection,
            request.enable_complexity_analysis,
            request.similarity_threshold,
        ]
    )


async def load_path_checkpoint(path: str, source_id: str | None = None, options: str = "") -> dict | None:
    """Return a previously-saved completed analysis result for *path*/*source_id*, or None (GH#8439)."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return None
        raw = await redis.get(path_checkpoint_key(path, source_id, options))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def save_path_checkpoint(path: str, result: dict, source_id: str | None = None, options: str = "") -> None:
    """Persist *result* as the checkpoint for *path*/*source_id* (GH#8439)."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.set(
                path_checkpoint_key(path, source_id, options), json.dumps(result, default=str), ex=_CHECKPOINT_TTL
            )
    except Exception:
        pass
