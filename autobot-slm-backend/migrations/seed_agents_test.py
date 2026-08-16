# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""seed_agents must do the seeding it reports, not just import cleanly (#14321).

Before this fix `migrations/seed_agents.py` defined only a standalone async
`seed_agents()` function that imported `backend.api.agent_config` -- a module
path that has never existed from this package (the top-level directory is
`autobot-backend`, not `backend`). Because `migrations.runner.run_migration`
calls a module by `migrate()`/`run()` and falls back to "Loaded migration:
<name> (no migrate function)" == success when neither exists, the runner
never even attempted that broken function -- it just recorded `seed_agents`
applied in `migrations_applied` and moved on. No agent was ever seeded via
this path.

These tests drive the real `migrate(db_url)` entry point this issue adds
against a fake psycopg2 connection and assert the canonical roster
(`models.agent_seed_roster.SEED_AGENT_CONFIGS` -- the same list main.py's
startup lifespan seeds with on every boot) actually lands as rows, not
merely that the function returns without raising. A `migrate()` reverted to
a no-op (e.g. `return` before the loop, or an empty SEED_AGENT_CONFIGS) goes
red here: the row-count and per-agent assertions both depend on rows the
fake cursor only gains when `execute()` is actually called with an INSERT
per configured agent.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from migrations import seed_agents

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _real_load(name: str, relative: str):
    """Load a module from its file, bypassing whatever the ambient test
    session's package-level stubs (autobot-slm-backend/conftest.py) may have
    installed for its parent package -- mirrors conftest's own
    `_REAL_SERVICE_MODULES` idiom for exactly this situation."""
    spec = importlib.util.spec_from_file_location(name, _BACKEND_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def real_agent_seeder():
    """The real roster, loaded from its leaf module (#14321).

    `migrate()` imports `models.agent_seed_roster.SEED_AGENT_CONFIGS` lazily
    (inside the function body) so it always resolves the roster current at call
    time. Force that name to the REAL module for the duration of the test,
    restoring whatever was there before.

    Deliberately NOT loaded through `services.agent_seeder`: importing that
    package executes `services/__init__.py`, which eagerly imports `.auth` /
    `.deployment` / `.reconciler` and drags FastAPI in. That is the same import
    chain that failed the SLM migration gate with `No module named 'fastapi'`,
    and a test reaching the roster by a heavier route than production does would
    stop reproducing the environment the migration actually runs in.
    """
    previous = sys.modules.get("models.agent_seed_roster")
    module = _real_load("models.agent_seed_roster", "models/agent_seed_roster.py")
    models_pkg = sys.modules.get("models")
    if models_pkg is not None:
        setattr(models_pkg, "agent_seed_roster", module)
    yield module
    if previous is not None:
        sys.modules["models.agent_seed_roster"] = previous
        if models_pkg is not None:
            setattr(models_pkg, "agent_seed_roster", previous)
    else:
        sys.modules.pop("models.agent_seed_roster", None)


class _FakeCursor:
    """Minimal psycopg2-cursor stand-in that actually applies the
    ON CONFLICT (agent_id) DO NOTHING semantics `migrate()` relies on, so the
    test exercises the same idempotency contract Postgres provides in
    production and the SLM migration gate's live-Postgres run.

    `table_exists()` is monkeypatched directly at the module level below
    (like `get_connection()`), so this cursor only ever needs to understand
    the INSERT statement `migrate()` issues."""

    def __init__(self, store: dict):
        self._store = store
        self.executed: list[tuple[str, tuple]] = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "insert into agents" in sql.lower():
            agent_id = params[0]
            if agent_id in self._store:
                self.rowcount = 0
            else:
                self._store[agent_id] = dict(
                    zip(
                        (
                            "agent_id",
                            "name",
                            "description",
                            "llm_provider",
                            "llm_endpoint",
                            "llm_model",
                            "llm_timeout",
                            "llm_temperature",
                            "llm_max_tokens",
                            "is_default",
                            "is_active",
                        ),
                        params,
                    )
                )
                self.rowcount = 1


class _FakeConnection:
    def __init__(self, store: dict):
        self._store = store
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._store)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _clear_deferrals():
    from migrations import utils as _utils

    _utils.reset_deferrals()
    yield
    _utils.reset_deferrals()


