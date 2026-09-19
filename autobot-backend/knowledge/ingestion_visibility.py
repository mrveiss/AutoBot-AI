# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which ownerless facts are ingested documents, and so visible to every signed-in user (#16693).

Owner decisions on #16693 (2026-09-14): documents only. A fact nobody owns is SYSTEM if it
came in through a connector, an admin file upload, a man-page import, the documentation
KB, the system-command reference, or the documentation part of the admin repo sync.
Every other ownerless fact stays private: chat, agent and LLC diaries, fact extraction,
audio or video transcripts, and the repo sync's reports, security docs and source code.

``source_type`` cannot tell these apart. ``_apply_provenance_defaults`` stamps
``manual_upload`` on every fact that sets none, diaries and extraction output included.
So each class is recognised by a positive marker that only its own writer sets. The
classes a free-text or caller-supplied field could imitate are excluded outright.

New ingestion is stamped at each trusted site, never at a generic chokepoint, because a
caller-supplied metadata dict (the MCP add route) could carry a marker. A site applies
:func:`stamp_if_document` to metadata it built itself, or writes
:data:`INGESTED_DOCUMENT_VISIBILITY` directly. The backfill uses the same predicate on
facts already stored.
"""

from typing import Any, Dict, Optional

#: What a trusted ingestion site writes on a fact nobody owns. Pinned to
#: ``VisibilityLevel.SYSTEM`` by its test; a literal so ingestion modules import nothing heavy.
INGESTED_DOCUMENT_VISIBILITY = "system"

#: What the backfill merges into a fact: the visibility, and a tag to find and reverse it by.
BACKFILL_MARK = {"visibility": INGESTED_DOCUMENT_VISIBILITY, "visibility_backfill": "16693"}

#: ``source`` values written only by the admin-only population router and the man-page parser.
_SOURCE_CLASSES = {
    "manual_pages_population": "man_page",
    "man_page_parser": "man_page",
    "autobot_docs_population": "documentation",
    "system_commands_population": "system_commands",
}
#: Categories of the admin repo sync (``source: project-documentation``) that are SYSTEM.
#: Its ``reports``, ``security`` and ``source-code`` categories stay private (#16693).
_REPO_SYNC_DOCUMENT_CATEGORIES = frozenset(
    {"user-guide", "developer-docs", "api-docs", "architecture", "troubleshooting", "project-overview", "documentation"}
)
#: A fact carrying any of these is never an ingested document, whatever else it says. A
#: diary's ``source`` is its agent's id, free text; extraction spreads caller metadata.
_NEVER_DOCUMENT = (("category", "AGENT_DIARY"), ("type", "atomic_facts"), ("source_type", "chat"))
#: Fields that file a fact under a person, organisation, group, share or board.
_OWNED_OR_SCOPED = ("owner_id", "user_id", "organization_id", "group_ids", "shared_with", "board_id")


def ingested_document_class(metadata: Dict[str, Any]) -> Optional[str]:
    """The ingestion class *metadata*'s marker names, or ``None`` when it names none."""
    if any(metadata.get(key) == value for key, value in _NEVER_DOCUMENT):
        return None
    if metadata.get("source_type") == "connector":
        return "connector"
    if metadata.get("type") == "file" and metadata.get("filename"):
        return "file_upload"
    if metadata.get("category") == "system/manpages" and metadata.get("machine_id"):
        return "man_page"
    source, category = metadata.get("source"), metadata.get("category")
    if source == "project-documentation":
        return "documentation" if isinstance(category, str) and category in _REPO_SYNC_DOCUMENT_CATEGORIES else None
    return _SOURCE_CLASSES.get(source) if isinstance(source, str) else None


def _unclaimed(metadata: Dict[str, Any]) -> bool:
    """No visibility yet, and nobody owns it or scopes it to an organisation, group, share or board."""
    return not metadata.get("visibility") and not any(metadata.get(key) for key in _OWNED_OR_SCOPED)


def system_backfill_class(metadata: Dict[str, Any]) -> Optional[str]:
    """The class of an unclaimed ingested document; ``None`` for any other fact.

    This is the backfill's whole selection: a fact with an owner, a visibility, or any
    organisation, group, share or board is never touched.
    """
    return ingested_document_class(metadata) if _unclaimed(metadata) else None


def stamp_if_document(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Mark *metadata* SYSTEM when it describes an unclaimed ingested document; otherwise leave it.

    For a trusted ingestion site whose output varies. A connector copies its source's
    metadata, which may already name an owner or a visibility, and that choice stands.
    The repo sync keeps its reports, security docs and source code private.
    """
    if system_backfill_class(metadata):
        metadata["visibility"] = INGESTED_DOCUMENT_VISIBILITY
    return metadata
