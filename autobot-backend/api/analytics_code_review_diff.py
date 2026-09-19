# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The per-file analysis and persistence halves of `analyze_diff` (#16186).

Extracted rather than left in place because `analytics_code_review.py` sits at
its ratchet ceiling: splitting a function within the file would have made it
longer, and the ceiling may shrink but never grow. Moving the two blocks out
satisfies the function-length guard and the size ratchet with one change.

Both are lifted verbatim -- the only edits are the parameters they now take
instead of closing over `analyze_diff`'s locals.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_7_DAYS

logger = get_logger(__name__)


async def collect_file_comments(files: list[dict[str, Any]], source_root: Path | None) -> list:
    """Analyse every reviewable file in the diff, skipping what is out of scope.

    A file that cannot be read is logged and skipped rather than failing the
    review: a diff naming a deleted or generated file is ordinary, and one
    unreadable path must not lose the findings from every other file.
    """
    # Late import: `analytics_code_review` imports this module, so binding these
    # at module scope would close the loop. Both names are defined there.
    from .analytics_code_review import REVIEWABLE_EXTENSIONS, analyze_code

    # Analyze each file
    all_comments = []
    for file_info in files:
        # Get full file content for analysis
        try:
            file_path = Path(file_info["path"])
            # Issue #3441: restrict to source_root when provided
            if source_root is not None:
                resolved = file_path.resolve()
                try:
                    resolved.relative_to(source_root.resolve())
                except ValueError:
                    logger.debug("Skipping file outside source_root: %s", file_info["path"])
                    continue
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(file_path.exists) and file_path.suffix in REVIEWABLE_EXTENSIONS:
                content = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="ignore")
                comments = analyze_code(content, str(file_path))
                all_comments.extend(comments)
        except Exception as e:
            logger.warning("Failed to analyze %s: %s", file_info["path"], e)
    return all_comments


async def persist_review(
    result_payload: dict[str, Any],
    review_id: str,
    analyzed_at: str,
    comment_count: int,
    score: Any,
    source_id: str | None,
) -> None:
    """Store the review and its history entry. Never raises.

    Persistence failing must not fail the review: the caller already has the
    findings and returns them regardless, so an unreachable Redis costs the
    history, not the analysis.
    """

    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            effective_source = source_id or "default"
            redis_key = f"code_review:result:{effective_source}:{review_id}"
            history_entry = {
                "id": review_id,
                "path": result_payload["path"],
                "analyzed_at": analyzed_at,
                "total_comments": comment_count,
                "score": score,
                "source_id": effective_source,
            }
            # redis.set writes to a different key than history ops — parallelize round-trips.
            await asyncio.gather(
                asyncio.to_thread(redis.set, redis_key, json.dumps(result_payload), "ex", TTL_7_DAYS),
                asyncio.to_thread(redis.lpush, f"code_review:history:{effective_source}", json.dumps(history_entry)),
            )
            # ltrim and expire both require lpush to have created the key first;
            # they are independent of each other so run them concurrently.
            await asyncio.gather(
                asyncio.to_thread(redis.ltrim, f"code_review:history:{effective_source}", 0, 99),
                asyncio.to_thread(redis.expire, f"code_review:history:{effective_source}", TTL_7_DAYS),
            )
            logger.info("Stored code review result %s for source %s", review_id, effective_source)
    except Exception as exc:
        logger.warning("Failed to persist code review result: %s", exc)
