# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deleting the facts a re-indexed file replaced (#20026; maintainer decision on #20028, 2026-10-30).

The sync may delete only what it created and nobody has touched: a fact it ingested, with no
update since and nothing marking it as protected. Each deletion is audited first, so an audit
failure keeps the fact. A fact that does not qualify stays in the KB, which #20015 accounts for.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("knowledge_sync_replacement")

SYNC_INGEST_ROUTE = "incremental_sync"
SYNC_AUDIT_ACTOR = "system:kb-sync"


def _is_protected(metadata: Dict[str, Any]) -> bool:
    """The no-data-loss predicate every automatic removal shares (#12554)."""
    from knowledge.facts import _fact_is_protected  # lazy: pulls in the whole knowledge stack

    return _fact_is_protected(metadata)


def is_replaceable(metadata: Dict[str, Any]) -> bool:
    """Did the sync create this fact, untouched since? ``update_fact`` stamps ``updated_at``."""
    return (
        metadata.get("ingest_route") == SYNC_INGEST_ROUTE
        and "updated_at" not in metadata
        and not _is_protected(metadata)
    )


async def _audit_deletion(fact_id: str, metadata: Dict[str, Any]) -> bool:
    """Write the deletion's audit entry; ``False`` means the fact must stay."""
    from services.audit.taxonomy import AuditAction
    from services.audit_logger import audit_log

    try:
        return bool(
            await audit_log(
                AuditAction.KNOWLEDGE_REMOVE.value,
                user_id=SYNC_AUDIT_ACTOR,
                resource=fact_id,
                details={"reason": "replaced by re-index", "relative_path": metadata.get("relative_path")},
            )
        )
    except Exception as exc:
        logger.warning("Audit failed, keeping replaced fact %s: %s", fact_id, exc)
        return False


async def _delete_one(kb: Any, fact_id: str) -> bool:
    fact = await asyncio.to_thread(kb.get_fact, fact_id)
    if not fact:
        return False  # already gone: nothing to delete, nothing to record
    metadata = fact.get("metadata") or {}
    if not is_replaceable(metadata):
        logger.info("Keeping replaced fact %s: edited, protected or not created by the sync", fact_id)
        return False
    if not await _audit_deletion(fact_id, metadata):
        return False
    result = await kb.delete_fact(fact_id)
    if isinstance(result, dict) and result.get("status") == "error":
        logger.warning("Failed to delete replaced fact %s: %s", fact_id, result.get("message"))
        return False
    return True


async def delete_replaced_facts(kb: Any, fact_ids: List[str]) -> int:
    """Delete each replaceable fact; returns how many went. One fact's failure never stops the rest."""
    results = await asyncio.gather(*[_delete_one(kb, fid) for fid in fact_ids], return_exceptions=True)
    for fact_id, result in zip(fact_ids, results):
        if isinstance(result, Exception):
            logger.warning("Failed to delete replaced fact %s: %s", fact_id, result)
    return sum(result is True for result in results)
