# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stable fact ids and the idempotent store for system knowledge (#18577).

The librarian's document bodies embed a timestamp, so the KB's content-hash dedup never matches a
re-import. One id per (kind, name) makes a repeat import update the fact instead of adding a copy.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Tuple

from autobot_shared.content_digest import content_digest
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: (kind) -> (metadata ``type`` the librarian stores it under, metadata field holding the name).
#: Legacy facts (stored before stable ids existed) are found by these two fields.
_KIND_METADATA = {
    "tool": ("tool_documentation", "tool_name"),
    "workflow": ("workflow_documentation", "workflow_name"),
    "procedure": ("system_documentation", "title"),
}

_FACT_ID_NAMESPACE = uuid.UUID("5f0c1d6e-0b7a-5c1e-9a55-18577a1b2c3d")

SYSTEM_SOURCE = "system_knowledge"
LINK_FIELD = "system_fact_id"
#: sha256 of the body the import last wrote. A body that no longer hashes to it was edited by a user.
IMPORT_HASH_FIELD = "system_import_hash"
#: sha256 of the template item the import last wrote from. Unchanged template -> nothing to write.
TEMPLATE_HASH_FIELD = "system_template_hash"


def system_fact_id(kind: str, name: str) -> str:
    """Stable fact id for a system-knowledge item (same kind+name -> same id, every run)."""
    return str(uuid.uuid5(_FACT_ID_NAMESPACE, f"{kind}:{name}"))


def text_digest(text: str) -> str:
    """sha256 of a fact body."""
    return content_digest(text)


def template_digest(item: Dict[str, Any]) -> str:
    """sha256 of one template item as the manager hands it to the librarian (timestamp-free)."""
    return text_digest(json.dumps(item, sort_keys=True, default=str))


class SystemFactStoreError(RuntimeError):
    """A store or update of a system-knowledge fact did not succeed; the item is retried next run."""


@dataclass(frozen=True)
class SystemFactRef:
    """Which fact a system-knowledge item is stored in, and what the import may do to it.

    - ``exists`` False: nothing stored yet, the item is created under ``stable_id``;
    - ``refreshable``: the import owns the fact AND its body still hashes to what the import last
      wrote, so a changed template may rewrite it;
    - otherwise (a legacy fact, a user-edited one, or one that carries no import hash to compare
      against): the text is never touched, the fact only gains the link id.
    """

    fact_id: str
    stable_id: str
    exists: bool = False
    refreshable: bool = False
    linked: bool = False
    template_hash: str = ""

    def action(self, template_hash: str) -> str:
        """``store`` | ``refresh`` | ``link`` | ``skip`` -- the one write this item needs, if any."""
        if not self.exists:
            return "store"
        if not self.refreshable:
            return "skip" if self.linked else "link"
        return "skip" if self.linked and self.template_hash == template_hash else "refresh"


def _stored_body(content: str, metadata: Dict[str, Any]) -> str:
    """The text the KB will actually persist for ``content`` (the write chokepoint redacts it)."""
    from knowledge.ingest_sanitize import sanitize_fact_content  # lazy: pulls the redaction stack

    return sanitize_fact_content(content, dict(metadata))[0]


def _checked(result: Any, what: str) -> Dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "success":
        raise SystemFactStoreError(f"{what} failed: {result}")
    return result


