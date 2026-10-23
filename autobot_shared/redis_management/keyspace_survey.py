# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`survey_databases`: every logical database on the Redis server, named or not (#18553).

A whole-keyspace survey (admin and diagnostic scripts) has to reach database numbers that no
``RedisDatabase`` member names -- DB 12 today -- so it cannot go through ``get_redis_client``, which
addresses databases by name and refuses an undeclared one. It still must not build its own client:
each survey client comes from the connection manager's own ``resolve_db_config("main")`` (SSOT host,
port, auth, TLS, timeouts) with only the database number changed, through the same
``build_sync_pool`` every named sync client uses.

Survey clients are short-lived and private to the survey. Each one's pool is disconnected as soon as
the caller advances past it, or when the generator is closed; wrap the call in
``contextlib.closing`` when the loop may ``break`` and cleanup must be deterministic.
"""

from __future__ import annotations

import dataclasses
from typing import Iterator

import redis

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_management.types import DATABASE_MAPPING

logger = get_logger(__name__)

#: Redis's own default for the ``databases`` server setting; used when ``CONFIG GET databases`` is
#: refused (ACL, renamed CONFIG command) or the server cannot be reached.
REDIS_DEFAULT_DATABASE_COUNT = 16

#: The connection to read ``CONFIG GET databases`` over.
_PROBE_DB = 0


def database_names_by_number() -> dict[int, str]:
    """Number -> registry name; the first declared name wins, so YAML names beat later aliases.

    A number nothing declares is absent: callers get ``None`` for it, never an invented name.
    """
    names: dict[int, str] = {}
    for name, number in DATABASE_MAPPING.items():
        names.setdefault(number, name)
    return names


def _survey_client(manager, number: int, decode_responses: bool) -> redis.Redis:
    """A client for DB *number* with the canonical ``main`` connection parameters."""
    config = dataclasses.replace(manager.resolve_db_config("main"), name=f"survey:db{number}", db=number)
    return redis.Redis(connection_pool=manager.build_sync_pool(config.name, config, decode_responses))


def _close(client: redis.Redis) -> None:
    """Release *client* and disconnect its private pool."""
    client.close()
    client.connection_pool.disconnect()


def server_database_count(manager) -> int:
    """The server's ``databases`` setting, or ``REDIS_DEFAULT_DATABASE_COUNT`` when it cannot be read."""
    client = _survey_client(manager, _PROBE_DB, decode_responses=True)
    try:
        value = client.config_get("databases").get("databases")
        return int(value)
    except (redis.RedisError, TypeError, ValueError) as error:
        logger.warning(
            "CONFIG GET databases unavailable (%s); assuming Redis's default of %d",
            error,
            REDIS_DEFAULT_DATABASE_COUNT,
        )
        return REDIS_DEFAULT_DATABASE_COUNT
    finally:
        _close(client)


def survey_databases(decode_responses: bool = False, manager=None) -> Iterator[tuple[int, str | None, redis.Redis]]:
    """Yield ``(db_number, registry_name_or_None, client)`` for every database the server has.

    *manager* defaults to the process's ``RedisConnectionManager`` singleton. Clients connect lazily,
    so an unreachable server surfaces as a ``redis.ConnectionError`` at the caller's first command.
    """
    if manager is None:
        from autobot_shared.redis_management.connection_manager import RedisConnectionManager

        manager = RedisConnectionManager()
    names = database_names_by_number()
    for number in range(server_database_count(manager)):
        client = _survey_client(manager, number, decode_responses)
        try:
            yield number, names.get(number), client
        finally:
            _close(client)
