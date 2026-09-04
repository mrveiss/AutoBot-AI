# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which store is authoritative for each persisted concept (#15663).

AutoBot keeps the same datum in Redis, Postgres and ChromaDB, and until this
table existed nothing said which copy wins when they disagree. That is not a
theoretical race: #12733 watched ``facts/by_category`` go 43 -> 0 while 22
ChromaDB vectors survived, because Redis was the only durable home a fact had
and no rule said it shouldn't be.

Three rules, and this module is where they are stated:

1. **Every persisted concept names its system of record.** One store is durable
   and authoritative; :attr:`Concept.system_of_record` is that store.
2. **Every other copy is a rebuildable projection.** If a copy cannot be
   reconstructed from the system of record it is not a cache, it is a second
   original -- which is the defect. :attr:`Concept.rebuilt_by` names the code
   that does the reconstructing, so the claim is checkable rather than asserted.
3. **Derived status is computed, never stored beside the data.** A flag written
   next to a datum to describe another store's contents drifts the moment the
   two disagree; ask the other store instead.

The table lives in code rather than in ``docs/`` so it is reachable *from the
copy site*: a module that persists a concept calls :func:`system_of_record` at
import time, which fails loudly on a name this table does not know.
``repo_tests/store_authority_test.py`` holds the other direction -- a module
that durably writes to two stores without a declaration is a finding.

A Redis system of record is legal, and some of the entries below are exactly
that. What is not legal is an *unstated* one: :attr:`Concept.note` must say why
the datum is genuinely ephemeral, and the guard enforces that it is non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class Store(str, Enum):
    """A place bytes can outlive the process that wrote them."""

    POSTGRES = "postgres"
    REDIS = "redis"
    CHROMADB = "chromadb"
    DISK = "disk"


@dataclass(frozen=True)
class Concept:
    """One persisted concept, its authoritative store, and its copies."""

    name: str
    system_of_record: Store
    #: Every other store holding the same datum. Each must be rebuildable.
    projections: Tuple[Store, ...]
    #: Repo-relative modules that write this concept to any of its stores.
    write_sites: Tuple[str, ...]
    #: How a projection is reconstructed from the system of record -- a symbol,
    #: a command, or the sentence that makes the rebuild obvious. Rule 2 is only
    #: worth stating if the reconstruction actually exists.
    rebuilt_by: str
    #: Why this authority, and -- when the system of record is Redis -- why the
    #: datum is genuinely ephemeral. Required for a Redis system of record.
    note: str = ""


_FACTS = "autobot-backend/knowledge/facts.py"