async def store_or_update_fact(
    knowledge_base: Any, content: str, metadata: Dict[str, Any], ref: Any = None, template_hash: str = ""
):
    """Store a fact. With a :class:`SystemFactRef` an existing fact is updated, never duplicated.

    - no ``ref``: behaviour unchanged (web research keeps its random ids and its source);
    - new item: stored under the stable id, tagged ``source=system_knowledge`` with the import hashes;
    - owned and unedited fact whose template changed: ``update_fact`` rewrites body and metadata;
    - any other existing fact (legacy, user-edited, unverifiable): only the link id is merged in;
    - nothing to change: no write at all.

    Raises :class:`SystemFactStoreError` when the KB reports anything but success.
    """
    if ref is None:
        return await knowledge_base.store_fact(content, metadata=metadata)
    action = ref.action(template_hash)
    if action == "skip":
        return {"status": "success", "action": "skipped", "fact_id": ref.fact_id}
    if action == "link":
        return _checked(
            await knowledge_base.update_fact(ref.fact_id, metadata={LINK_FIELD: ref.stable_id}),
            f"linking {ref.fact_id}",
        )
    body = _stored_body(content, metadata)
    metadata = {
        **metadata,
        "source": SYSTEM_SOURCE,
        LINK_FIELD: ref.stable_id,
        IMPORT_HASH_FIELD: text_digest(body),
        TEMPLATE_HASH_FIELD: template_hash,
    }
    if action == "refresh":
        return _checked(
            await knowledge_base.update_fact(ref.fact_id, content=body, metadata=metadata),
            f"refreshing {ref.fact_id}",
        )
    result = await knowledge_base.store_fact(body, metadata=metadata, fact_id=ref.fact_id)
    if isinstance(result, dict) and result.get("status") == "duplicate":
        return await _adopt_duplicate(knowledge_base, result, metadata, ref)
    return _checked(result, f"storing {ref.fact_id}")


def _unresolved(ref: Any, dup_id: str, why: str, *args: Any) -> Dict[str, Any]:
    """Leave the item unlinked: a warning with both ids (never content), not a retry-causing failure."""
    logger.warning("Item %s matched fact %s " + why + "; left unlinked", ref.stable_id, dup_id, *args)
    return {"status": "success", "action": "unresolved", "fact_id": dup_id}


def _system_writable(found: Any) -> bool:
    """Whether the matched fact may take a system import's write: read back, and no principal holds it."""
    from knowledge.ownership_index import is_ownerless_platform_fact  # lazy: pulls the ownership stack

    # A record with no metadata dict is unreadable, not ownerless: the predicate reads None as {} (#19296).
    meta = found.get("metadata") if isinstance(found, dict) else None
    return isinstance(meta, dict) and is_ownerless_platform_fact(meta)


async def _adopt_duplicate(knowledge_base: Any, result: Dict[str, Any], metadata: Dict[str, Any], ref: Any):
    """The KB matched the new body to an existing fact (exact hash or semantic): link it as the item.

    Text, type and name are never rewritten. Same kind (same ``type``, same or absent name): the link id
    (and the name, when absent) is merged in, so the next ``load()`` finds it and writes nothing. Another
    kind (a semantic match can be): ONLY the link id is merged; ``load()`` does not see it, so a later
    template-changed import re-checks that item once more -- an accepted cost.

    Reported ``unresolved`` and never written (#19296, #19216): a fact a user, org, group or share holds,
    or one not readable to check that; and one already linked to a DIFFERENT item.
    """
    dup_id = result.get("fact_id")
    if not dup_id or dup_id == "?":
        raise SystemFactStoreError(f"storing {ref.fact_id} reported a duplicate without its id: {result}")
    found = await asyncio.to_thread(knowledge_base.get_fact, dup_id)
    if not _system_writable(found):
        return _unresolved(ref, dup_id, "held by a principal or unreadable")  # a system job never writes it
    held = found.get("metadata") or {}
    linked_to = held.get(LINK_FIELD)
    if linked_to and linked_to != ref.stable_id:  # stealing the link would flip-flop the two items forever
        return _unresolved(ref, dup_id, "linked to %s", linked_to)
    name_field = next(f for t, f in _KIND_METADATA.values() if t == metadata["type"])
    merge: Dict[str, Any] = {LINK_FIELD: ref.stable_id}
    if held.get("type") != metadata["type"] or held.get(name_field) not in (None, metadata[name_field]):
        logger.info("Item %s matched fact %s of another kind; linked only", ref.stable_id, dup_id)
    elif held.get(name_field) is None:
        merge[name_field] = metadata[name_field]
    return _checked(await knowledge_base.update_fact(dup_id, metadata=merge), f"linking duplicate {dup_id}")


