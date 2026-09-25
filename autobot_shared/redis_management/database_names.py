# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for turning a database reference into a registry name (#17435).

`RedisDatabase` is a plain `Enum` whose VALUES are database numbers
(`MAIN = 0`, `ANALYTICS = 11`), while the runtime lookup is keyed by NAMES
(`DATABASE_MAPPING: Dict[str, int]`). So the enum's `.value` is not a key, and
`str(enum)` is `"RedisDatabase.ANALYTICS"`, which is not one either -- the two
plausible conversions are both wrong and only one of them is obviously so.

Before this module the rule lived in three hand-copied lines -- twice in
`redis_client.py`, once in `api/analytics_controller.py` -- and was absent from
the two module-level functions most call sites use. A caller passing the enum
reached `DATABASE_MAPPING.get(name, 0)` and got **DB 0**, after a warning and
before two lines of success logging:

    WARNING Unknown database name 'RedisDatabase.ANALYTICS', defaulting to DB 0.
    INFO    Redis database 'RedisDatabase.ANALYTICS' is ready
    INFO    Created async pool for 'RedisDatabase.ANALYTICS' with retry protection

So analytics writes landed in `main`, while the reader asking for `"analytics"`
looked in DB 11 and reported `Loaded 0 patterns from Redis`. One feature
addressing one logical database two ways, one of them wrong.

`database_number` REFUSES an unknown name rather than defaulting. The default is
why this reached production wearing a green log line, and it is also why seven
further call sites passing `RedisDatabase.MAIN` looked healthy: `MAIN` is 0,
which is exactly what the fallback returned. Those were not working -- they were
agreeing with the failure mode, and the agreement would have ended the moment
any of them was repointed.
"""

from __future__ import annotations

from autobot_shared.redis_management.types import DATABASE_MAPPING, RedisDatabase

__all__ = ["database_name", "database_number"]


def database_name(database: RedisDatabase | str) -> str:
    """The registry name for *database*, whichever of the two forms it arrives in."""
    if isinstance(database, RedisDatabase):
        return database.name.lower()
    return database


def database_number(database: RedisDatabase | str) -> int:
    """Resolve *database* to its DB number, refusing a name nothing declares.

    Raises rather than defaulting. An unrecognised database is a programming
    error, and a working default for one is indistinguishable from success --
    which is the whole of #17435. Callers that genuinely want a fallback should
    choose it explicitly at the call site, where it is visible.
    """
    name = database_name(database)
    if name not in DATABASE_MAPPING:
        raise KeyError(
            f"unknown Redis database {name!r}; declared databases are {sorted(DATABASE_MAPPING)}. "
            "A RedisDatabase member must go through database_name(): its .value is a DB "
            "number, not a key, and str() of it is not one either."
        )
    return DATABASE_MAPPING[name]
