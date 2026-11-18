# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046/#20567: migration 20261106_113 builds both one-pending-per-node indexes, and refuses duplicates by name."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa


def _migration():
    path = (
        Path(__file__).parents[1]
        / "migrations/versions/20261106_113_approvals_pending_ssh_password_and_env_copies_unique.py"
    )
    spec = importlib.util.spec_from_file_location("mig113_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, rows):
    mod = _migration()
    engine = sa.create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE approvals (status TEXT, context JSON)"))
        for action, key, value in rows:
            conn.execute(
                sa.text("INSERT INTO approvals VALUES ('pending', json_object('action', :a, :k, :v))"),
                {"a": action, "k": key, "v": value},
            )

        def execute(statement):  # this SQLite predates ``->>``
            return conn.execute(
                sa.text(re.sub(r"context ->> '(\w+)'", r"json_extract(context, '$.\1')", str(statement)))
            )

        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), execute=execute)
        create = MagicMock()
        monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
        monkeypatch.setattr(mod.op, "create_index", create)
        monkeypatch.setattr(mod, "has_table", lambda _t: True)
        monkeypatch.setattr(mod, "has_index", lambda _t, _i: False)
        mod.upgrade()
    return create


def test_it_chains_on_the_previous_head() -> None:
    assert _migration().down_revision == "20261105_111"


def test_it_creates_both_indexes_without_duplicates(monkeypatch) -> None:
    create = _run(monkeypatch, [("slm_node_ssh_password_delete", "node_id", "n1")])
    assert [c.args[0] for c in create.call_args_list] == [
        "uq_approvals_pending_ssh_password_deletion",
        "uq_approvals_pending_env_copies_cleanup",
    ]


def test_duplicate_ssh_proposals_fail_naming_the_node(monkeypatch) -> None:
    rows = [("slm_node_ssh_password_delete", "node_id", "n-dup")] * 2
    with pytest.raises(RuntimeError, match=r"n-dup \(2 pending\)"):
        _run(monkeypatch, rows)


def test_duplicate_cleanups_on_one_node_fail_and_other_nodes_do_not_collide(monkeypatch) -> None:
    ok = [("env_backup_copies_cleanup", "node", "a"), ("env_backup_copies_cleanup", "node", "b")]
    assert _run(monkeypatch, ok).call_count == 2
    with pytest.raises(RuntimeError, match=r"a \(2 pending\)"):
        _run(monkeypatch, ok[:1] * 2)


def test_the_env_copies_index_definition_matches_the_migration_and_the_model(monkeypatch) -> None:
    """Columns/expressions, uniqueness and the partial WHERE of the created index, against the model's index."""
    from sqlalchemy.dialects import postgresql

    from models.approval import PENDING_ENV_COPIES_INDEX, PENDING_ENV_COPIES_WHERE, Approval

    create = _run(monkeypatch, [])
    call = next(c for c in create.call_args_list if c.args[0] == PENDING_ENV_COPIES_INDEX)
    assert call.args[1] == "approvals" and call.kwargs["unique"] is True
    assert [str(e) for e in call.args[2]] == ["(context ->> 'action')", "(context ->> 'node')"]
    assert str(call.kwargs["postgresql_where"]) == PENDING_ENV_COPIES_WHERE
    model_index = {i.name: i for i in Approval.__table__.indexes}[PENDING_ENV_COPIES_INDEX]
    assert model_index.unique is True
    assert str(model_index.dialect_options["postgresql"]["where"]) == PENDING_ENV_COPIES_WHERE
    literal = {"dialect": postgresql.dialect(), "compile_kwargs": {"literal_binds": True}}
    model_expressions = [
        str(e.compile(**literal)).replace("approvals.", "").strip("()") for e in model_index.expressions
    ]
    assert model_expressions == [str(e).strip("()") for e in call.args[2]]
