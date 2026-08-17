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
import re as _re
import subprocess as _subprocess
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

import pytest
import yaml as _yaml

_SERVICES_DIR = str(_Path(__file__).parent.parent.parent / "services")

_TOUCHED_KEYS = (
    "services",
    "services.role_registry",
    "models",
    "models.database",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
)

# #11478: snapshot every key this bootstrap touches so the pre-import state
# can be restored after the import below.  Leaking the thin models.database
# shim broke later modules in the same directory sweep (git_tracker's
# CodeSource import in version_checker_test).
_SAVED_MODULES = {_key: sys.modules[_key] for _key in _TOUCHED_KEYS if _key in sys.modules}

# Drop MagicMock stubs for everything role_registry transitively imports.
for _key in _TOUCHED_KEYS:
    sys.modules.pop(_key, None)

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

# #11478: restore the pre-bootstrap sys.modules state.  The tests below only
# use the _rr reference, so the shims are not needed at runtime — leaving them
# in sys.modules poisons every module collected after this one.
for _key in _TOUCHED_KEYS:
    if _key in _SAVED_MODULES:
        sys.modules[_key] = _SAVED_MODULES[_key]
    else:
        sys.modules.pop(_key, None)

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
    # #12170: postgres now has a dedicated deploy playbook (was None → 422).
    assert role["ansible_playbook"] == "playbooks/deploy-postgres-role.yml"
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
    # #12083: "deploy-backend.yml" never existed under ansible/ (FileNotFoundError
    # on every Migrate); scheduler now shares the generic role dispatcher
    # (playbooks/deploy_role.yml), which include_role: backend for
    # deploy_role in ['backend', 'celery', 'scheduler'].
    assert role["ansible_playbook"] == "playbooks/deploy_role.yml"


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
    if defs_by_name is not None:
        assert "vnc" in defs_by_name, "vnc must be returned by get_role_definitions"
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


def test_backend_post_sync_delegates_to_canonical_filter_script():
    """The backend post_sync_cmd must delegate the filter+rewrite to the
    canonical scripts/build-filtered-requirements.sh (#11134) — not re-inline
    its own grep|sed copy, which is what let it drift from the ansible role's
    copy (that dropped `-r` lines entirely instead of rewriting them — #11135)."""
    backend = next(r for r in DEFAULT_ROLES if r["name"] == "backend")
    cmd = backend["post_sync_cmd"]
    assert "scripts/build-filtered-requirements.sh" in cmd
    assert "requirements.txt" in cmd
    assert "/code_source" in cmd
    # no re-inlined grep|sed pipeline duplicating the script's logic
    assert "grep -Ev" not in cmd
    assert "sed 's|" not in cmd


