# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Zero-count knowledge-base Chroma collections: a read-only report, removal only after approval (#19725).

The knowledge health scan reads Redis facts only, so empty vector collections never showed up as a finding.
``scan_empty_collections`` lists them (and the collections it could not read, which are NOT reported as
empty). ``delete_empty_collection`` is reachable only from the post-approval handler, and re-checks at that
moment that the collection is still empty, under the collection's exclusive write lease so no write can land
between the count and the delete (a collection being written to is kept). A collection with no
vectors cannot change a retrieval result, so no retrieval-cache invalidation is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autobot_shared.coordination.collection_lease import CollectionLeaseUnavailable
from autobot_shared.logging_manager import get_logger
from knowledge.graph_buckets import FACT_VECTOR_COLLECTIONS, section_for
from services.approval_execution import register_post_approval_action
from services.kb_cleanup_proposals import record_cleanup_outcome, require_context
from utils.async_chromadb_client import get_async_chromadb_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "chroma_empty_collection_delete"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.knowledge_chroma_empty"


def is_kb_collection(name: str) -> bool:
    """True for a collection the knowledge base owns: a graph bucket section or the fact-vector collection.

    The registry is ``knowledge.graph_buckets``; a collection outside it (another subsystem's, a cache, a
    scratch benchmark) is never reported here, so it can never be proposed for deletion from this surface.
    """
    return section_for(name) is not None or name in FACT_VECTOR_COLLECTIONS


@dataclass
class EmptyCollectionReport:
    """``unreadable`` collections could not be counted: never read them as empty."""

    total: int = 0
    empty: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)


async def scan_empty_collections() -> EmptyCollectionReport:
    """Count every knowledge-base collection and name those holding zero vectors (read-only)."""
    client = await get_async_chromadb_client()
    report = EmptyCollectionReport()
    for name in sorted(n for n in await client.list_collections() if is_kb_collection(n)):
        report.total += 1
        try:
            count = await (await client.get_collection(name)).count()
        except Exception as exc:  # one broken collection must not hide the rest
            logger.warning("Could not count Chroma collection %s: %s", name, exc)
            report.unreadable.append(name)
            continue
        if count == 0:
            report.empty.append(name)
    return report


async def delete_empty_collection(name: str) -> tuple[bool, str | None]:
    """Delete *name* if it exists and is still empty; (done, reason). Only the approval handler calls this."""
    if not is_kb_collection(name):  # defence in depth: an approval's context is data, not a registry
        return False, "the collection is not a knowledge-base collection; nothing deleted"
    client = await get_async_chromadb_client()
    collection = await client.get_collection_or_none(name)
    if collection is None:
        return False, "the collection no longer exists"
    try:
        count = await client.delete_collection_if_empty(name)
    except CollectionLeaseUnavailable as exc:  # a writer holds the collection, or the lease lapsed: did not run
        logger.warning("Empty-collection delete of %s did not run: %s", name, exc)
        return False, "a write to the collection is in progress or the delete lease was lost; nothing deleted"
    except Exception as exc:  # an unreachable lease registry, count or delete failure: nothing was deleted
        logger.warning("Empty-collection delete of %s did not run: %s", name, exc)
        return False, f"the delete did not run ({type(exc).__name__}); nothing deleted"
    if count != 0:
        return False, f"the collection now holds {count} vector(s); nothing deleted"
    return True, None


async def execute_empty_collection_delete(approval: "Approval", session: "AsyncSession") -> None:
    """Delete the collection an approved gate named, and record what happened."""
    (name,) = require_context(approval, "collection")
    done, reason = await delete_empty_collection(name)
    await record_cleanup_outcome(
        approval,
        session,
        operation="chroma.empty_collection_delete",
        done=done,
        resource=f"chroma:{name}",
        summary="Empty-collection cleanup",
        reason=reason,
    )


def register_empty_collection_delete() -> None:
    """Idempotent. Server-only and admin-decided: this approves deleting a stored vector collection."""
    register_post_approval_action(
        ACTION, execute_empty_collection_delete, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )
