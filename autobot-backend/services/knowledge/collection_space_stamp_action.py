# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an approved request to record a collection's embedding space on its metadata (#18143, #17038).

The proposer (``services.knowledge.collection_space_proposal``) files an approval-gate request whose context
names this action. Nothing stamps a collection until a human approves it. On approval the handler:

* re-reads the collection and one stored vector's dimension, and REFUSES if that no longer equals the
  dimension the proposal named, or if the collection now records a different space;
* merges (model, dim) into the existing metadata through ``BaseCollection.modify_metadata``, never a replace.
  The model is INFERRED from a dimension match, not observed; the proposal and the comment both say so;
* reads the metadata back and fails loudly unless the space is recorded;
* leaves an ApprovalComment and an audit entry either way.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from autobot_shared.embedding_provenance import EmbeddingProvenance, provenance_from_metadata, provenance_to_metadata
from autobot_shared.paths import chromadb_data_dir
from models.approval import ApprovalComment
from services.approval_execution import register_post_approval_action
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

ACTION = "stamp_collection_embedding_space"
PROPOSED_BY = "services.knowledge.collection_space_proposal"


def _open_collection(name: str):
    from knowledge.backends import get_default_client

    return get_default_client(db_path=str(chromadb_data_dir())).get_collection(name)


def _stored_dim(collection) -> int | None:
    embs = collection.peek(limit=1).get("embeddings")
    return len(embs[0]) if embs is not None and len(embs) > 0 and embs[0] is not None else None


def _stamp(name: str, want: EmbeddingProvenance) -> str | None:
    """Stamp ``name`` with ``want``. Returns the reason it was refused, or None once it is recorded."""
    collection = _open_collection(name)
    recorded = provenance_from_metadata(collection.metadata)
    if recorded is not None and recorded != want:
        return f"the collection now records {recorded.model_name} / {recorded.dim}-d, not the proposed space"
    stored = _stored_dim(collection)
    if stored != want.dim:
        return f"its stored vectors are {stored}-d now, the proposal named {want.dim}-d"
    if recorded is None:
        collection.modify_metadata(provenance_to_metadata(want))
        if provenance_from_metadata(_open_collection(name).metadata) != want:
            raise RuntimeError(f"the space did not read back from collection '{name}' after the stamp")
    return None


async def _write_trail(approval: "Approval", session: "AsyncSession", body: str, result: str, **details: Any) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await audit_log(
        "collection.stamp_embedding_space",
        result=result,
        user_id=approval.decided_by_user,
        resource=str((approval.context or {}).get("collection")),
        details={"approval_id": str(approval.id), **details},
    )


async def execute_stamp(approval: "Approval", session: "AsyncSession") -> None:
    """Record the proposed space on the collection once a human has approved."""
    ctx = approval.context or {}
    name, want = str(ctx["collection"]), EmbeddingProvenance(str(ctx["model"]), int(ctx["dim"]))
    refusal = await asyncio.to_thread(_stamp, name, want)
    if refusal:
        await _write_trail(
            approval, session, f"Stamp REFUSED, nothing was written: {refusal}.", "refused", reason=refusal
        )
        return
    body = (
        f"Recorded embedding space ({want.model_name}, {want.dim}-d) on '{name}'; existing metadata kept. "
        "The model was INFERRED from a dimension match, not observed (dimension match only, model unverified)."
    )
    await _write_trail(approval, session, body, "success", model=want.model_name, dim=want.dim)


def register_stamp_action() -> None:
    """Idempotent registration of the executor, with its declared proposer."""
    register_post_approval_action(ACTION, execute_stamp, proposed_by=PROPOSED_BY)


__all__ = ["ACTION", "PROPOSED_BY", "execute_stamp", "register_stamp_action"]
