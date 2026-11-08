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
#: Key prefixes the KB writes in its database (``knowledge/facts.py``, ``tags.py``, ``categories.py``,
#: ``collections.py``, ``document_ingest.py``, ``acl_epoch.py``). A key outside these is not KB data.
KB_KEY_PREFIXES: tuple[str, ...] = ("fact:", "kb:", "tag:", "tag_style:", "category:", "collection:")
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


def _unlink_prefix(client, prefix: str) -> int:
    removed, batch = 0, []
    for key in client.scan_iter(match=f"{prefix}*", count=SCAN_BATCH):
        batch.append(key)
        if len(batch) >= SCAN_BATCH:
            removed += int(client.unlink(*batch))
            batch = []
    if batch:
        removed += int(client.unlink(*batch))
    return removed


def execute_redis(record: list[dict], client_factory: ClientFactory = default_client) -> None:
    """Drop the KB indexes (with their documents), then unlink the KB prefixes; append to *record* per step."""
    for database in KB_WIPE_DATABASES:
        client = _client_or_raise(client_factory, database)
        for index in _database_plan(client, database)["indexes"]:
            client.execute_command("FT.DROPINDEX", index["name"], "DD")
            record.append({"database": database, "kind": "index", "name": index["name"], "count": index["documents"]})
        for prefix in KB_KEY_PREFIXES:
            record.append(
                {"database": database, "kind": "prefix", "name": prefix, "count": _unlink_prefix(client, prefix)}
            )
