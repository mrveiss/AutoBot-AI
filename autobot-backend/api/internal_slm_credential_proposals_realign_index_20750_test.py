# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20750: migration 20261107_114 builds the one-pending-realign-per-node index, and refuses duplicates by name."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

_ACTION = "slm_backend_internal_key_realign"


def _migration():
    path = Path(__file__).parents[1] / "migrations/versions/20261107_114_approvals_pending_key_realign_unique.py"
    spec = importlib.util.spec_from_file_location("mig114_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, rows, dialect: str = "postgresql"):
    mod = _migration()
    engine = sa.create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE approvals (status TEXT, context JSON)"))
        for action, node in rows:
            conn.execute(
                sa.text("INSERT INTO approvals VALUES ('pending', json_object('action', :a, 'node_id', :n))"),
                {"a": action, "n": node},
            )

        def execute(statement):  # this SQLite predates ``->>``
            return conn.execute(
                sa.text(re.sub(r"context ->> '(\w+)'", r"json_extract(context, '$.\1')", str(statement)))
            )

        bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect), execute=execute)
        create = MagicMock()
        monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
        monkeypatch.setattr(mod.op, "create_index", create)
        monkeypatch.setattr(mod, "has_table", lambda _t: True)
        monkeypatch.setattr(mod, "has_index", lambda _t, _i: False)
        mod.upgrade()
    return create


def test_it_chains_on_the_previous_head() -> None:
    assert _migration().down_revision == "20261102_110"


def test_it_creates_the_realign_index_without_duplicates(monkeypatch) -> None:
    create = _run(monkeypatch, [(_ACTION, "n1"), (_ACTION, "n2")])
    assert [c.args[0] for c in create.call_args_list] == ["uq_approvals_pending_key_realign"]


def test_it_does_nothing_off_postgresql(monkeypatch) -> None:
    assert _run(monkeypatch, [], dialect="sqlite").call_count == 0


def test_duplicate_realign_proposals_fail_naming_the_node(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match=r"n-dup \(2 pending\)"):
        _run(monkeypatch, [(_ACTION, "n-dup")] * 2)


def test_other_actions_on_the_same_node_do_not_collide(monkeypatch) -> None:
    rows = [(_ACTION, "n1"), ("slm_node_ssh_password_delete", "n1")]
    assert _run(monkeypatch, rows).call_count == 1
