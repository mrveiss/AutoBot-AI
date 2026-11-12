# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Zero-count Chroma collections: a read-only report and a removal that needs an approved request (#19725).

The knowledge health scan reads Redis facts only, so empty vector collections never showed up as a finding.
``scan_empty_collections`` lists them (and the collections it could not read, which are NOT reported as
empty). ``delete_empty_collection`` is reachable only from the post-approval handler, and re-checks at that
moment that the collection is still empty. A collection with no vectors cannot change a retrieval result, so
no retrieval-cache invalidation is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autobot_shared.logging_manager import get_logger
from services.approval_execution import register_post_approval_action
from services.kb_cleanup_proposals import record_outcome, require_context
from utils.async_chromadb_client import get_async_chromadb_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "chroma_empty_collection_delete"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.knowledge_chroma_empty"


@dataclass
class EmptyCollectionReport:
    """``unreadable`` collections could not be counted: never read them as empty."""

    total: int = 0
    empty: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)


async def scan_empty_collections() -> EmptyCollectionReport:
    """Count every collection and name those holding zero vectors (read-only)."""
    client = await get_async_chromadb_client()
    report = EmptyCollectionReport()
    for name in sorted(await client.list_collections()):
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
    client = await get_async_chromadb_client()
    collection = await client.get_collection_or_none(name)
    if collection is None:
        return False, "the collection no longer exists"
    count = await collection.count()
    if count != 0:
        return False, f"the collection now holds {count} vector(s); nothing deleted"
    await client.delete_collection(name)
    return True, None


async def execute_empty_collection_delete(approval: "Approval", session: "AsyncSession") -> None:
    """Delete the collection an approved gate named, and record what happened."""
    (name,) = require_context(approval, "collection")
    done, reason = await delete_empty_collection(name)
    await record_outcome(
        approval,
        session,
        operation="chroma.empty_collection_delete",
        done=done,
        resource=f"chroma:{name}",
        summary="Empty-collection cleanup",
        reason=reason,
    )


def register_cleanup_action() -> None:
    """Idempotent. Server-only: only the proposer route may create this approval."""
    register_post_approval_action(ACTION, execute_empty_collection_delete, proposed_by=PROPOSED_BY, server_only=True)
