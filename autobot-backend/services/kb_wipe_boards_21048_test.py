# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""User-made boards survive the knowledge wipe, and no plan can re-include them (#21048).

Fakes only: no real Redis is touched.
"""

import fnmatch

import pytest

from services import kb_wipe_redis as redis_mod

BOARDS = "kb:boards"


class FakeRedis:
    def __init__(self, data):
        self.data = dict(data)

    def execute_command(self, *args):
        return []

    def scan_iter(self, match, count=None):
        return iter([k for k in list(self.data) if fnmatch.fnmatchcase(k, match)])

    def unlink(self, *keys):
        for key in keys:
            self.data.pop(key, None)
        return len(keys)


@pytest.fixture(autouse=True)
def kb_index(monkeypatch):
    monkeypatch.setattr(redis_mod, "kb_index_names", lambda: ("llama_index",))


def _client():
    return FakeRedis({BOARDS: "x", "kb:stats": "x", "kb:ingest:d": "x", "fact:1": "x"})


def test_boards_survive_a_wipe_while_the_rest_of_the_kb_family_goes():
    client = _client()
    scope = redis_mod.frozen_redis_scope(redis_mod.plan_redis(lambda database: client))
    redis_mod.execute_redis([], scope, lambda database: client)
    assert set(client.data) == {BOARDS}


def test_the_plan_does_not_count_boards():
    plan = redis_mod.plan_redis(lambda database: _client())[0]
    assert {p["prefix"]: p["keys"] for p in plan["prefixes"]}["kb:"] == 2


@pytest.mark.parametrize("named", [BOARDS, "kb:boards:extra"])
def test_a_plan_naming_the_boards_family_is_refused_before_any_delete(named):
    client = _client()
    plan = [{"database": "knowledge", "indexes": [], "prefixes": [{"prefix": named, "keys": 1}]}]
    plan[0]["prefixes"].insert(0, {"prefix": "fact:", "keys": 1})
    with pytest.raises(ValueError, match="always keeps"):
        redis_mod.frozen_redis_scope(plan)
    assert BOARDS in client.data and "fact:1" in client.data