async def _durable_batches() -> AsyncIterator[List[Dict[str, Any]]]:
    """Batches of the durable facts whose metadata ``type`` is one the system import writes.

    ``fact_store.iter_facts`` pages 500 rows per query (keyset on created_at, id) until a page
    comes back empty: ``ceil(N/500) + 1`` SQL queries for N matching facts (1 when N is 0). Each is
    filtered in Postgres on ``metadata_json->>'type'``; there is no index on that JSON, so each is
    a table scan inside the database, but only matching rows cross the wire.
    """
    from knowledge import fact_store  # lazy: pulls in the DB layer
    from models.knowledge_fact import KnowledgeFact

    types = [kind_type for kind_type, _ in _KIND_METADATA.values()]
    where = (KnowledgeFact.metadata_json["type"].astext.in_(types),)
    async for batch in fact_store.iter_facts(where=where):
        yield batch


class SystemFactIds:
    """Resolves the fact an item is stored in and what the import may do to it (#18577).

    ``load()`` reads the existing system facts once per import run (paged, see
    :func:`_durable_batches`) and indexes them by (kind, name); ``of()`` then returns the existing
    fact's id (adopt it in place, whatever its id) or, when none exists, the stable uuid5 id.
    With several legacy facts for one item the oldest wins and the rest are left untouched.

    Only durable (Postgres) rows are seen. Every write since #15663 is durable-first, so a
    Redis-only fact can exist only on a node whose startup adoption (``adopt_legacy_facts``,
    fire-and-forget at KB creation) has not finished; an import racing that adoption can store a
    second copy of such a fact.
    """

    def __init__(self, batches: Callable[[], AsyncIterator[List[Dict[str, Any]]]] = _durable_batches) -> None:
        self._batches = batches
        self._existing: Dict[Tuple[str, str], Tuple[SystemFactRef, bool]] = {}

    @staticmethod
    def _ref_of(fact: Dict[str, Any], kind: str, name: str) -> Tuple[SystemFactRef, bool]:
        metadata = fact["metadata"]
        stable = system_fact_id(kind, name)
        owned = fact["fact_id"] == stable or metadata.get("source") == SYSTEM_SOURCE
        recorded = metadata.get(IMPORT_HASH_FIELD)
        pristine = owned and bool(recorded) and text_digest(fact["content"] or "") == recorded
        ref = SystemFactRef(
            fact_id=fact["fact_id"],
            stable_id=stable,
            exists=True,
            refreshable=pristine,
            linked=metadata.get(LINK_FIELD) == stable,
            template_hash=metadata.get(TEMPLATE_HASH_FIELD) or "",
        )
        return ref, owned

    async def load(self) -> None:
        by_type = {kind_type: (kind, field) for kind, (kind_type, field) in _KIND_METADATA.items()}
        existing: Dict[Tuple[str, str], Tuple[SystemFactRef, bool]] = {}
        async for batch in self._batches():
            for fact in batch:
                kind, field = by_type[fact["metadata"]["type"]]
                name = fact["metadata"].get(field)
                if not name:
                    continue
                candidate = self._ref_of(fact, kind, name)
                held = existing.get((kind, name))
                if held is None or (candidate[1] and not held[1]):  # oldest wins; an owned fact beats a legacy one
                    existing[(kind, name)] = candidate
        self._existing = existing
        logger.info("Indexed %d existing system-knowledge facts", len(existing))

    def of(self, kind: str, name: str) -> SystemFactRef:
        held = self._existing.get((kind, name))
        if held is not None:
            return held[0]
        stable = system_fact_id(kind, name)
        return SystemFactRef(fact_id=stable, stable_id=stable)
