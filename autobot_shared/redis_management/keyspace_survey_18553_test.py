# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`survey_databases` visits every server database through the canonical connection path (#18553).

No Redis server is needed: clients connect lazily, and ``CONFIG GET`` is answered by a fake.
"""

import pytest
import redis

from autobot_shared import redis_client
from autobot_shared.redis_management import keyspace_survey
from autobot_shared.redis_management.config import PoolConfig, RedisDbConfig
from autobot_shared.redis_management.connection_manager import RedisConnectionManager
from autobot_shared.redis_management.types import DATABASE_MAPPING

#: A fixture value, not a credential.
_PW = "pw"  # pragma: allowlist secret
#: Declared by no YAML entry, enum member or alias; the survey must still visit it.
_UNNAMED = 12


def _manager() -> RedisConnectionManager:
    """A manager with SSOT-shaped state and no network: only config resolution and pool building run."""
    manager = object.__new__(RedisConnectionManager)
    manager._tcp_keepalive_options = {}
    manager._config_broken = set()
    manager._config = {"host": "10.0.0.5", "port": 6390, "password": _PW, "username": "default"}
    manager._pool_config = PoolConfig()
    main = RedisDbConfig(name="main", db=0, host="10.0.0.5", port=6390, password=_PW, username="default")
    manager._configs = {"main": main}
    return manager


def _serve_databases(monkeypatch, answer) -> None:
    def _config_get(self, pattern="*", *args):
        if isinstance(answer, Exception):
            raise answer
        return {"databases": answer}

    monkeypatch.setattr(redis.Redis, "config_get", _config_get)


def _survey(manager, decode_responses=False):
    return list(keyspace_survey.survey_databases(decode_responses, manager))


def test_every_server_database_is_visited_including_the_unnamed_one(monkeypatch):
    _serve_databases(monkeypatch, "16")
    visited = _survey(_manager())
    assert [number for number, _, _ in visited] == list(range(16))
    assert _UNNAMED not in DATABASE_MAPPING.values()  # the case under test really is unnamed
    assert visited[_UNNAMED][1] is None


def test_the_count_comes_from_the_server(monkeypatch):
    _serve_databases(monkeypatch, "20")
    assert [number for number, _, _ in _survey(_manager())] == list(range(20))


def test_names_match_the_registry_mapping(monkeypatch):
    _serve_databases(monkeypatch, "16")
    for number, name, _ in _survey(_manager()):
        if name is not None:
            assert DATABASE_MAPPING[name] == number
    assert keyspace_survey.database_names_by_number()[0] == "main"  # a YAML name beats the `memory` alias


@pytest.mark.parametrize("decode", [False, True])
def test_connection_params_are_the_canonical_clients(monkeypatch, decode):
    _serve_databases(monkeypatch, "16")
    manager = _manager()
    # The pool get_sync_client("main", decode_responses=...) is built from.
    canonical = manager._create_sync_pool("main", decode).connection_kwargs
    assert canonical["host"] == "10.0.0.5" and canonical["password"] == _PW  # the fixture's config, not defaults
    for number, _, client in _survey(manager, decode_responses=decode):
        surveyed = dict(client.connection_pool.connection_kwargs)
        assert surveyed.pop("db") == number
        assert _config_view(surveyed) == _config_view({key: value for key, value in canonical.items() if key != "db"})


_CONFIG_SCALARS = (str, bytes, int, float, bool, type(None), tuple, list, dict)


def _config_view(kwargs):
    """Connection kwargs with per-pool runtime objects reduced to their type.

    redis builds some kwargs fresh for every pool (``himport_registry``, the
    maint-notifications handler) and they define no equality, so two pools
    built from identical configuration never compare equal on them. Settings
    (host, port, auth, TLS, timeouts) compare by value; ``Retry`` defines
    equality and compares by value too.
    """
    return {
        key: value if isinstance(value, _CONFIG_SCALARS) or type(value).__eq__ is not object.__eq__ else type(value)
        for key, value in kwargs.items()
    }


@pytest.mark.parametrize("refusal", [redis.ResponseError("NOPERM"), redis.ConnectionError("refused")])
def test_a_refused_config_get_falls_back_to_the_redis_default(monkeypatch, refusal):
    _serve_databases(monkeypatch, refusal)
    count = keyspace_survey.server_database_count(_manager())
    assert count == keyspace_survey.REDIS_DEFAULT_DATABASE_COUNT == 16


def test_each_client_is_closed_once_the_caller_moves_on(monkeypatch):
    _serve_databases(monkeypatch, "3")
    closed = []
    monkeypatch.setattr(keyspace_survey, "_close", closed.append)
    survey = keyspace_survey.survey_databases(False, _manager())
    _, _, first = next(survey)
    assert first not in closed
    next(survey)
    assert first in closed
    survey.close()
    assert len(closed) == 3  # the CONFIG GET probe, then both surveyed clients


def test_reexported_from_redis_client():
    assert redis_client.survey_databases is keyspace_survey.survey_databases
    assert "survey_databases" in redis_client.__all__
