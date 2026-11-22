# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Redis half of the approved knowledge wipe (#21048, #17038).

Nothing here flushes a database. The ``knowledge`` database also holds settings that are not KB data, such
as the embedding-model override (``autobot_shared.embedding_model.EMBEDDING_OVERRIDE_KEY``), so the wipe
drops the KB's own search index and unlinks only the keys under ``KB_KEY_PREFIXES``. Every other key survives.

RediSearch indexes are global to the server, so ``FT._LIST`` also names indexes of other components. The wipe
drops only the index names ``knowledge.index_scope.kb_index_names`` returns, and the executor acts only on the
scope frozen in the approved plan (``frozen_redis_scope``): it never lists indexes to decide what to drop.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.redis_utils import decode_redis_list, decode_redis_value
from knowledge.index_scope import kb_index_names

#: Redis databases the wipe may touch. Knowledge only; sessions, settings and queues are never listed.
KB_WIPE_DATABASES: tuple[str, ...] = ("knowledge",)
#: Key families in the ``knowledge`` database that are DERIVED from KB content, so they go with it. Entries are
#: SCAN patterns (a ``*`` inside is a glob). Each family's database was verified as ``knowledge``:
#:   fact:, session:facts:, content_hash:, unique_key:  ``knowledge/facts.py`` (``redis_client``, ``base.py:336``)
#:   user:kb:, group:kb:, org:kb:, user:facts:          ``knowledge/ownership.py`` (fact-id membership sets)
#:   kb:                  every ``kb:`` key in the knowledge database EXCEPT ``KB_KEPT_PREFIXES``; classified below
#:   tag:, category:facts:, collection:facts:           membership sets of fact ids (``tags.py``, ``categories.py``,
#:                                                      ``collections.py``)
#:   connector:*:ts:, connector:*:checkpoint, connector:*:external_state, connector:notion:hash:
#:       connector sync state (``connectors/base.py:271,283``, ``notion.py:45,218``): left behind, the connectors
#:       would see "unchanged" and never re-ingest into the emptied KB
#:   bm25:corpus_stats    ``search_components/keyword_search.py:26`` via the KB's ``_aioredis_client`` (``base.py:352``)
#:   context:summary:     ``pipeline/cognifiers/context_generator.py:42,76`` (summaries keyed by dropped doc ids)
#:   entity:, timeline:global   the pipeline's graph of KB documents (``pipeline/loaders/redis_graph_loader.py``)
#: The ``kb:`` writers, each classified (grep of backend and shared code; database in brackets):
#:   WIPED  kb:stats [knowledge, ``knowledge/base.py``], kb:ingest: [knowledge, ``document_ingest.py``],
#:          kb:rel:out:/kb:rel:in: [knowledge, ``relations.py``], kb:acl_epoch [knowledge, ``acl_epoch.py``],
#:          kb:membership_epoch: [knowledge, ``autobot_shared/membership_epoch.py``; derived invalidation counter],
#:          kb:system:facts, kb:category:chat_knowledge [knowledge, ``ownership*.py``], kb:vectorize:pending
#:          [knowledge, ``background_vectorization.py``], kb:lint:report [knowledge, ``contradiction_detector.py``],
#:          kb:cache:, kb:stats:category: [knowledge, ``api/knowledge.py``, ``knowledge_category_counts.py``]
#:   KEPT   kb:boards [knowledge, ``api/knowledge_boards.py``]: user-made board definitions, taxonomy like
#:          ``collection:{id}``, not ingested knowledge (``KB_KEPT_PREFIXES``)
#:   OUT OF SCOPE (main database, never scanned): kb:synthesis:*, kb:watch_folders, kb:watch_folder:
#:   NOT A KEY: kb:embedding-switch (a coordination scope name, ``embedding_switch_lock.py``)
#: KEPT on purpose (settings, credentials, locks, definitions, user activity): ``kb:boards``, ``category:{id}``,
#: ``category:path:``, ``category:children:``, ``category:root`` and ``collection:{id}``, ``collection:all``
#: (user-made taxonomy), ``tag_style:`` (display preference), ``metadata:template:`` (templates),
#: ``connector:{id}`` / ``:auth`` / ``oauth:`` / ``schedule:`` / ``scheduler:leader`` / ``sync:`` (config, credentials,
#: locks), ``rag:feedback:`` (user activity) and the embedding-model override.
#: Not atomic: keys written by a concurrent writer during the wipe survive, so the KB should be idle.
KB_KEY_PREFIXES: tuple[str, ...] = (
    "fact:",
    "session:facts:",
    "content_hash:",
    "unique_key:",
    "user:kb:",
    "group:kb:",
    "org:kb:",
    "user:facts:",
    "kb:",
    "tag:",
    "category:facts:",
    "collection:facts:",
    "connector:*:ts:",
    "connector:*:checkpoint",
    "connector:*:external_state",
    "connector:notion:hash:",
    "bm25:corpus_stats",
    "context:summary:",
    "entity:",
    "timeline:global",
)
#: Key families under a ``KB_KEY_PREFIXES`` entry that the wipe never touches: the scan skips them and
#: ``frozen_redis_scope`` refuses a plan that names one, so no plan can re-include them.
KB_KEPT_PREFIXES: tuple[str, ...] = ("kb:boards",)
#: Stated in the plan output: the wipe does not quiesce the KB.
NOT_ATOMIC_NOTE = "Not atomic: keys written by a concurrent writer during the wipe survive. Run it with the KB idle."
#: Keys scanned and unlinked per call.
SCAN_BATCH = env_int_clamped("AUTOBOT_KB_WIPE_SCAN_BATCH", 500, 1, 10000)

