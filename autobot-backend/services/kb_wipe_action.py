# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wipe the knowledge base only through an approved proposal (#21048, #17038).

The KB setup script used to drop every search index and flush ten Redis databases on a bare invocation.
That is a data deletion, so it is now only *proposed*: an admin (or the operator script) raises an
ordinary approval gate, ``approval_type=destructive_action``, and nothing is deleted until a human
approves it. Approval runs :func:`execute_kb_wipe_action` through the ``services.approval_execution``
registry, which records a comment on the approval and a durable audit entry naming who approved, when,
and every store deleted with its counts.

Scope is the knowledge database and the search indexes living in it (``KB_WIPE_DATABASES``), plus the
KB's own ChromaDB collections, where its embeddings live (``services.kb_wipe_chroma``). The
handler never reads its scope from the approval, so a proposal cannot widen it. ``vectors`` is
deliberately absent: it is an alias of the logs database, not a store of its own.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import decode_redis_list, decode_redis_value
from models.approval import ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_execution import register_post_approval_action, verified_decider
from services.audit_logger import audit_log
from services.kb_wipe_chroma import ChromaFactory, clear_chroma, plan_chroma

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "kb_wipe"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.kb_wipe_action"
#: Redis databases the wipe may touch. Knowledge only; sessions, settings and queues are never listed.
KB_WIPE_DATABASES: tuple[str, ...] = ("knowledge",)
#: ``Approval.title`` is ``String(255)``.
PROPOSAL_TITLE = "Wipe the knowledge base (indexes and documents)"

ClientFactory = Callable[[str], Any]


def _default_client(database: str):
    from autobot_shared.redis_client import get_redis_client

    return get_redis_client(database=database)


def _index_documents(client, name: str) -> int:
    """Indexed document count from ``FT.INFO``; 0 when the reply has no ``num_docs``."""
    info = decode_redis_list(client.execute_command("FT.INFO", name))
    return int(info[info.index("num_docs") + 1]) if "num_docs" in info else 0


def _database_plan(client, database: str) -> dict:
    indexes = [decode_redis_value(name) for name in client.execute_command("FT._LIST") or []]
    return {
        "database": database,
        "keys": int(client.dbsize()),
        "indexes": [{"name": name, "documents": _index_documents(client, name)} for name in indexes],
    }


def _plan_redis(client_factory: ClientFactory) -> list[dict]:
    stores = []
    for database in KB_WIPE_DATABASES:
        client = client_factory(database)
        if client is None:
            raise RuntimeError(f"Redis database {database!r} is unavailable; the wipe plan cannot be built")
        stores.append(_database_plan(client, database))
    return stores


async def plan_kb_wipe(
    client_factory: ClientFactory = _default_client, chroma_factory: ChromaFactory | None = None
) -> dict:
    """Read only: what a wipe would delete (Redis KB database and Chroma KB collections), with counts."""
    stores = await asyncio.to_thread(_plan_redis, client_factory)
    collections = await plan_chroma(chroma_factory)
    return {
        "databases": stores,
        "chroma_collections": collections,
        "total_keys": sum(s["keys"] for s in stores),
        "total_vectors": sum(c["vectors"] for c in collections),
    }


def execute_wipe(client_factory: ClientFactory = _default_client) -> list[dict]:
    """Drop the KB search indexes (with their documents), then flush the KB database; return what went."""
    deleted = []
    for database in KB_WIPE_DATABASES:
        client = client_factory(database)
        if client is None:
            raise RuntimeError(f"Redis database {database!r} is unavailable; nothing was deleted from it")
        store = _database_plan(client, database)
        for index in store["indexes"]:
            client.execute_command("FT.DROPINDEX", index["name"], "DD")
        client.flushdb()
        deleted.append(store)
    return deleted


async def propose_kb_wipe(session: "AsyncSession", requested_by: str, plan: dict) -> "Approval":
    """Raise (or reuse the pending) #17038 proposal to wipe the KB. Deletes nothing."""
    from sqlalchemy import select

    from models.approval import Approval
    from services.approval_gate_service import ApprovalGateService

    query = select(Approval).where(
        Approval.status == ApprovalStatus.PENDING.value, Approval.context["action"].astext == ACTION
    )
    if (pending := (await session.execute(query)).scalars().first()) is not None:
        return pending
    return await ApprovalGateService(session).create_approval(
        title=PROPOSAL_TITLE,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=(
            "Drops the knowledge search indexes, flushes the knowledge database and empties the knowledge "
            "ChromaDB collections. Nothing else is touched."
        ),
        requested_by_agent=f"kb-wipe:{requested_by}",
        context={"action": ACTION, "requested_by": requested_by, "databases": list(KB_WIPE_DATABASES), "plan": plan},
    )


async def _audit(approval: "Approval", result: str, stores: list[dict], chroma: list[dict], error: str | None = None):
    await audit_log(
        "knowledge.wipe",
        result=result,  # type: ignore[arg-type]
        user_id=approval.decided_by_user,
        resource="knowledge_base",
        details={
            "approval_id": str(approval.id),
            "approved_by": approval.decided_by_user,
            "approved_at": approval.decided_at.isoformat() if approval.decided_at else None,
            "stores": stores,
            "chroma_collections": chroma,
            "error": error,
        },
    )


async def _wipe(approval: "Approval") -> tuple[list[dict], list[dict]]:
    """Redis first, then Chroma; a failure audits what was already deleted before it re-raises."""
    stores: list[dict] = []
    chroma: list[dict] = []
    try:
        stores.extend(await asyncio.to_thread(execute_wipe))
        chroma.extend(await clear_chroma())
    except Exception as exc:
        await _audit(approval, "failed", stores, chroma, error=type(exc).__name__)
        raise
    return stores, chroma


async def execute_kb_wipe_action(approval: "Approval", session: "AsyncSession") -> None:
    """Wipe the KB for an approved gate, and record exactly what went."""
    if verified_decider(approval) is None:
        raise ValueError(f"approval {approval.id} has no verified decider; the wipe is refused")
    stores, chroma = await _wipe(approval)
    body = "Knowledge wipe done: " + ", ".join(
        [f"{s['database']} ({s['keys']} keys, {len(s['indexes'])} indexes)" for s in stores]
        + [f"chroma {c['name']} ({c['vectors']} vectors)" for c in chroma]
    )
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()
    await _audit(approval, "success", stores, chroma)


def register_kb_wipe_action() -> None:
    """Idempotent: re-registering replaces the same key with an equal handler."""
    register_post_approval_action(
        ACTION, execute_kb_wipe_action, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )


__all__ = [
    "ACTION",
    "KB_WIPE_DATABASES",
    "PROPOSED_BY",
    "execute_kb_wipe_action",
    "execute_wipe",
    "plan_kb_wipe",
    "propose_kb_wipe",
    "register_kb_wipe_action",
]
