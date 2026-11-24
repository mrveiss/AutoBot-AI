# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one-off migration that gives the desktop server the vnc role (#22211).

Driven against a fake cursor that applies the three tables' semantics, so the assertions are about the
rows the migration leaves behind, not about the SQL text.
"""

from __future__ import annotations

import inspect
import re

import pytest

from migrations import assign_vnc_role_to_desktop_node as mig


class _World:
    def __init__(self, nodes, rdp_creds=(), services=(), roles=()):
        self.nodes = {n: [] for n in nodes}
        self.rdp = set(rdp_creds)
        self.services = set(services)
        self.roles = {tuple(r) for r in roles}  # (node_id, role, assignment_type)
        self.commits = 0


class _Cursor:
    def __init__(self, w: _World):
        self.w = w
        self._rows: list = []

    def execute(self, sql, params=()):
        q = " ".join(sql.split()).lower()
        if q.startswith("select distinct node_id from node_credentials"):
            self._rows = [(n,) for n in sorted(self.w.rdp)]
        elif q.startswith("select distinct node_id from services"):
            self._rows = [(n,) for n in sorted(self.w.services)]
        elif q.startswith("select node_id from nodes"):
            self._rows = [(n,) for n in params[0] if n in self.w.nodes]
        elif q.startswith("select 1 from node_roles"):
            self._rows = [(1,)] if any(r[:2] == tuple(params) for r in self.w.roles) else []
        elif q.startswith("insert into node_roles"):
            self.w.roles.add((params[0], params[1], params[2]))
        elif q.startswith("update nodes set roles = (coalesce(roles::jsonb, '[]'::jsonb) ||"):
            if params[0] not in self.w.nodes[params[1]]:
                self.w.nodes[params[1]].append(params[0])
        elif q.startswith("update nodes set roles = (coalesce(roles::jsonb, '[]'::jsonb) -"):
            self.w.nodes[params[1]] = [r for r in self.w.nodes[params[1]] if r != params[0]]
        elif q.startswith("delete from node_roles"):
            gone = [r for r in self.w.roles if r[1] == params[0] and r[2] == params[1]]
            self.w.roles -= set(gone)
            self._rows = [(r[0],) for r in gone]
        else:
            raise AssertionError(f"unexpected SQL: {q}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, w):
        self.w = w

    def cursor(self):
        return _Cursor(self.w)

    def commit(self):
        self.w.commits += 1

    def close(self):
        pass


@pytest.fixture
def run(monkeypatch):
    def _run(world, fn=mig.migrate):
        monkeypatch.setattr(mig, "get_connection", lambda url: _Conn(world))
        monkeypatch.setattr(mig, "table_exists", lambda cur, name: True)
        fn("postgresql://unused")
        return world

    return _run


def test_assigns_vnc_once_to_the_node_carrying_the_xrdp_purpose(run) -> None:
    w = run(_World(["a", "b", "c"], rdp_creds=["b"], services=["b"]))
    assert w.roles == {("b", "vnc", "migration")}
    assert w.nodes["b"] == ["vnc"] and w.nodes["a"] == w.nodes["c"] == []


def test_either_signal_alone_identifies_the_node(run) -> None:
    assert run(_World(["a", "b"], services=["a"])).roles == {("a", "vnc", "migration")}
    assert run(_World(["a", "b"], rdp_creds=["b"])).roles == {("b", "vnc", "migration")}


def test_is_idempotent(run) -> None:
    w = run(_World(["a"], rdp_creds=["a"]))
    run(w)
    assert w.roles == {("a", "vnc", "migration")} and w.nodes["a"] == ["vnc"] and w.commits == 1


def test_an_existing_vnc_row_is_left_untouched(run) -> None:
    w = run(_World(["a"], rdp_creds=["a"], roles=[("a", "vnc", "manual")]))
    assert w.roles == {("a", "vnc", "manual")} and w.commits == 0


@pytest.mark.parametrize("world", [_World(["a", "b"]), _World(["a", "b"], rdp_creds=["a", "b"])], ids=["none", "two"])
def test_no_node_or_an_ambiguous_pair_assigns_nothing(run, world) -> None:
    assert run(world).roles == set()


def test_a_credential_for_a_removed_node_is_not_a_candidate(run) -> None:
    assert run(_World(["a"], rdp_creds=["ghost"])).roles == set()


def test_downgrade_removes_only_its_own_rows(run) -> None:
    w = run(_World(["a", "b"], rdp_creds=["a"], roles=[("b", "vnc", "manual")]))
    w.nodes["b"] = ["vnc"]
    run(w, mig.downgrade)
    assert w.roles == {("b", "vnc", "manual")} and w.nodes["a"] == [] and w.nodes["b"] == ["vnc"]


def test_no_node_is_hardcoded() -> None:
    src = inspect.getsource(mig)
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", src)
    assert "autobot-llm" not in src and "05-LLM" not in src


def test_is_registered_with_the_runner() -> None:
    from migrations.runner import MIGRATIONS

    assert MIGRATIONS.count("assign_vnc_role_to_desktop_node") == 1
