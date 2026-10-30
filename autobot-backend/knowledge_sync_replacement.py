# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deleting the facts a re-indexed file replaced (#20026; maintainer decision on #20028, 2026-10-30).

The sync may delete only what it created and nobody has touched. "Untouched" is an allowlist, not
a list of known edits: tags, sharing and category writes each edit a fact their own way, so a
metadata key this module does not recognise keeps the fact, and so does any future writer's. Each
deletion's audit row is written first, so an audit failure keeps the fact. A fact that does not
qualify stays in the KB, which #20015 accounts for.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("knowledge_sync_replacement")

SYNC_INGEST_ROUTE = "incremental_sync"
SYNC_AUDIT_ACTOR = "system:kb-sync"

#: Every metadata key a sync chunk carries from ``_store_chunks_in_knowledge_base`` and ``store_fact``.
_SYNC_FACT_KEYS = frozenset(
    {
        "source",
        "relative_path",
        "filename",
        "file_size",
        "sync_time",
        "category",
        "visibility",
        "chunk_index",
        "total_chunks",
        "semantic_score",
        "sentence_count",
        "character_count",
        "gpu_optimized",
        "ingest_route",
        "injection_sanitized",
        "injection_rules_hit",
        "credential_redacted",
        "fact_id",
        "timestamp",
        "embedding_model",
        "content_fingerprint",
        "access_count",  # usage counters, surfaced on read
        "last_accessed",
    }
)


def _provenance_defaults() -> Dict[str, Any]:
    from knowledge.facts import _PROVENANCE_DEFAULTS  # lazy: pulls in the whole knowledge stack

    return _PROVENANCE_DEFAULTS


def _is_protected(metadata: Dict[str, Any]) -> bool:
    """The no-data-loss predicate every automatic removal shares (#12554)."""
    from knowledge.facts import _fact_is_protected  # lazy: pulls in the whole knowledge stack

    return _fact_is_protected(metadata)


def is_replaceable(metadata: Dict[str, Any]) -> bool:
    """Did the sync create this fact, with nothing on it beyond what the sync and the store wrote?"""
    if metadata.get("ingest_route") != SYNC_INGEST_ROUTE or _is_protected(metadata):
        return False
    defaults = _provenance_defaults()
    return all(
        key in _SYNC_FACT_KEYS or (key in defaults and value == defaults[key]) for key, value in metadata.items()
    )


async def _audit_deletion(fact_id: str, metadata: Dict[str, Any]) -> bool:
    """Write the deletion's audit row and wait for it; ``False`` means the fact must stay."""
    from services.audit import audit as canonical
    from services.audit.taxonomy import AuditAction, AuditCategory

    event = canonical.AuditEvent(
        category=AuditCategory.SECURITY,
        action=AuditAction.KNOWLEDGE_REMOVE.value,
        actor_id=SYNC_AUDIT_ACTOR,
        resource_type="knowledge_fact",
        resource_id=fact_id,
        metadata={"reason": "replaced by re-index", "relative_path": metadata.get("relative_path")},
    )
    try:
        return await canonical.record(event)
    except Exception as exc:
        logger.warning("Audit failed, keeping replaced fact %s: %s", fact_id, exc)
        return False


async def _delete_one(kb: Any, fact_id: str) -> bool:
    fact = await asyncio.to_thread(kb.get_fact, fact_id)
    if not fact:
        return False  # already gone: nothing to delete, nothing to record
    metadata = fact.get("metadata") or {}
    # A category assignment is a hash field beside the metadata, which get_fact does not return.
    category_id = await asyncio.to_thread(kb.redis_client.hget, f"fact:{fact_id}", "category_id")
    if category_id or not is_replaceable(metadata):
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
