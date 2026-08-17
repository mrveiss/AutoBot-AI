# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A migration can declare a database other than DATABASE_URL (#14300).

``add_role_permission_audit_log_timestamps`` alters ``role_permissions`` and
``audit_logs`` — user_management tables that live in a database separate
from the one ``migrations.runner`` connects to for everything else
(``DATABASE_URL``). Before this change the runner had no way to express
that, so the migration's own ``table_exists`` checks always failed and it
deferred forever without ever reaching its tables (#14300's root cause,
isolated by #14370's real-Postgres gate).

Two things this file exists to prove:

1. A migration that declares no ``TARGET_DB`` keeps using ``DATABASE_URL``
   unchanged -- every migration written before #14300 is unaffected.
2. A migration that declares ``TARGET_DB_USER_MANAGEMENT`` gets the
   user_management database's URL instead, sourced from the same config
   module (``user_management.config.get_slm_db_config``) the SLM backend
   itself already uses to open that database at startup -- not a second,
   hardcoded connection string.
3. An unrecognized ``TARGET_DB`` value raises immediately rather than
   silently falling back to a database that cannot see the migration's own
   tables -- the exact failure mode (a wrong target that looks like an
   ordinary deferral) this change exists to make loud.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_MIGRATION_PATH = _BACKEND_ROOT / "migrations" / "add_role_permission_audit_log_timestamps.py"


def _migration_source() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Structural -- no import, so these run regardless of whether psycopg2 is
# installed in this environment.
# ---------------------------------------------------------------------------


def test_the_migration_declares_a_target_db():
    """The migration must opt into the user_management database explicitly --
    a silent default would put it right back on DATABASE_URL (#14300)."""
    tree = ast.parse(_migration_source())
    module_level_names = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "TARGET_DB" in module_level_names, (
        "add_role_permission_audit_log_timestamps.py must set a module-level "
        "TARGET_DB, or migrations.runner falls back to DATABASE_URL and the "
        "migration can never reach role_permissions/audit_logs again"
    )


def test_the_migration_imports_the_user_management_target_constant():
    """Guards against the value drifting to a literal that no longer matches
    ``migrations.runner.TARGET_DB_USER_MANAGEMENT`` (#14300)."""
    tree = ast.parse(_migration_source())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "migrations.runner"
        for alias in node.names
    }
    assert "TARGET_DB_USER_MANAGEMENT" in imported


# ---------------------------------------------------------------------------
# Behavioural -- require importing the real modules (psycopg2).
# ---------------------------------------------------------------------------

psycopg2 = pytest.importorskip("psycopg2")


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, _BACKEND_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.fixture
def runner():
    return _load("_runner_14300", "migrations/runner.py")


class _Module:
    """A bare object standing in for an imported migration module."""


def test_a_module_with_no_target_db_uses_the_default_url(runner):
    module = _Module()

    resolved = runner._resolve_migration_db_url(module, "postgresql://default-db/slm")

    assert resolved == "postgresql://default-db/slm"


def test_a_module_targeting_user_management_gets_that_databases_url(runner, monkeypatch):
    module = _Module()
    module.TARGET_DB = runner.TARGET_DB_USER_MANAGEMENT

    monkeypatch.setattr(runner, "get_user_management_db_url", lambda: "postgresql://um-db/slm_users")

    resolved = runner._resolve_migration_db_url(module, "postgresql://default-db/slm")

    assert resolved == "postgresql://um-db/slm_users"


def test_an_unrecognized_target_db_raises_instead_of_deferring(runner):
    module = _Module()
    module.TARGET_DB = "some_other_database_nobody_wired_up"
    module.__name__ = "pretend_migration"

    with pytest.raises(ValueError, match="unknown TARGET_DB"):
        runner._resolve_migration_db_url(module, "postgresql://default-db/slm")


def test_run_migration_passes_the_resolved_url_to_migrate(runner, monkeypatch):
    """The resolution must actually reach the migration's entry point, not
    just exist as a helper nothing calls (#14300)."""
    captured = {}

    class _TargetedMigration:
        TARGET_DB = runner.TARGET_DB_USER_MANAGEMENT

        @staticmethod
        def migrate(db_url):
            captured["db_url"] = db_url

    monkeypatch.setattr(runner.importlib, "import_module", lambda _name: _TargetedMigration(), raising=False)
    monkeypatch.setattr(runner, "get_user_management_db_url", lambda: "postgresql://um-db/slm_users")

    success, message = runner.run_migration("postgresql://default-db/slm", "pretend_migration")

    assert success is True
    assert captured["db_url"] == "postgresql://um-db/slm_users"


def test_run_migration_defaults_untargeted_migrations_to_database_url(runner, monkeypatch):
    """A migration that declares no TARGET_DB must keep behaving exactly as
    it did before #14300 -- no regression for the other 26 migrations."""
    captured = {}

    class _UntargetedMigration:
        @staticmethod
        def migrate(db_url):
            captured["db_url"] = db_url

    monkeypatch.setattr(runner.importlib, "import_module", lambda _name: _UntargetedMigration(), raising=False)

    success, message = runner.run_migration("postgresql://default-db/slm", "pretend_migration")

    assert success is True
    assert captured["db_url"] == "postgresql://default-db/slm"


def test_the_real_migration_module_targets_user_management(runner):
    """Connects the structural assertions above to the runner's own constant
    -- both must agree, not merely each compile independently."""
    migration = _load("_mig_14300_target", "migrations/add_role_permission_audit_log_timestamps.py")

    assert migration.TARGET_DB == runner.TARGET_DB_USER_MANAGEMENT
