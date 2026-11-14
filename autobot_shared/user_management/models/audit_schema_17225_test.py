# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``audit_logs`` grew into the audit trail's system of record additively (#17225 D1).

Measured per column, the ``core_test.py`` way: the twelve columns the table had
before #17225 (measured on ``origin/main`` before the change) must be unchanged
in type, nullability, default and foreign key, and every added column must be
nullable or carry a server default -- so the migration rewrites no existing row.
The backend's Alembic revision and the SLM's migration must add exactly the
columns the model declares, or one of the two databases drifts from the model.
"""

import ast
import pathlib
from typing import Any

from autobot_shared.user_management.models.audit import AuditLog

_ROOT = pathlib.Path(__file__).resolve().parents[3]

#: (type, nullable, server_default, foreign keys) per column, before #17225.
_BEFORE: dict[str, tuple[Any, ...]] = {
    "action": ("VARCHAR(100)", False, None, []),
    "created_at": ("DATETIME", False, "now()", []),
    "details": ("JSONB", False, None, []),
    "id": ("UUID", False, None, []),
    "ip_address": ("VARCHAR(45)", True, None, []),
    "org_id": ("UUID", True, None, ["organizations.id"]),
    "outcome": ("VARCHAR(50)", False, None, []),
    "resource_id": ("UUID", True, None, []),
    "resource_type": ("VARCHAR(100)", False, None, []),
    "updated_at": ("DATETIME", False, "now()", []),
    "user_agent": ("VARCHAR(500)", True, None, []),
    "user_id": ("UUID", True, None, ["users.id"]),
}
_ADDED: dict[str, tuple[Any, ...]] = {
    "category": ("VARCHAR(32)", False, "security", []),
    "actor": ("VARCHAR(255)", True, None, []),
    "session_id": ("VARCHAR(255)", True, None, []),
    "resource_ref": ("VARCHAR(512)", True, None, []),
}
_BACKEND_MIGRATION = _ROOT / "autobot-backend/migrations/versions/20261011_098_audit_logs_canonical_columns.py"
_SLM_MIGRATION = _ROOT / "autobot-slm-backend/migrations/add_audit_logs_canonical_columns.py"


def _spec() -> dict[str, tuple[Any, ...]]:
    out = {}
    for col in AuditLog.__table__.columns:
        default = None if col.server_default is None else str(getattr(col.server_default, "arg", col.server_default))
        out[col.name] = (str(col.type), col.nullable, default, sorted(f.target_fullname for f in col.foreign_keys))
    return out


def test_every_pre_existing_column_is_unchanged() -> None:
    spec = _spec()
    assert {name: spec[name] for name in _BEFORE} == _BEFORE


def test_the_table_is_exactly_the_old_columns_plus_the_added_ones() -> None:
    assert _spec() == {**_BEFORE, **_ADDED}


def test_every_added_column_rewrites_no_existing_row() -> None:
    for name, (_type, nullable, server_default, _fk) in _ADDED.items():
        assert nullable or server_default is not None, f"{name} would need a value for every existing row"


def _backend_added_columns() -> set[str]:
    tree = ast.parse(_BACKEND_MIGRATION.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_column":
            column = node.args[1]
            assert isinstance(column, ast.Call) and isinstance(column.args[0], ast.Constant)
            names.add(column.args[0].value)
    return names


def test_the_backend_migration_adds_exactly_the_model_columns() -> None:
    assert _backend_added_columns() == set(_ADDED)


def test_the_slm_migration_adds_exactly_the_model_columns() -> None:
    text = _SLM_MIGRATION.read_text(encoding="utf-8")
    added = {name for name in _ADDED if f'"audit_logs", "{name}"' in text}
    assert added == set(_ADDED)
    assert "add_audit_logs_canonical_columns" in (_ROOT / "autobot-slm-backend/migrations/runner.py").read_text(
        encoding="utf-8"
    )


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def test_the_backend_downgrade_drops_nothing() -> None:
    """#17038: rolling back must not delete the audit records written into the new columns."""
    body = _function(ast.parse(_BACKEND_MIGRATION.read_text(encoding="utf-8")), "downgrade").body
    statements = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert statements == [], "downgrade() must stay a documented no-op"


def test_the_backend_builds_its_indexes_concurrently_outside_the_transaction() -> None:
    """A plain CREATE INDEX locks writes to audit_logs for the whole build."""
    tree = ast.parse(_BACKEND_MIGRATION.read_text(encoding="utf-8"))
    creates = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in {"create_index", "drop_index"}
    ]
    assert creates, "control: the detector must find the index calls"
    for call in creates:
        flag = {k.arg: k.value for k in call.keywords}.get("postgresql_concurrently")
        assert isinstance(flag, ast.Constant) and flag.value is True, ast.unparse(call)
    upgrade = _function(tree, "upgrade")
    blocks = [w for w in ast.walk(upgrade) if isinstance(w, ast.With)]
    assert any("autocommit_block" in ast.unparse(w.items[0].context_expr) for w in blocks)


def test_the_slm_builds_its_indexes_concurrently() -> None:
    text = _SLM_MIGRATION.read_text(encoding="utf-8")
    creates = [line for line in text.splitlines() if "CREATE INDEX" in line]
    assert len(creates) == 2 and all("CREATE INDEX CONCURRENTLY IF NOT EXISTS" in line for line in creates)
    assert "def downgrade" not in text and "DROP COLUMN" not in text.upper()
