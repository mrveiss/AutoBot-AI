# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for services/role_registry.py.

Verifies that the canonical role registry contains all expected roles
with correct field shapes, and that the new postgres + scheduler roles
(#9853) are present and correctly configured.

The root conftest stubs services.role_registry with a MagicMock so heavy
imports don't run in other test modules.  This module needs the real
implementation, so it removes the stub from sys.modules before importing.
"""

import importlib
import sys

# ---------------------------------------------------------------------------
# Bootstrap: bypass the MagicMock stubs from conftest and load the real
# role_registry module.  Approach:
#  1. Remove the MagicMock stub for services (and role_registry) so Python
#     will find the real package on sys.path.
#  2. Replace it with a hollow types.ModuleType that has __path__ set to the
#     real services/ directory — the same trick conftest uses for "api".
#  3. Provide thin shims for the two external symbols role_registry imports:
#     SyncType (from models.database) and the sqlalchemy async session type.
# ---------------------------------------------------------------------------
import types as _types
from pathlib import Path as _Path
from unittest.mock import MagicMock as _MagicMock

_SERVICES_DIR = str(_Path(__file__).parent.parent.parent / "services")

# Drop MagicMock stubs for everything role_registry transitively imports.
for _key in list(sys.modules):
    if _key in (
        "services",
        "services.role_registry",
        "models",
        "models.database",
        "sqlalchemy",
        "sqlalchemy.ext",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.orm",
    ):
        del sys.modules[_key]

# Hollow real-path package for services/ so submodule imports work.
_svc_pkg = _types.ModuleType("services")
_svc_pkg.__path__ = [_SERVICES_DIR]  # type: ignore[assignment]
_svc_pkg.__package__ = "services"
_svc_pkg.__spec__ = None  # type: ignore[assignment]
sys.modules["services"] = _svc_pkg

# SQLAlchemy shims — role_registry only imports AsyncSession for a type annotation.
for _m in ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"):
    sys.modules[_m] = _MagicMock()

# models.database shim — role_registry uses SyncType + Role.
_models_pkg = _types.ModuleType("models")
_models_pkg.__path__ = []  # type: ignore[assignment]
sys.modules["models"] = _models_pkg

_models_db = _types.ModuleType("models.database")


class _SyncTypeEnum:
    COMPONENT = _types.SimpleNamespace(value="component")
    PACKAGE = _types.SimpleNamespace(value="package")


_models_db.SyncType = _SyncTypeEnum  # type: ignore[attr-defined]
_models_db.Role = _MagicMock()  # type: ignore[attr-defined]
sys.modules["models.database"] = _models_db
setattr(_models_pkg, "database", _models_db)

_rr = importlib.import_module("services.role_registry")

DEFAULT_ROLES = _rr.DEFAULT_ROLES
ROLE_ANSIBLE_GROUPS = _rr.ROLE_ANSIBLE_GROUPS
ROLE_DEPENDENCIES = _rr.ROLE_DEPENDENCIES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _role(name: str) -> dict:
    """Return the DEFAULT_ROLES entry matching *name*, or raise."""
    for r in DEFAULT_ROLES:
        if r["name"] == name:
            return r
    raise KeyError(f"Role not found in DEFAULT_ROLES: {name!r}")


# ---------------------------------------------------------------------------
# Schema shape tests
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"name", "display_name", "required", "degraded_without", "ansible_playbook"}


def test_all_roles_have_required_fields():
    for role in DEFAULT_ROLES:
        missing = REQUIRED_FIELDS - role.keys()
        assert not missing, f"Role {role.get('name')!r} missing fields: {missing}"


def test_role_names_are_unique():
    names = [r["name"] for r in DEFAULT_ROLES]
    assert len(names) == len(set(names)), "Duplicate role names in DEFAULT_ROLES"


# ---------------------------------------------------------------------------
# Postgres role (#9853)
# ---------------------------------------------------------------------------


def test_postgres_role_present():
    role = _role("postgres")
    assert role["display_name"] == "PostgreSQL"
    assert role["systemd_service"] == "postgresql"
    assert role["required"] is True
    assert role["auto_restart"] is True
    # No AutoBot playbook owns postgres provisioning; api/roles.py returns 422.
    assert role["ansible_playbook"] is None
    assert role["sync_type"] is None
    # Non-empty target_path ensures role_detector activates path + systemd checks.
    assert role["target_path"] == "/var/lib/postgresql"


def test_postgres_in_databases_ansible_group():
    assert ROLE_ANSIBLE_GROUPS["postgres"] == "databases"


def test_postgres_dependencies():
    assert ROLE_DEPENDENCIES["postgres"] == ["postgresql"]


# ---------------------------------------------------------------------------
# Scheduler role (#9853)
# ---------------------------------------------------------------------------


def test_scheduler_role_present():
    role = _role("scheduler")
    assert role["display_name"] == "Celery Beat Scheduler"
    assert role["systemd_service"] == "autobot-celery-beat"
    assert role["required"] is True
    assert role["auto_restart"] is True
    assert role["ansible_playbook"] == "deploy-backend.yml"


def test_scheduler_in_backend_ansible_group():
    assert ROLE_ANSIBLE_GROUPS["scheduler"] == "backend"


def test_scheduler_dependencies():
    assert ROLE_DEPENDENCIES["scheduler"] == ["python314"]


# ---------------------------------------------------------------------------
# Cross-registry consistency
# ---------------------------------------------------------------------------


def test_all_default_roles_have_ansible_group_entry():
    """Every role in DEFAULT_ROLES that is not an infra-only role must appear
    in ROLE_ANSIBLE_GROUPS so the dynamic inventory builder works."""
    # Infra roles (autobot_shared, slm-agent, docker) are intentionally absent —
    # they are installed on every node and don't map to a single inventory group.
    exempt = {"autobot_shared", "slm-agent", "docker"}
    for role in DEFAULT_ROLES:
        name = role["name"]
        if name in exempt:
            continue
        assert name in ROLE_ANSIBLE_GROUPS, f"Role {name!r} missing from ROLE_ANSIBLE_GROUPS"


def test_all_default_roles_have_dependency_entry():
    """Every non-infra role must have an entry in ROLE_DEPENDENCIES."""
    exempt = {"docker", "autobot_shared", "slm-agent"}
    for role in DEFAULT_ROLES:
        name = role["name"]
        if name in exempt:
            continue
        assert name in ROLE_DEPENDENCIES, f"Role {name!r} missing from ROLE_DEPENDENCIES"


def test_serviceable_roles_include_postgres_and_scheduler():
    """Roles with a systemd_service (surfaced by get_role_definitions) include
    both new roles added in #9853."""
    defs = {r["name"] for r in DEFAULT_ROLES if r.get("target_path") or r.get("systemd_service")}
    assert "postgres" in defs
    assert "scheduler" in defs


# ---------------------------------------------------------------------------
# VNC role (#9965)
# ---------------------------------------------------------------------------


def test_vnc_role_has_non_empty_target_path():
    """vnc must have a non-empty target_path so role_detector.py does not skip
    it due to the old guard that only checked target_path (#9965)."""
    role = _role("vnc")
    assert role["target_path"], "vnc target_path must be non-empty so role_detector detects it"
    assert role["systemd_service"] == "tigervncserver"
    assert role["required"] is False


def test_vnc_in_get_role_definitions():
    """get_role_definitions must include vnc so agents receive its detection spec."""
    defs_by_name = (
        {r["name"]: r for r in _rr.get_role_definitions.__wrapped__()}  # sync call
        if hasattr(_rr.get_role_definitions, "__wrapped__")
        else None
    )
    # Fallback: inspect DEFAULT_ROLES directly (get_role_definitions is async)
    detectable = {r["name"] for r in DEFAULT_ROLES if r.get("target_path") or r.get("systemd_service")}
    assert "vnc" in detectable, "vnc must be in the detectable role set (has target_path or systemd_service)"


def test_optional_roles_are_not_required():
    """docker, browser-service, tts-worker and vnc must all be optional (required=False)
    so they cannot cause health=degraded on their own (#9965)."""
    optional_names = {
        "docker",
        "browser-service",
        "tts-worker",
        "vnc",
        "npu-worker",
        "autobot-llm-cpu",
        "autobot-llm-gpu",
        "slm-monitoring",
    }
    for name in optional_names:
        role = _role(name)
        assert role["required"] is False, f"{name} should be optional (required=False)"


# ---------------------------------------------------------------------------
# seed_default_roles upsert logic (#11132)
#
# The SLM conftest stubs sqlalchemy, so a real-DB test isn't feasible here; this
# drives seed_default_roles against a mock async session to prove it refreshes a
# stale registry-owned field on an already-seeded row (the insert-only bug).
# ---------------------------------------------------------------------------
import asyncio as _asyncio
from unittest.mock import AsyncMock as _AsyncMock


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


def test_seed_default_roles_upserts_stale_field_on_existing_row():
    target_idx, target = next((i, r) for i, r in enumerate(DEFAULT_ROLES) if r.get("post_sync_cmd"))
    existing = _types.SimpleNamespace(**dict(target))
    existing.post_sync_cmd = "STALE_BROKEN_CMD"
    existing.source_paths = ["WRONG/"]

    # execute() is called once per role in order → existing row only at the target index.
    results = [_Result(existing if i == target_idx else None) for i in range(len(DEFAULT_ROLES))]
    db = _AsyncMock()
    db.execute = _AsyncMock(side_effect=results)
    db.commit = _AsyncMock()
    db.add = _MagicMock()

    created = _asyncio.run(_rr.seed_default_roles(db))

    # Stale registry-owned fields refreshed from DEFAULT_ROLES; created counts new rows only.
    assert existing.post_sync_cmd == target["post_sync_cmd"]
    assert existing.source_paths == target["source_paths"]
    assert created == len(DEFAULT_ROLES) - 1
    db.commit.assert_awaited()


def test_seed_default_roles_no_write_when_existing_rows_match_registry():
    # Every role already exists with registry-identical values → no commit, created == 0.
    existing_rows = [_types.SimpleNamespace(**dict(r)) for r in DEFAULT_ROLES]
    db = _AsyncMock()
    db.execute = _AsyncMock(side_effect=[_Result(row) for row in existing_rows])
    db.commit = _AsyncMock()
    db.add = _MagicMock()

    created = _asyncio.run(_rr.seed_default_roles(db))

    assert created == 0
    db.commit.assert_not_awaited()
    db.add.assert_not_called()


def test_backend_post_sync_rewrites_root_requirements_not_strips_it():
    """The backend post_sync_cmd must REWRITE `-r ../requirements.txt` to the
    code_source path (so the root runtime deps install on deploy), not strip it
    like the old `grep -Ev '...|^-r'` did — #11135."""
    backend = next(r for r in DEFAULT_ROLES if r["name"] == "backend")
    cmd = backend["post_sync_cmd"]
    # rewrite present (sed maps the sibling include to code_source)
    assert "s|^-r \\.\\./requirements.txt|-r " in cmd
    assert "/code_source/requirements.txt|" in cmd
    # and the grep no longer drops -r lines
    assert "^-r" not in cmd.split("| sed")[0]
    # the -c constraints rewrite (#11117) is preserved
    assert "s|^-c \\.\\./constraints/|-c " in cmd
