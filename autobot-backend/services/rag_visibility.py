# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Visibility for RAGService (#16664): who may read a result, and which cache a result may sit in.

``RAGService.advanced_search`` takes a required principal. Every leg that returns KB content
(the optimizer, both fallbacks, the mesh retriever, the docs merge and the three cache tiers)
filters through :func:`filter_ranked`, which is ``knowledge.search_filters.filter_for_principal``
over ``RankedResult`` objects -- there is no second visibility model. The caches are partitioned
by :func:`cache_scope`, which also carries the ACL epoch so a revoked share orphans every entry.
"""

import hashlib
from typing import List

from advanced_rag_optimizer import RankedResult
from autobot_shared.logging_manager import get_llm_logger
from knowledge.acl_epoch import read_acl_epoch
from knowledge.search_filters import SYSTEM_SCOPE, KbPrincipal, filter_for_principal, require_kb_principal

logger = get_llm_logger("rag_visibility")

#: A post-filter can only remove results, so each leg asks its source for this multiple of what
#: the caller wants; the top-k then survives the facts the caller may not read.
VISIBILITY_OVERFETCH = 2

#: Key under which a semantic-cache hit keeps the top result's ownership metadata, so the hit
#: can be post-filtered like any other result.
RESULT_METADATA_KEY = "result_metadata"


def scope_key(principal: KbPrincipal, epoch: str) -> str:
    """The cache partition of *principal* at ACL *epoch*.

    Two principals share a partition only when user, org and groups all match; the epoch makes a
    revocation orphan every earlier partition. ``SYSTEM_SCOPE`` has its own readable key.
    """
    if principal is SYSTEM_SCOPE:
        return f"system|{epoch}"
    raw = f"{principal.user_id}|{principal.company_id or ''}|{','.join(sorted(principal.group_ids))}|{epoch}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def cache_scope(principal: KbPrincipal) -> str | None:
    """The cache scope key for *principal*, or ``None`` when the epoch cannot be read.

    ``None`` means every cache tier is skipped for this search -- read and write alike -- since an
    entry cannot be shown to predate a revocation.
    """
    epoch = await read_acl_epoch()
    if epoch is None:
        return None
    return scope_key(require_kb_principal(principal), epoch)


async def filter_ranked(results: List[RankedResult], principal: KbPrincipal, ownership_manager) -> List[RankedResult]:
    """The *results* the principal may read, in their original order."""
    wrapped = [
        {"id": (r.metadata or {}).get("fact_id", ""), "metadata": r.metadata or {}, "idx": i}
        for i, r in enumerate(results)
    ]
    kept = await filter_for_principal(wrapped, principal, ownership_manager)
    dropped = len(wrapped) - len(kept)
    if dropped:
        logger.debug("RAG visibility dropped %d/%d result(s)", dropped, len(wrapped))
    return [results[w["idx"]] for w in kept]