ClientFactory = Callable[[str], Any]


def default_client(database: str):
    from autobot_shared.redis_client import get_redis_client

    return get_redis_client(database=database)


def _index_documents(client, name: str) -> int:
    """Indexed document count from ``FT.INFO``; 0 when the reply has no ``num_docs``."""
    info = decode_redis_list(client.execute_command("FT.INFO", name))
    return int(info[info.index("num_docs") + 1]) if "num_docs" in info else 0


def is_kept_key(key: object) -> bool:
    """Whether *key* belongs to a family the wipe never touches (``KB_KEPT_PREFIXES``)."""
    return decode_redis_value(key).startswith(KB_KEPT_PREFIXES)


def _wiped_keys(client, prefix: str):
    """The keys under *prefix* that the wipe may remove: the scan with the kept families skipped."""
    return (key for key in client.scan_iter(match=f"{prefix}*", count=SCAN_BATCH) if not is_kept_key(key))


def _count_prefix(client, prefix: str) -> int:
    return sum(1 for _ in _wiped_keys(client, prefix))


def _kb_indexes_present(client) -> list[str]:
    """The KB's own indexes that exist on the server, in ``kb_index_names`` order; a foreign index is never named."""
    listed = {decode_redis_value(name) for name in client.execute_command("FT._LIST") or []}
    return [name for name in kb_index_names() if name in listed]


def _database_plan(client, database: str) -> dict:
    prefixes = [{"prefix": p, "keys": _count_prefix(client, p)} for p in KB_KEY_PREFIXES]
    return {
        "note": NOT_ATOMIC_NOTE,
        "database": database,
        "indexes": [{"name": n, "documents": _index_documents(client, n)} for n in _kb_indexes_present(client)],
        "prefixes": prefixes,
        "keys": sum(p["keys"] for p in prefixes),
    }


def _client_or_raise(client_factory: ClientFactory, database: str):
    client = client_factory(database)
    if client is None:
        raise RuntimeError(f"Redis database {database!r} is unavailable; nothing was deleted from it")
    return client


def plan_redis(client_factory: ClientFactory = default_client) -> list[dict]:
    """Read only: per KB database, the KB's own search index and the keys under each KB prefix."""
    return [_database_plan(_client_or_raise(client_factory, db), db) for db in KB_WIPE_DATABASES]


def _refuse_outside_scope(kind: str, names: list[str], allowed: tuple[str, ...]) -> None:
    outside = [n for n in names if n not in allowed]
    if outside:
        raise ValueError(f"the approved plan names {kind} outside the knowledge scope ({outside}); nothing was deleted")


