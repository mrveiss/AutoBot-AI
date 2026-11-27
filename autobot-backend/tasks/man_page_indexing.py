# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Celery refresh's man-page indexing, called in-process (#22272).

This used to shell out to ``index_all_man_pages.py`` and parse the indexed count out of
its stdout (#15853) -- but the script logs to stderr, so the counts were always 0, and the
script path was a second thing that could resolve nowhere. It now awaits the canonical
``services.man_page_ingestion.index_all_man_pages`` and uses its return value. Kept out of
``knowledge_tasks``, which sits at its file-size ceiling (#14236).
"""

from autobot_shared.logging_manager import get_logger
from services.man_page_ingestion import ManPageIndexingError, index_all_man_pages

logger = get_logger(__name__)


async def run_man_page_indexing() -> dict:
    """Index all man pages and return the refresh task's success dict.

    A known indexing failure (no knowledge base, no man pages, storage rejecting every page)
    returns ``failed`` with its message, which is a fixed diagnostic safe to show an admin; any
    other failure propagates and the Celery task reports the generic ``failed``.
    """
    try:
        counts = await index_all_man_pages()
    except ManPageIndexingError as exc:
        logger.error("System knowledge refresh could not run: %s", exc)
        return {"status": "failed", "error": str(exc), "message": "Knowledge refresh failed"}
    logger.info(
        "System knowledge refresh complete: %d commands indexed, %d total facts",
        counts["commands_indexed"],
        counts["total_facts"],
    )
    return {
        "status": "success",
        "commands_indexed": counts["commands_indexed"],
        "storage_failed": counts["storage_failed"],
        "total_facts": counts["total_facts"],
        "message": "System knowledge refreshed successfully",
    }
