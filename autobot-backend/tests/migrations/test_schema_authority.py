# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase C (#10001/#10026): migrations are the only schema authority.

Two permanent gates:

* the runtime guard in migrations/schema_bootstrap.py refuses
  ``create_all`` against anything but local SQLite data files unless
  ``AUTOBOT_DB_CREATE_ALL=true`` is set explicitly;
* a static sweep asserts no backend runtime code path calls
  ``metadata.create_all`` outside the allowlisted, guarded sites — the
  pattern that originally stranded fleet databases (#10026 case 3) cannot
  silently return.

No database needed.
"""

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Runtime files allowed to call metadata.create_all. Each entry must be a
# guarded site: lifespan's skills init goes through ensure_create_all_allowed.
ALLOWED_CREATE_ALL_FILES = {
    "initialization/lifespan.py",
}

# Directories that are not production runtime code.
NON_RUNTIME_PARTS = {"tests", "test", "migrations"}


def _runtime_py_files():
    for path in BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(BACKEND_ROOT)
        if NON_RUNTIME_PARTS & set(rel.parts):
            continue
        if rel.name.startswith("test_") or rel.name.endswith("_test.py"):
            continue
        yield rel, path


def _create_all_calls(path: Path) -> list[int]:
    """Line numbers of every ``<x>.metadata.create_all`` reference."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "create_all"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "metadata"
        ):
            lines.append(node.lineno)
    return lines


def test_no_unmanaged_create_all_in_runtime_code():
    """The schema-without-stamp faucet stays closed.

    Any new runtime metadata.create_all must go through the guarded helper
    and be added to the allowlist consciously — with an explanation of why
    it cannot be a migration.
    """
    offenders = {}
    for rel, path in _runtime_py_files():
        lines = _create_all_calls(path)
        if lines and str(rel) not in ALLOWED_CREATE_ALL_FILES:
            offenders[str(rel)] = lines
    assert not offenders, (
        "runtime metadata.create_all outside the allowlist — schema must come "
        f"from Alembic migrations (#10001): {offenders}"
    )


def test_guard_allows_sqlite():
    """Local SQLite data files are app-managed; create_all stays allowed."""
    from migrations.schema_bootstrap import ensure_create_all_allowed

    ensure_create_all_allowed("sqlite")  # must not raise


def test_guard_blocks_postgres_by_default(monkeypatch):
    """create_all against the alembic-managed dialect refuses without the flag."""
    from migrations.schema_bootstrap import ensure_create_all_allowed

    monkeypatch.delenv("AUTOBOT_DB_CREATE_ALL", raising=False)
    with pytest.raises(RuntimeError) as exc:
        ensure_create_all_allowed("postgresql")
    assert "AUTOBOT_DB_CREATE_ALL" in str(exc.value)
    assert "migration" in str(exc.value).lower()


def test_guard_flag_opts_in(monkeypatch):
    """Explicit AUTOBOT_DB_CREATE_ALL=true re-enables (dev/compose profiles)."""
    from migrations.schema_bootstrap import ensure_create_all_allowed

    monkeypatch.setenv("AUTOBOT_DB_CREATE_ALL", "true")
    ensure_create_all_allowed("postgresql")  # must not raise


def test_lifespan_skills_init_is_guarded():
    """lifespan's allowlisted create_all actually calls the guard."""
    source = (BACKEND_ROOT / "initialization" / "lifespan.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    skills_fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_init_skills_tables"
    )
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(skills_fn)
        if isinstance(node, ast.Call)
    }
    assert "ensure_create_all_allowed" in calls, (
        "_init_skills_tables must call ensure_create_all_allowed before create_all"
    )