def _refuse_kept(prefixes: list[str]) -> None:
    kept = [p for p in prefixes if p.startswith(KB_KEPT_PREFIXES)]
    if kept:
        raise ValueError(f"the approved plan names a key family the wipe always keeps ({kept}); nothing was deleted")


def frozen_redis_scope(plan_databases: list[dict]) -> list[dict]:
    """What the approved plan says to delete in Redis, checked against the code's scope; raises when it exceeds it.

    Returns ``[{"database", "indexes": [name], "prefixes": [prefix]}]`` and nothing else: the executor deletes
    exactly this. A database, index or prefix the knowledge scope does not list refuses the whole wipe before
    any delete, so a tampered or stale plan cannot widen it.
    """
    scope = []
    for entry in plan_databases:
        database = entry["database"]
        indexes = [item["name"] for item in entry["indexes"]]
        prefixes = [item["prefix"] for item in entry["prefixes"]]
        _refuse_outside_scope("a database", [database], KB_WIPE_DATABASES)
        _refuse_outside_scope("an index", indexes, kb_index_names())
        _refuse_kept(prefixes)
        _refuse_outside_scope("a key prefix", prefixes, KB_KEY_PREFIXES)
        scope.append({"database": database, "indexes": indexes, "prefixes": prefixes})
    return scope


class WipeStopped(RuntimeError):
    """The caller stopped the wipe between two batches (the awaiting task was cancelled)."""


def _check_stop(stop: threading.Event | None) -> None:
    if stop is not None and stop.is_set():
        raise WipeStopped("the knowledge wipe was stopped between batches")


def _unlink_prefix(client, prefix: str, entry: dict, stop: threading.Event | None = None) -> None:
    """Unlink the keys under *prefix*, updating ``entry["count"]`` per batch so a failure keeps the count so far.

    *stop* is checked before every batch: at most the batch in flight completes after it is set.
    """
    batch: list = []
    for key in _wiped_keys(client, prefix):
        batch.append(key)
        if len(batch) >= SCAN_BATCH:
            _check_stop(stop)
            entry["count"] += int(client.unlink(*batch))
            batch = []
    if batch:
        _check_stop(stop)
        entry["count"] += int(client.unlink(*batch))


def _drop_indexes(
    client, database: str, names: list[str], record: list[dict], stop: threading.Event | None = None
) -> None:
    """Drop each approved index (with its documents) that still exists; an index already gone is recorded, not retried.

    ``FT._LIST`` is read only to skip a vanished name. It can narrow what is dropped, never widen it. A step is
    appended with ``complete=False`` BEFORE ``FT.DROPINDEX`` runs and flips when it returns, so a connection lost
    after the server executed the drop still leaves the step in the failure audit.
    """
    present = {decode_redis_value(name) for name in client.execute_command("FT._LIST") or []}
    for name in names:
        _check_stop(stop)
        step = {"database": database, "kind": "index", "name": name, "count": 0, "complete": False}
        record.append(step)
        if name in present:
            step["count"] = _index_documents(client, name)
            client.execute_command("FT.DROPINDEX", name, "DD")
        else:
            step["absent"] = True
        step["complete"] = True


def execute_redis(
    record: list[dict],
    scope: list[dict],
    client_factory: ClientFactory = default_client,
    stop: threading.Event | None = None,
) -> None:
    """Delete exactly *scope* (from ``frozen_redis_scope``): its indexes first, then its prefixes; append per step.

    A prefix's entry is appended BEFORE its keys are scanned and ``complete`` flips when it finishes. Setting
    *stop* from another thread ends the wipe at the next batch with ``WipeStopped``.
    """
    for entry in scope:
        database = entry["database"]
        client = _client_or_raise(client_factory, database)
        _drop_indexes(client, database, entry["indexes"], record, stop)
        for prefix in entry["prefixes"]:
            step = {"database": database, "kind": "prefix", "name": prefix, "count": 0, "complete": False}
            record.append(step)
            _unlink_prefix(client, prefix, step, stop)
            step["complete"] = True
