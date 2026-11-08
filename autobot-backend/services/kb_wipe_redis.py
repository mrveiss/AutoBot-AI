# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Redis half of the approved knowledge wipe (#21048, #17038).

Nothing here flushes a database. The ``knowledge`` database also holds settings that are not KB data, such
as the embedding-model override (``autobot_shared.embedding_model.EMBEDDING_OVERRIDE_KEY``), so the wipe
drops the KB's search indexes and unlinks only the keys under ``KB_KEY_PREFIXES``. Every other key survives.
"""

from __future__ import annotations

from typing import Any, Callable

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.redis_utils import decode_redis_list, decode_redis_value

#: Redis databases the wipe may touch. Knowledge only; sessions, settings and queues are never listed.
KB_WIPE_DATABASES: tuple[str, ...] = ("knowledge",)
#: Key families in the ``knowledge`` database that are DERIVED from KB content, so they go with it. Entries are
#: SCAN patterns (a ``*`` inside is a glob). Each family's database was verified as ``knowledge``:
#:   fact:, session:facts:, content_hash:, unique_key:  ``knowledge/facts.py`` (``redis_client``, ``base.py:336``)
#:   user:kb:, group:kb:, org:kb:, user:facts:          ``knowledge/ownership.py`` (fact-id membership sets)
#:   kb:                  stats, ingest records, ACL epoch, relations, system/category indexes (``knowledge/*.py``)
#:   tag:, category:facts:, collection:facts:           membership sets of fact ids (``tags.py``, ``categories.py``,
#:                                                      ``collections.py``)
#:   connector:*:ts:, connector:*:checkpoint, connector:*:external_state, connector:notion:hash:
#:       connector sync state (``connectors/base.py:271,283``, ``notion.py:45,218``): left behind, the connectors
#:       would see "unchanged" and never re-ingest into the emptied KB
#:   bm25:corpus_stats    ``search_components/keyword_search.py:26`` via the KB's ``_aioredis_client`` (``base.py:352``)
#:   context:summary:     ``pipeline/cognifiers/context_generator.py:42,76`` (summaries keyed by dropped doc ids)
#:   entity:, timeline:global   the pipeline's graph of KB documents (``pipeline/loaders/redis_graph_loader.py``)
#: KEPT on purpose (settings, credentials, locks, definitions, user activity): ``category:{id}``,
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


def _count_prefix(client, prefix: str) -> int:
    return sum(1 for _ in client.scan_iter(match=f"{prefix}*", count=SCAN_BATCH))


def _database_plan(client, database: str) -> dict:
    names = [decode_redis_value(name) for name in client.execute_command("FT._LIST") or []]
    prefixes = [{"prefix": p, "keys": _count_prefix(client, p)} for p in KB_KEY_PREFIXES]
    return {
        "note": NOT_ATOMIC_NOTE,
        "database": database,
        "indexes": [{"name": n, "documents": _index_documents(client, n)} for n in names],
        "prefixes": prefixes,
        "keys": sum(p["keys"] for p in prefixes),
    }


def _client_or_raise(client_factory: ClientFactory, database: str):
    client = client_factory(database)
    if client is None:
        raise RuntimeError(f"Redis database {database!r} is unavailable; nothing was deleted from it")
    return client


def plan_redis(client_factory: ClientFactory = default_client) -> list[dict]:
    """Read only: per KB database, its search indexes and the keys under each KB prefix."""
    return [_database_plan(_client_or_raise(client_factory, db), db) for db in KB_WIPE_DATABASES]


def _unlink_prefix(client, prefix: str, entry: dict) -> None:
    """Unlink the keys under *prefix*, updating ``entry["count"]`` per batch so a failure keeps the count so far."""
    batch: list = []
    for key in client.scan_iter(match=f"{prefix}*", count=SCAN_BATCH):
        batch.append(key)
        if len(batch) >= SCAN_BATCH:
            entry["count"] += int(client.unlink(*batch))
            batch = []
    if batch:
        entry["count"] += int(client.unlink(*batch))


def execute_redis(record: list[dict], client_factory: ClientFactory = default_client) -> None:
    """Drop the KB indexes (with their documents), then unlink the KB prefixes; append to *record* per step.

    A prefix's entry is appended BEFORE its keys are scanned and ``complete`` flips when it finishes. Index
    names come from ``FT._LIST``; the prefix scan is not repeated here.
    """
    for database in KB_WIPE_DATABASES:
        client = _client_or_raise(client_factory, database)
        for name in (decode_redis_value(n) for n in client.execute_command("FT._LIST") or []):
            documents = _index_documents(client, name)
            client.execute_command("FT.DROPINDEX", name, "DD")
            record.append({"database": database, "kind": "index", "name": name, "count": documents})
        for prefix in KB_KEY_PREFIXES:
            entry = {"database": database, "kind": "prefix", "name": prefix, "count": 0, "complete": False}
            record.append(entry)
            _unlink_prefix(client, prefix, entry)
            entry["complete"] = True
