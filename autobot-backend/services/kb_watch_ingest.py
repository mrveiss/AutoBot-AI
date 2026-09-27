# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/services/kb_watch_ingest.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge Base ingest for the watch-folder service.

Split out of ``kb_folder_watcher.py`` so the ingest can be exercised without
constructing an observer, and so the watcher keeps room under MAX_LINES.

The Knowledge Base write API is ``KnowledgeBase.add_document(content, metadata)``.
There is no ``add_fact`` method on it, and there never was: the watcher called
one for months. #13551 removed a missing ``await`` in front of
``get_knowledge_base()``, which turned ``AttributeError: 'coroutine' object has
no attribute 'add_fact'`` into ``AttributeError: 'KnowledgeBase' object has no
attribute 'add_fact'`` -- the same exception naming the same attribute, so no log
line distinguished the fixed code from the broken code and ingestion still never
landed a single file (#17022).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:  # WatchFolderConfig lives in the watcher, which imports this module.
    from services.kb_folder_watcher import WatchFolderConfig

logger = get_logger(__name__)

# A write whose content is now in the store. "duplicate" is a fact the Knowledge
# Base already holds under a returned id, which is a landed ingest and not an error:
# re-reading a watched file must not be reported as a failure.
STORED_STATUSES = ("success", "duplicate")


def build_watch_metadata(folder_id: str, config: "WatchFolderConfig", file_path: Path) -> Dict[str, Any]:
    """Metadata for one watched file.

    ``add_document`` takes only ``content``, ``metadata`` and ``doc_id``, so
    category and tags are metadata keys rather than parameters -- which is where
    the rest of the Knowledge Base reads them from (``knowledge/tags.py``,
    ``knowledge/search.py``).
    """
    return {
        "source": "watch_folder",
        "category": config.category,
        "tags": list(config.tags) + [f"watch_folder:{folder_id}"],
        "folder_id": folder_id,
        "filename": file_path.name,
        "file_path": str(file_path),
        "collection": config.collection,
    }


async def ingest_watched_file(
    folder_id: str,
    config: "WatchFolderConfig",
    file_path: Path,
    content: str,
) -> Dict[str, Any]:
    """Land one watched file's text in the Knowledge Base, returning its result dict."""
    from knowledge import get_knowledge_base

    # get_knowledge_base is a coroutine function: un-awaited it yields a coroutine
    # whose every attribute access raises AttributeError (#13551).
    kb = await get_knowledge_base()
    return await kb.add_document(content=content, metadata=build_watch_metadata(folder_id, config, file_path))


def ingest_stored(result: Dict[str, Any]) -> bool:
    """Whether a write result means the content is now in the Knowledge Base.

    ``add_document`` reports a rejection in its return value instead of raising, so
    a caller that never reads the result counts attempts rather than ingests.
    """
    return result.get("status") in STORED_STATUSES
