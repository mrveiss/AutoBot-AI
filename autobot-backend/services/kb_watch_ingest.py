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


#: How many documents one watched path may resolve to. A path should map to one
#: document; a higher cap exists so a duplicate ingest is cleaned up rather than
#: half-removed, and so the count is reportable when it is not 1.
MAX_REMOVAL_MATCHES = 25


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


#: How many collections one page of `list_collections` returns while resolving. The
#: resolver pages to completion rather than trusting one call -- `list_collections`
#: defaults to 100 and a watched folder naming the 101st collection must not be told
#: it does not exist (#17533, and the same shape as #17713).
_COLLECTION_PAGE = 100


async def resolve_collection_id(name: str) -> Dict[str, Any]:
    """Resolve a collection NAME to the UUID the store is keyed by (#17533).

    Collections are keyed by a UUID minted at creation (`knowledge/collections.py`),
    while `WatchFolderConfig.collection` is user-authored text. Nothing joined the two,
    so a watched folder never reached the collection it named.

    **This refuses; it never creates.** Owner ruling, 2026-09-28: an unknown name is an
    error the operator sees, not a new collection. A typo in a config string would
    otherwise mint a durable collection and ingest into it, with nothing to mark it as
    unintended -- and creating stored data as a side effect of a name lookup is not a
    decision this path gets to make. Create-on-first-use remains available later as a
    deliberate, gated feature.

    Returns a status that separates three outcomes an empty result cannot:

    ``resolved``    ``collection_id`` is the id to store
    ``not_found``   the listing was read in full and no collection carries this name
    ``error``       the listing could not be read, so nothing is known

    The ``not_found`` message names the collections that DO exist, because a refusal an
    operator cannot act on is only marginally better than a silent drop.
    """
    from knowledge import get_knowledge_base

    wanted = (name or "").strip()
    if not wanted:
        return {"status": "error", "message": "watch folder has no collection configured"}

    kb = await get_knowledge_base()
    seen: list[str] = []
    offset = 0
    while True:
        page = await kb.list_collections(limit=_COLLECTION_PAGE, offset=offset)
        if not page.get("success"):
            return {
                "status": "error",
                "message": f"could not list collections: {page.get('message', 'no message')}",
            }
        for collection in page.get("collections") or []:
            found_name = (collection.get("name") or "").strip()
            if found_name == wanted:
                return {"status": "resolved", "collection_id": collection.get("id")}
            seen.append(found_name)
        if not page.get("has_more"):
            break
        offset += _COLLECTION_PAGE

    known = ", ".join(sorted(n for n in seen if n)) or "none"
    return {
        "status": "not_found",
        "message": f"no collection is named {wanted!r}; collections that exist: {known}",
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
    resolved = await resolve_collection_id(config.collection)
    if resolved["status"] != "resolved":
        # #17533: refuse rather than store into a collection that does not exist. The
        # result shape matches `add_document`'s so `ingest_stored` reads it correctly --
        # a rejection here must look like a rejection, not like a write that happened.
        return {
            "status": "rejected",
            "message": f"collection routing failed: {resolved['message']}",
            "collection_status": resolved["status"],
        }

    kb = await get_knowledge_base()
    metadata = build_watch_metadata(folder_id, config, file_path)
    # The store is keyed by id; the name is kept beside it so a human reading a stored
    # document still sees what the folder was configured with (#17533).
    metadata["collection_name"] = metadata["collection"]
    metadata["collection"] = resolved["collection_id"]
    return await kb.add_document(content=content, metadata=metadata)


def ingest_stored(result: Dict[str, Any]) -> bool:
    """Whether a write result means the content is now in the Knowledge Base.

    ``add_document`` reports a rejection in its return value instead of raising, so
    a caller that never reads the result counts attempts rather than ingests.
    """
    return result.get("status") in STORED_STATUSES


async def remove_watched_file(file_path: Path) -> Dict[str, Any]:
    """Remove Knowledge Base documents previously ingested from *file_path* (#17546).

    A watched file that is deleted or renamed leaves its document behind; nothing
    read the watcher's `change_type` to notice. Documents are addressed by the
    ``file_path`` metadata key that :func:`build_watch_metadata` already records,
    rather than by a doc_id derived from the path -- a derived id would only address
    documents ingested after this change, so the delete would silently do nothing for
    exactly the backlog the feature exists for.

    Returns a result dict whose ``status`` distinguishes THREE outcomes that an empty
    list cannot:

    ``removed``     the documents were found and deleted (``removed`` counts them)
    ``not_found``   the search ran and matched nothing
    ``error``       the search or a delete failed, so nothing is known

    That split matters because ``search_by_metadata`` returns ``fact_ids: []`` on
    both a clean miss and an internal failure, separating them only by ``status`` --
    a caller reading the list alone would report "nothing to remove" for a failed
    lookup.

    KNOWN CEILING: ``search_by_metadata`` scans only the first 500 fact keys
    (``knowledge/metadata.py``), so on a large Knowledge Base a document can exist
    and not be found. That is why ``not_found`` is a reportable outcome here rather
    than a quiet success -- the caller records it, so an unremovable document is
    visible instead of being indistinguishable from a file that was never ingested.
    """
    from knowledge import get_knowledge_base

    kb = await get_knowledge_base()
    # Unfiltered by design, classified NOT_USER_FACING in the #16654 allowlist
    # (_WATCH_RECONCILE): this runs from a filesystem observer with no user in context, and
    # scoping a reconciliation delete to one user's view would skip the rows that user cannot
    # see -- leaving documents for deleted files that nothing could then remove.
    found = await kb.search_by_metadata("file_path", str(file_path), limit=MAX_REMOVAL_MATCHES)
    if found.get("status") != "success":
        return {
            "status": "error",
            "message": f"metadata search failed: {found.get('message', 'no message')}",
            "removed": 0,
        }

    fact_ids = found.get("fact_ids") or []
    if not fact_ids:
        return {
            "status": "not_found",
            "message": ("no knowledge-base document records this file_path (searched the first 500 fact keys)"),
            "removed": 0,
        }

    removed = 0
    failures = []
    for fact_id in fact_ids:
        try:
            await kb.delete_fact(fact_id)
            removed += 1
        except Exception as exc:  # noqa: BLE001 - one failure must not strand the rest
            failures.append(f"{fact_id}: {type(exc).__name__}: {exc}")

    if failures:
        return {
            "status": "error",
            "message": f"removed {removed} of {len(fact_ids)}; failed: {'; '.join(failures)}",
            "removed": removed,
        }
    return {"status": "removed", "removed": removed}
