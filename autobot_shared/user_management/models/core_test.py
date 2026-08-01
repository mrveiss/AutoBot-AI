# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``UserCore``/``OrganizationCore`` are the single shared implementation (#12647).

``models/user.py`` and ``models/organization.py`` were the last two files still
forked between the backends. They could not be relocated wholesale the way the
six models in #13130 were: backend genuinely carries more than SLM (activity
relationships #871; LLC/PM-sync columns #8211/#8257/#8241/#4451). The owner's
decision was an **abstract core** — shared columns/relationships/helpers
declared once, each backend keeping a thin concrete subclass for its own
extras.

The property that matters is that the move changed **nothing about either
schema**. These tests pin the post-move shape of both concrete tables against
the pre-move shape measured on ``origin/Dev_new_gui``, so a later edit that
drops a backend-only column, or quietly promotes one into the shared core,
fails here rather than in a migration.

Each concrete class is loaded in its **own subprocess**: backend's ``User`` and
SLM's ``User`` map the same ``users`` table name onto the same shared
``Base.metadata``, so importing both into one interpreter would collide.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from autobot_shared.user_management.models.organization import OrganizationCore
from autobot_shared.user_management.models.user import UserCore

_ROOT = pathlib.Path(__file__).resolve().parents[3]

# Measured on origin/Dev_new_gui *before* the cores were extracted, then
# re-measured after: identical in columns, types, nullability, index/unique,
# foreign keys (incl. ondelete) and relationship configuration.
_PINNED = {
    ("autobot-backend", "user"): {
        "columns": [
            "avatar_url",
            "bio",
            "created_at",
            "deleted_at",
            "display_name",
            "email",
            "email_verified_at",
            "id",
            "is_active",
            "is_platform_admin",
            "is_verified",
            "last_login_at",
            "mfa_enabled",
            "org_id",
            "password_hash",
            "preferences",
            "updated_at",
            "username",
        ],
        "relationships": [
            "api_keys",
            "browser_activities",
            "desktop_activities",
            "file_activities",
            "mfa",
            "organization",
            "secret_usage",
            "sso_links",
            "team_memberships",
            "terminal_activities",
            "user_roles",
        ],
    },
    ("autobot-backend", "organization"): {
        "columns": [
            "brand_color",
            "budget_monthly_cents",
            "created_at",
            "deleted_at",
            "description",
            "external_pm_config",
            "external_pm_type",
            "id",
            "is_active",
            "issue_counter",
            "issue_prefix",
            "kb_inheritance_weight",
            "llc_status",
            "max_users",
            "name",
            "parent_org_id",
            "pause_reason",
            "paused_at",
            "require_approval_for_hires",
            "settings",
            "slug",
            "spent_monthly_cents",
            "subscription_tier",
            "updated_at",
        ],
        "relationships": [
            "children",
            "parent",
            "roles",
            "sso_providers",
            "teams",
            "users",
        ],
    },
    ("autobot-slm-backend", "user"): {
        "columns": [
            "avatar_url",
            "bio",
            "created_at",
            "deleted_at",
            "display_name",
            "email",
            "email_verified_at",
            "id",
            "is_active",
            "is_platform_admin",
            "is_verified",
            "last_login_at",
            "mfa_enabled",
            "org_id",
            "password_hash",
            "preferences",
            "updated_at",
            "username",
        ],
        "relationships": [
            "api_keys",
            "mfa",
            "organization",
            "sso_links",
            "team_memberships",
            "user_roles",
        ],
    },
    ("autobot-slm-backend", "organization"): {
        "columns": [
            "created_at",
            "deleted_at",
            "description",
            "id",
            "is_active",
            "max_users",
            "name",
            "settings",
            "slug",
            "subscription_tier",
            "updated_at",
        ],
        "relationships": ["roles", "sso_providers", "teams", "users"],
    },
}

# What each backend must keep to itself — declaring any of these on the shared
# core would push a column into the other backend's schema (#12647's whole
# reason for an abstract core rather than a union model).
_BACKEND_ONLY = {
    "user": [
        "terminal_activities",
        "file_activities",
        "browser_activities",
        "desktop_activities",
        "secret_usage",
    ],
    "organization": [
        "parent_org_id",
        "issue_prefix",
        "issue_counter",
        "budget_monthly_cents",
        "spent_monthly_cents",
        "brand_color",
        "require_approval_for_hires",
        "llc_status",
        "pause_reason",
        "paused_at",
        "external_pm_type",
        "external_pm_config",
        "kb_inheritance_weight",
        "children",
        "parent",
    ],
}


