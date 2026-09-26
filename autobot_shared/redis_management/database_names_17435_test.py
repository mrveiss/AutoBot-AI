# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A database reference resolves to the database it names, or not at all (#17435).

Every test here uses a **non-zero** database on purpose. `MAIN` is 0 and the old
fallback returned 0, so any test written with `MAIN` passes against the defect and
proves nothing -- which is exactly how seven call sites passing
`RedisDatabase.MAIN` stayed invisible while one passing `ANALYTICS` misrouted.

Mutation to check these are not vacuous: restore
`return DATABASE_MAPPING.get(database_name, 0)` in `_get_database_number`. The
resolution test then reports 0 for `ANALYTICS`, and the refusal test stops
raising.
"""

from __future__ import annotations

import pytest

from autobot_shared.redis_management.database_names import database_name, database_number
from autobot_shared.redis_management.types import DATABASE_MAPPING, RedisDatabase

#: Not MAIN. See the module docstring -- MAIN == 0 == the old fallback, so it
#: cannot distinguish a resolved answer from a defaulted one.
_NON_ZERO = RedisDatabase.ANALYTICS


def test_the_enum_resolves_to_the_database_it_names() -> None:
    """The defect: this returned 0, so analytics writes landed in `main`."""
    assert database_number(_NON_ZERO) == DATABASE_MAPPING["analytics"]
    assert database_number(_NON_ZERO) != 0, "a non-zero database resolving to 0 is the bug"


def test_the_name_string_and_the_enum_agree() -> None:
    """One logical database, two accepted forms, one answer.

    The live symptom was a writer using the enum and a reader using the string,
    reaching different databases inside one feature.
    """
    assert database_number(_NON_ZERO) == database_number("analytics")


def test_the_enum_value_is_a_number_not_a_key() -> None:
    """Why `.value` is the wrong conversion, pinned so the fix is not re-broken.

    `RedisDatabase.ANALYTICS.value` is 11 -- a database NUMBER. Passing it where a
    name is expected is a second wrong answer wearing the shape of a fix.
    """
    assert _NON_ZERO.value == 11
    assert str(_NON_ZERO.value) not in DATABASE_MAPPING
    assert database_name(_NON_ZERO) == "analytics"


def test_stringifying_the_enum_is_not_a_key_either() -> None:
    """The actual defect's mechanism: `str(enum)` is not a registry name."""
    assert str(_NON_ZERO) not in DATABASE_MAPPING
    with pytest.raises(KeyError, match="unknown Redis database"):
        database_number(str(_NON_ZERO))


def test_an_undeclared_database_is_refused_rather_than_defaulted() -> None:
    """Exit 0 with a working default is indistinguishable from success."""
    with pytest.raises(KeyError, match="unknown Redis database"):
        database_number("no_such_database")


@pytest.mark.parametrize("member", list(RedisDatabase))
def test_every_enum_member_resolves_to_its_own_value(member: RedisDatabase) -> None:
    """The enum and the name registry must not disagree for ANY member.

    Parametrised over the whole enum rather than a sample: a per-member drift
    between `redis-databases.yaml` and the enum is exactly the kind of thing a
    spot-check misses.
    """
    assert database_number(member) == member.value, (
        f"{member.name} resolves to {database_number(member)} but its enum value is "
        f"{member.value} -- the name registry and the enum disagree"
    )


def test_no_pool_key_can_be_an_undeclared_name() -> None:
    """Pools are keyed by the NAME string, so a bogus name got its own pool.

    The log showed it: `Created async pool for 'RedisDatabase.ANALYTICS'`. DB 0
    could therefore carry three pools -- `main`, `RedisDatabase.MAIN` and
    `RedisDatabase.ANALYTICS` -- each with its own `max_connections`, all
    pointing at the same database.

    This asserts the invariant rather than the symptom: every key a pool can be
    created under must be a declared database. Normalising at the manager's entry
    is what makes it hold, because the entry is where the key is taken from.
    """
    from autobot_shared.redis_management.database_names import database_name as _name

    for member in RedisDatabase:
        assert _name(member) in DATABASE_MAPPING, (
            f"{member.name} normalises to {_name(member)!r}, which is not a declared "
            "database -- a pool created under that key would be a phantom"
        )
    assert str(RedisDatabase.ANALYTICS) not in DATABASE_MAPPING


def test_the_analytics_writer_and_reader_resolve_to_one_database() -> None:
    """The live symptom, pinned at the two real call sites rather than in the abstract.

    Before the fix:

        writer  api/analytics_embedding_patterns.py  _redis_database = RedisDatabase.ANALYTICS  -> DB 0
        reader  api/analytics_pattern_learning.py    database="analytics"                       -> DB 11

    One feature, one logical database, two addressing forms, and only one of them
    right -- so the reader reported `Loaded 0 patterns from Redis` while the writer
    filled `main`.

    This reads the writer's declared database off the class rather than restating
    it, so the test follows the call site if it is ever changed.
    """
    import importlib

    writer = importlib.import_module("api.analytics_embedding_patterns")
    declared = writer.EmbeddingPatternAnalyzer._redis_database

    assert database_number(declared) == database_number("analytics"), (
        f"the writer declares {declared!r} and the reader asks for 'analytics'; they must "
        "resolve to the same database or the feature writes where nothing reads"
    )
    assert database_number(declared) != 0, "analytics resolving to DB 0 is the original defect"