def test_migrate_seeds_every_agent_in_the_canonical_roster(monkeypatch, real_agent_seeder):
    """The row-count bar: migrate() must produce one row per
    SEED_AGENT_CONFIGS entry, not just "no exception raised"."""
    store: dict = {}
    monkeypatch.setattr(seed_agents, "get_connection", lambda db_url: _FakeConnection(store))
    monkeypatch.setattr(seed_agents, "table_exists", lambda cursor, name: True)

    seed_agents.migrate("postgresql://fake/slm")

    roster = real_agent_seeder.SEED_AGENT_CONFIGS
    assert roster, "fixture loaded an empty roster -- test would pass vacuously"
    assert set(store.keys()) == {cfg["agent_id"] for cfg in roster}
    assert len(store) == len(roster)


def test_migrate_writes_the_configured_fields_per_agent(monkeypatch, real_agent_seeder):
    """Not just presence -- the seeded row must carry the roster's own model,
    default flag, and the SSOT-resolved Ollama endpoint."""
    from autobot_shared.ssot_config import config as ssot_config

    store: dict = {}
    monkeypatch.setattr(seed_agents, "get_connection", lambda db_url: _FakeConnection(store))
    monkeypatch.setattr(seed_agents, "table_exists", lambda cursor, name: True)

    seed_agents.migrate("postgresql://fake/slm")

    orchestrator_cfg = next(c for c in real_agent_seeder.SEED_AGENT_CONFIGS if c["agent_id"] == "orchestrator")
    row = store["orchestrator"]
    assert row["is_default"] is True
    assert row["llm_model"] == orchestrator_cfg["llm_model"]
    assert row["llm_provider"] == "ollama"
    assert row["llm_endpoint"] == ssot_config.llm.ollama_endpoint

    chat_cfg = next(c for c in real_agent_seeder.SEED_AGENT_CONFIGS if c["agent_id"] == "chat")
    assert store["chat"]["is_default"] is False
    assert store["chat"]["llm_model"] == chat_cfg["llm_model"]


def test_migrate_is_idempotent_on_a_second_run(monkeypatch, real_agent_seeder):
    """Mirrors the SLM migration gate's pass (b): re-running against an
    already-seeded table must not duplicate or error."""
    store: dict = {}
    monkeypatch.setattr(seed_agents, "get_connection", lambda db_url: _FakeConnection(store))
    monkeypatch.setattr(seed_agents, "table_exists", lambda cursor, name: True)

    seed_agents.migrate("postgresql://fake/slm")
    first_run_count = len(store)

    seed_agents.migrate("postgresql://fake/slm")

    assert len(store) == first_run_count


def test_migrate_defers_rather_than_crashes_when_agents_table_is_absent(monkeypatch, real_agent_seeder):
    """#14300 pattern: a missing target table must be recorded as a deferral
    (retried next boot), never marked applied, and never a hard crash."""
    from migrations import utils as _utils

    store: dict = {}
    monkeypatch.setattr(seed_agents, "get_connection", lambda db_url: _FakeConnection(store))
    monkeypatch.setattr(seed_agents, "table_exists", lambda cursor, name: False)

    seed_agents.migrate("postgresql://fake/slm")

    assert store == {}
    assert _utils.deferrals() == ["agents"]


def test_the_migration_never_imports_the_service_package():
    """Regression guard for the FastAPI drag (#14321).

    `services/__init__.py` eagerly imports `.auth`, `.database`, `.deployment`
    and `.reconciler`, so ANY `from services.… import …` inside a migration
    pulls FastAPI into the migration runner — which does not have it, and
    should not: a schema migration must not depend on the HTTP layer. That is
    exactly how this migration first failed the SLM migration gate.

    Asserts the invariant rather than the one import that was fixed: any future
    `services.` import in this module reddens here instead of in a live gate run.
    """
    import ast

    migration = _BACKEND_ROOT / "migrations" / "seed_agents.py"
    tree = ast.parse(migration.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("services"):
            offenders.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            offenders += [
                f"line {node.lineno}: import {alias.name}"
                for alias in node.names
                if alias.name.startswith("services")
            ]

    assert offenders == [], (
        "the migration imports the services package, which drags FastAPI into "
        f"the migration runner: {offenders}"
    )