def _dump_spec(backend: str, model: str) -> dict:
    """Load one concrete model in a fresh interpreter and return its spec."""
    path = _ROOT / backend / "user_management/models" / f"{model}.py"
    class_name = "User" if model == "user" else "Organization"
    env = dict(os.environ, PYTHONPATH=str(_ROOT))
    result = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__)), str(path), class_name],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        env=env,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("core", [UserCore, OrganizationCore])
def test_cores_are_abstract(core):
    """The shared core must never be mapped — each backend maps the table."""
    assert core.__dict__.get("__abstract__") is True
    assert "__tablename__" not in core.__dict__
    assert not hasattr(core, "__table__")


@pytest.mark.parametrize("backend,model", sorted(_PINNED))
def test_concrete_schema_is_unchanged_by_the_extraction(backend, model):
    """No column or relationship gained or lost when the core moved (#12647)."""
    spec = _dump_spec(backend, model)
    expected = _PINNED[(backend, model)]

    assert sorted(spec["columns"]) == expected["columns"]
    assert sorted(spec["relationships"]) == expected["relationships"]


@pytest.mark.parametrize("model", sorted(_BACKEND_ONLY))
def test_backend_only_features_stay_out_of_the_shared_core(model):
    """Promoting one of these into the core changes SLM's schema (#12647)."""
    core = UserCore if model == "user" else OrganizationCore
    declared = set(dir(core))

    leaked = sorted(name for name in _BACKEND_ONLY[model] if name in declared)
    assert leaked == [], f"backend-only names leaked into the shared core: {leaked}"


def test_slm_carries_no_columns_the_shared_core_lacks():
    """SLM was a strict subset — after the move it must be exactly the core."""
    for model in ("user", "organization"):
        spec = _dump_spec("autobot-slm-backend", model)
        core = UserCore if model == "user" else OrganizationCore
        core_names = set(dir(core))

        extra = sorted(c for c in spec["columns"] if c not in core_names)
        assert extra == [], f"SLM {model} declares columns outside the core: {extra}"


def test_org_id_keeps_its_foreign_key_and_nullability():
    """org_id moved into a declared_attr — its FK/index must survive (#12647)."""
    spec = _dump_spec("autobot-backend", "user")
    org_id = spec["columns"]["org_id"]

    assert org_id["nullable"] is True  # platform admins have no org
    assert org_id["index"] is True
    assert org_id["foreign_keys"] == ["organizations.id|CASCADE"]


def _main() -> None:
    """Subprocess entrypoint: dump one model's table spec as JSON.

    Kept in this module rather than a helper script so the isolation the tests
    need travels with them.
    """
    import importlib.util
    import types

    from sqlalchemy.orm import RelationshipProperty

    path, class_name = sys.argv[1], sys.argv[2]

    from autobot_shared.user_management.models import base as shared_base

    # The concrete modules import the backend-local shim package; stub the
    # package path so one file can be loaded without a whole backend.
    for name in ("user_management", "user_management.models"):
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    sys.modules["user_management.models.base"] = shared_base

    spec = importlib.util.spec_from_file_location("model_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["model_under_test"] = module
    spec.loader.exec_module(module)

    cls = getattr(module, class_name)
    columns = {
        c.name: {
            "type": str(c.type),
            "nullable": c.nullable,
            "primary_key": c.primary_key,
            "unique": bool(c.unique),
            "index": bool(c.index),
            "foreign_keys": sorted(f"{fk.target_fullname}|{fk.ondelete}" for fk in c.foreign_keys),
        }
        for c in cls.__table__.columns
    }
    relationships = {
        name: {
            "target": str(prop.argument),
            "back_populates": prop.back_populates,
            "uselist": prop.uselist,
        }
        for name, prop in cls.__mapper__._props.items()
        if isinstance(prop, RelationshipProperty)
    }
    print(json.dumps({"columns": columns, "relationships": relationships}))


if __name__ == "__main__":
    _main()
