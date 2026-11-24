# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#22033: the migration builds the one-pending-per-location index the model declares, and refuses duplicates."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

_NAME = "20261124_123_approvals_pending_stale_sync_files_unique.py"
_ACTION = "slm_node_stale_sync_files_cleanup"


def _migration():
    spec = importlib.util.spec_from_file_location(
        "mig_stale_files_test", Path(__file__).parents[1] / "migrations/versions" / _NAME
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, locations: list[str]):
    mod = _migration()
    engine = sa.create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE approvals (status TEXT, context JSON)"))
        for location in locations:
            conn.execute(
                sa.text("INSERT INTO approvals VALUES ('pending', json_object('action', :a, 'location', :l))"),
                {"a": _ACTION, "l": location},
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


def test_it_chains_on_the_head_it_was_written_against() -> None:
    assert _migration().down_revision == "20261122_121"


def test_distinct_locations_build_the_index_and_a_duplicate_location_fails_naming_it(monkeypatch) -> None:
    assert _run(monkeypatch, ["n1:/a", "n1:/b", "n2:/a"]).call_count == 1
    with pytest.raises(RuntimeError, match=r"n1:/a \(2 pending\)"):
        _run(monkeypatch, ["n1:/a", "n1:/a"])


def test_the_migration_index_is_the_model_index(monkeypatch) -> None:
    """Expression, uniqueness and the partial WHERE of the created index, against the model's index."""
    from models.approval import PENDING_STALE_SYNC_FILES_INDEX, PENDING_STALE_SYNC_FILES_WHERE, Approval

    call = _run(monkeypatch, []).call_args
    assert call.args[0] == PENDING_STALE_SYNC_FILES_INDEX and call.kwargs["unique"] is True
    assert [str(e) for e in call.args[2]] == ["(context ->> 'location')"]
    assert str(call.kwargs["postgresql_where"]) == PENDING_STALE_SYNC_FILES_WHERE
    index = {i.name: i for i in Approval.__table__.indexes}[PENDING_STALE_SYNC_FILES_INDEX]
    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == PENDING_STALE_SYNC_FILES_WHERE