#: Keyed by concept name. Ordered by store so a reader can see, in one pass,
#: which concepts share an authority.
STORE_AUTHORITY: dict[str, Concept] = {
    "knowledge_facts": Concept(
        name="knowledge_facts",
        system_of_record=Store.POSTGRES,
        projections=(Store.REDIS, Store.CHROMADB),
        write_sites=(
            _FACTS,
            "autobot-backend/knowledge/fact_store.py",
            "autobot-backend/knowledge/fact_projection.py",
            "autobot-backend/knowledge/ownership.py",
            "autobot-backend/api/knowledge_vectorization.py",
            "autobot-backend/background_vectorization.py",
        ),
        rebuilt_by="FactsMixin.rebuild_fact_projections() replays knowledge_facts rows into the "
        "fact:* hashes and their indexes; the ChromaDB vectors are rebuilt by re-embedding "
        "the row content (background_vectorization reconciles what is missing).",
        note="Redis with RDB snapshots was the only durable home a fact had, and #12733 lost 43 of "
        "them. The row is the fact; the hash is a read cache and the vector is an index.",
    ),
    "identity_and_rbac": Concept(
        name="identity_and_rbac",
        system_of_record=Store.POSTGRES,
        projections=(Store.REDIS,),
        write_sites=(
            "autobot-backend/user_management/middleware/rbac_middleware.py",
            "autobot-slm-backend/user_management/middleware/rbac_middleware.py",
            "autobot-slm-backend/user_management/services/sso_service.py",
        ),
        rebuilt_by="Every Redis entry is written with setex and re-derived from the users/roles/"
        "permissions tables on the next miss; the invalidation pubsub drops them early.",
    ),
    "llc_work": Concept(
        name="llc_work",
        system_of_record=Store.POSTGRES,
        projections=(Store.REDIS, Store.CHROMADB),
        write_sites=(
            "autobot-backend/llc/services/portability.py",
            "autobot-backend/llc/services/work_item_service.py",
            "autobot-backend/llc/services/handoff.py",
            "autobot-backend/llc/services/goal.py",
            "autobot-backend/llc/scheduler/heartbeat_scheduler.py",
            "autobot-backend/llc/scheduler/session_checkpointer.py",
        ),
        rebuilt_by="SessionCheckpointer re-adds due agents to the heartbeat sorted set from the "
        "run rows; the checkout keys are NX locks with a TTL and the H2A brief is a TTL cache. "
        "GoalService.upsert re-embeds a goal row, so the collection is rebuildable from Postgres.",
    ),
    "device_credentials": Concept(
        name="device_credentials",
        system_of_record=Store.POSTGRES,
        projections=(),
        write_sites=("autobot-backend/api/mobile_devices.py",),
        rebuilt_by="desktop_mobile_devices rows are the credential; nothing else stores one.",
    ),
    "verbatim_memory": Concept(
        name="verbatim_memory",
        system_of_record=Store.CHROMADB,
        projections=(Store.REDIS,),
        write_sites=(
            "autobot-backend/memory/verbatim_store.py",
            "autobot-backend/api/memory_privacy.py",
        ),
        rebuilt_by="VerbatimStore._index_symbolic re-tokenises a chunk into the inverted term "
        "index, so the Redis sets are reconstructible from the autobot_verbatim collection.",
        note="The chunks are on disk in ChromaDB and the collection is append-only; the Redis "
        "term index exists only to make exact-word search fast.",
    ),
    "code_index": Concept(
        name="code_index",
        system_of_record=Store.CHROMADB,
        projections=(Store.DISK,),
        write_sites=("autobot-backend/services/knowledge/code_indexer.py",),
        rebuilt_by="The cache file records which files were indexed and at what hash; deleting it "
        "costs a re-scan, not data, because the embeddings live in the collection.",
    ),
    "codebase_analytics": Concept(
        name="codebase_analytics",
        system_of_record=Store.CHROMADB,
        projections=(),
        write_sites=("autobot-backend/api/codebase_analytics/chromadb_storage.py",),
        rebuilt_by="Every row is derived from the repository by re-running the analysis.",
    ),
    "multimodal_vectors": Concept(
        name="multimodal_vectors",
        system_of_record=Store.CHROMADB,
        projections=(Store.REDIS,),
        write_sites=("autobot-backend/npu_semantic_search.py",),
        rebuilt_by="The Redis entries are embeddings cached under a TTL and are regenerated by "
        "the NPU on the next miss.",
    ),
    "chat_sessions": Concept(
        name="chat_sessions",
        system_of_record=Store.DISK,
        projections=(Store.REDIS,),
        write_sites=(
            "autobot-backend/chat_history/file_io.py",
            "autobot-backend/chat_history/session.py",
            "autobot-backend/chat_history/cache.py",
        ),
        rebuilt_by="ChatHistoryCacheMixin repopulates a session's cache entry from its session "
        "file on the next load; the file is written atomically and is the session.",
    ),
    "auth_signing_key": Concept(
        name="auth_signing_key",
        system_of_record=Store.DISK,
        projections=(),
        write_sites=("autobot-backend/auth_middleware.py",),
        rebuilt_by="The PEM on disk is the key. Regenerating it invalidates every issued token, "
        "which is why it is written once and never mirrored.",
    ),
    "auth_sessions": Concept(
        name="auth_sessions",
        system_of_record=Store.REDIS,
        projections=(),
        write_sites=("autobot-backend/auth_middleware.py",),
        rebuilt_by="Losing them logs users out; a new session is created by authenticating again.",
        note="Deliberate exception. A bearer session is a TTL'd capability, not user-owned state "
        "-- every entry is written with setex and the durable identity behind it is "
        "identity_and_rbac's Postgres rows.",
    ),
    "device_pairing_challenge": Concept(
        name="device_pairing_challenge",
        system_of_record=Store.REDIS,
        projections=(),
        write_sites=("autobot-backend/api/mobile_devices.py",),
        rebuilt_by="Losing a challenge means the user rescans the QR code.",
        note="Deliberate exception. The challenge is single-use and TTL'd; the credential it "
        "issues is device_credentials, which is durable in Postgres.",
    ),
    "autoresearch_proposal": Concept(
        name="autoresearch_proposal",
        system_of_record=Store.REDIS,
        projections=(),
        write_sites=("autobot-backend/services/knowledge/autonomous_loop.py",),
        rebuilt_by="An expired proposal is re-proposed by the next loop cycle.",
        note="Deliberate exception. The pending-approval payload is a 7-day handoff between the "
        "loop and its operator; the configuration it proposes is durable only once accepted.",
    ),
}


def system_of_record(concept: str) -> Concept:
    """The declared authority for *concept*, for a module that persists it.

    Called at module level by a write site so the declaration sits beside the
    code that writes the copy::

        SYSTEM_OF_RECORD = system_of_record("knowledge_facts")

    Raises:
        KeyError: the concept is not declared. A new persisted concept must be
            added to :data:`STORE_AUTHORITY` before it can be written, which is
            the whole point -- an undeclared concept is one nothing can check.
    """
    try:
        return STORE_AUTHORITY[concept]
    except KeyError:
        raise KeyError(
            f"{concept!r} has no declared system of record. Add it to "
            "autobot_shared/store_authority.py naming the store that is durable and "
            "authoritative for it, and how every other copy is rebuilt from that store (#15663)."
        ) from None