def test_build_filtered_requirements_script_rewrites_root_requirements_not_strips_it(tmp_path):
    """Behavioral-equivalence check for scripts/build-filtered-requirements.sh
    (#11134): must REWRITE `-r ../requirements.txt` and `-c ../constraints/...`
    to the code_source path, not strip `-r` like the old ansible-role copy did
    — #11135, #11117."""
    script = _Path(__file__).parent.parent.parent.parent / "scripts" / "build-filtered-requirements.sh"
    assert script.is_file(), f"canonical script missing: {script}"

    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "-e ../autobot_shared\n"
        "-c ../constraints/shared.txt  # comment\n"
        "fastapi>=0.139.2\n"
        "-r ../requirements.txt\n",
        encoding="utf-8",
    )

    result = _subprocess.run(
        ["bash", str(script), str(requirements), "/opt/autobot/code_source"],
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout

    assert "-e ../autobot_shared" not in output
    assert "-c /opt/autobot/code_source/constraints/shared.txt" in output
    assert "-r /opt/autobot/code_source/requirements.txt" in output
    assert "fastapi>=0.139.2" in output


# ---------------------------------------------------------------------------
# Ansible playbook resolution (#12170 gave postgres a real playbook; guards the
# #12083/#12095 bug class where an ansible_playbook points at a non-existent
# file, making per-role Migrate raise FileNotFoundError / return HTTP 422).
# ---------------------------------------------------------------------------

_ANSIBLE_DIR = _Path(__file__).parent.parent.parent / "ansible"


def test_postgres_has_deploy_playbook():
    """#12170: postgres must have a real deploy playbook (was None -> HTTP 422)."""
    assert _role("postgres")["ansible_playbook"] == "playbooks/deploy-postgres-role.yml"


def test_all_role_ansible_playbooks_resolve():
    """Every configured ansible_playbook resolves to a real file under ansible/,
    so per-role Migrate/Redeploy can never FileNotFoundError."""
    missing = []
    for role in DEFAULT_ROLES:
        pb = role.get("ansible_playbook")
        if not pb:
            continue
        if not (_ANSIBLE_DIR / pb).is_file():
            missing.append(f"{role['name']} -> {pb}")
    assert not missing, f"role ansible_playbook(s) missing under {_ANSIBLE_DIR}: {missing}"


# ---------------------------------------------------------------------------
# #14446: the two registry maps must agree about what a node actually runs
# ---------------------------------------------------------------------------
#
# ROLE_ANSIBLE_GROUPS decides which inventory GROUP a role joins.
# ROLE_DEPENDENCIES decides what Phase 0 installs on the node.
#
# They are independent, and they disagreed: "vnc" joins the *backend* group,
# so Phase 4a applied the backend ansible role and created a python3.14 venv,
# while "vnc": [] told Phase 0 to install no interpreter. Provisioning failed
# with "No such file or directory: b'python3.14'" -- an error naming the venv
# rather than the dependency, on a node whose declared roles never mentioned
# the backend at all.
#
# The requirement is DERIVED here rather than listed. A test that restated
# either map would have passed: each map is self-consistent on its own, and
# the defect lives in the relationship between them.


def _activation_sources() -> dict:
    """ansible role -> what switches it on: inventory groups AND node roles.

    Read out of `role_active_facts.yml`, which is what the provisioning
    playbook actually gates each `include_role` on. Both clauses matter: a
    role activates either because the node landed in a group or because the
    node declares the role by name, and covering only the group half leaves
    the node-roles half unguarded -- which is how the `redis` gap survived
    the first version of this rule.
    """
    facts_file = _ANSIBLE_DIR / "playbooks" / "vars" / "role_active_facts.yml"
    text = facts_file.read_text(encoding="utf-8")

    activating: dict = {}
    current = None
    for line in text.splitlines():
        match = _re.match(r"^role_([a-z0-9_]+)_active:", line)
        if match:
            current = match.group(1).replace("_", "-")
            activating.setdefault(current, {"groups": set(), "roles": set()})
            continue
        if current:
            for group in _re.findall(r"groups\.get\('([a-z0-9_]+)'", line):
                activating[current]["groups"].add(group)
            for role in _re.findall(r"'([a-z0-9_-]+)' in \(node_roles", line):
                activating[current]["roles"].add(role)
    return activating


def _groups_activating_ansible_role() -> dict:
    """The group half, kept as its own view for the derivation self-check."""
    return {role: sources["groups"] for role, sources in _activation_sources().items()}


def _role_tasks(role_name: str):
    """Every task in an ansible role, including those nested in block/rescue/always."""

    def walk(tasks):
        for task in tasks or []:
            if not isinstance(task, dict):
                continue
            yield task
            for key in ("block", "rescue", "always"):
                if isinstance(task.get(key), list):
                    yield from walk(task[key])

    for candidate in (role_name, role_name.replace("-", "_")):
        tasks_dir = _ANSIBLE_DIR / "roles" / candidate / "tasks"
        if not tasks_dir.is_dir():
            continue
        for task_file in sorted(tasks_dir.rglob("*.yml")):
            try:
                parsed = _yaml.safe_load(task_file.read_text(encoding="utf-8"))
            except _yaml.YAMLError:
                continue
            if isinstance(parsed, list):
                yield from walk(parsed)


def _ansible_role_needs_python(role_name: str) -> bool:
    """Does this ansible role build a Python venv?

    Matched structurally, on any command that runs `-m venv`. An earlier
    version looked for two hand-picked literals ("virtual environment via
    deadsnakes" / "python_interpreter_version") and silently missed ai-stack,
    whose task is named "Create Python virtual environment (#3534)" and runs
    `python3.14 -m venv` directly -- so that whole group went unguarded while
    the rule still reported success.
    """
    for task in _role_tasks(role_name):
        for module in ("ansible.builtin.command", "ansible.builtin.shell", "command", "shell"):
            spec = task.get(module)
            body = spec if isinstance(spec, str) else (spec or {}).get("cmd", "") if isinstance(spec, dict) else ""
            if "-m venv" in str(body):
                return True
        if "python_interpreter_version" in str(task):
            return True
    return False


def _ansible_role_needs_nginx(role_name: str) -> bool:
    """Does this ansible role start nginx unconditionally?

    `when`-gated starts do not count: those roles run fine on a node where the
    condition is false. An UNgated `systemd: name=nginx state=started` means
    the package has to be there, whatever the node's declared roles say.
    """
    for task in _role_tasks(role_name):
        if "when" in task:
            continue
        for module in ("ansible.builtin.systemd", "ansible.builtin.service", "systemd", "service"):
            spec = task.get(module)
            if isinstance(spec, dict) and spec.get("name") == "nginx" and spec.get("state") == "started":
                return True
    return False


# What each shared dependency is detected by, so the rule below covers every
# dependency the ansible roles actually impose rather than just the one that
# happened to fail first.
_DEPENDENCY_PROBES = {
    "python314": _ansible_role_needs_python,
    "nginx": _ansible_role_needs_nginx,
}


def test_the_derivation_finds_something():
    """An empty derivation would make the rule below vacuous.

    Both probes are pinned against a role known to trip them, so a rename or a
    restructure fails loudly instead of quietly detecting nothing and reporting
    a clean run. `ai-stack` is named explicitly because the first version of the
    python probe missed it.
    """
    activating = _groups_activating_ansible_role()

    assert activating, "no role_*_active facts parsed - the guard is pinned to the wrong file"
    assert any(activating.values()), "no group references parsed out of the active facts"
    assert _ansible_role_needs_python("backend"), "the backend venv signal has moved"
    assert _ansible_role_needs_python("ai-stack"), (
        "ai-stack is no longer detected as building a venv - it names its task differently "
        "from backend, which is exactly the blind spot this probe was widened to close"
    )
    assert _ansible_role_needs_nginx("backend"), "the backend role's ungated nginx start is no longer detected"


def test_every_role_declares_what_its_group_actually_requires():
    """The #14446 invariant, over every shared dependency -- not just the first to fail.

    Joining a group switches on an ansible role. Whatever that role requires
    unconditionally, the node needs, regardless of what the node's own declared
    roles are called. Fixing only the interpreter would have left the identical
    hole one task later, at `nginx -t`.
    """
    sources = _activation_sources()

    # group -> {dependency: ansible role imposing it}, and the same by node role
    group_requires: dict = {}
    role_requires: dict = {}
    for ansible_role, activated_by in sources.items():
        for dependency, probe in _DEPENDENCY_PROBES.items():
            if not probe(ansible_role):
                continue
            for group in activated_by["groups"]:
                group_requires.setdefault(group, {})[dependency] = ansible_role
            for node_role in activated_by["roles"]:
                role_requires.setdefault(node_role, {})[dependency] = ansible_role

    offenders = []
    for role, group in ROLE_ANSIBLE_GROUPS.items():
        declared = ROLE_DEPENDENCIES.get(role, [])
        for dependency, via in group_requires.get(group, {}).items():
            if dependency not in declared:
                offenders.append(f"{role!r} joins group {group!r} (runs {via!r}) but does not declare {dependency!r}")

    # The node-roles half: a role that activates itself by name, with no group
    # involved at all.
    for role, required in role_requires.items():
        if role not in ROLE_DEPENDENCIES:
            continue
        declared = ROLE_DEPENDENCIES[role]
        for dependency, via in required.items():
            if dependency not in declared:
                offenders.append(f"{role!r} activates {via!r} by name but does not declare {dependency!r}")

    assert not offenders, (
        "role(s) mapped into a group whose ansible role requires a dependency they do not declare - "
        "Phase 0 skips it and provisioning fails once Phase 4a needs it (#14446): " + "; ".join(offenders)
    )


@pytest.mark.parametrize("role", ["vnc", "celery", "scheduler"])
@pytest.mark.parametrize("dependency", ["python314", "nginx"])
def test_the_backend_group_roles_declare_both(role, dependency):
    """The observed regression and its two silent siblings, pinned by name.

    `vnc` is what failed in the field. `celery` and `scheduler` share the same
    group and carried the identical undeclared gap -- never exercised only
    because such nodes are normally co-located with a real backend node.

    The derived rule above would keep passing if the derivation broke in a way
    that found nothing; this names the cases.
    """
    assert dependency in ROLE_DEPENDENCIES[role], (
        f"{role} does not declare {dependency}, but joins the backend group and runs the backend "
        f"ansible role, which requires it unconditionally (#14446)"
    )
