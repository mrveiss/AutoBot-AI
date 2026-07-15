# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for fleet-health logic (#11360).

Covers:
- _classify_fleet_health: online node with all roles assigned -> healthy
- _classify_fleet_health: genuinely-down required role -> critical
- _classify_fleet_health: all required up, some optional down -> degraded
- _get_active_role_names: ONLINE self-managed node's Node.roles counted as active
- _get_active_role_names: OFFLINE self-managed node's roles are NOT counted
- _get_active_role_names: no self-managed nodes -> only one DB query
- _sync_slm_node_roles: inserts active rows for detected roles, not-installed for others
- _sync_slm_node_roles: upgrades existing not_installed row to active for detected roles
"""

import importlib.util as _ilu
import sys
import types
from pathlib import Path as _Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Load only the pure helper functions we need directly, avoiding Pydantic
# model class construction which fails on Python 3.10 with MagicMock stubs.
# ---------------------------------------------------------------------------


def _make_role(name: str, required: bool) -> types.SimpleNamespace:
    return types.SimpleNamespace(name=name, required=required)


def _load_helpers_from_roles():
    """Load _classify_fleet_health and _get_active_role_names from api/roles.py."""
    import importlib.util
    from pathlib import Path

    import pydantic

    roles_py = Path(__file__).parent.parent.parent / "api" / "roles.py"

    # Minimal RoleStatus enum stub matching what the functions use
    class _RoleStatus:
        class _Val:
            def __init__(self, v):
                self.value = v

        ACTIVE = _Val("active")

    for mod_name in [
        "asyncio",
        "logging",
        "re",
        "typing",
        "fastapi",
        "pydantic",
        "sqlalchemy",
        "sqlalchemy.ext",
        "sqlalchemy.ext.asyncio",
        "typing_extensions",
        "models",
        "models.database",
        "services",
        "services.auth",
        "services.database",
        "services.role_registry",
    ]:
        sys.modules.setdefault(mod_name, MagicMock())

    sys.modules["models.database"].RoleStatus = _RoleStatus
    sys.modules["models.database"].Node = MagicMock()
    sys.modules["models.database"].NodeRole = MagicMock()
    sys.modules["models.database"].Role = MagicMock()
    sys.modules["models.database"].SyncType = MagicMock()

    # Use real pydantic so Pydantic models validate properly
    sys.modules["pydantic"] = pydantic

    # Stub compose_fleet for the _get_active_role_names import
    compose_stub = MagicMock()
    compose_stub._SELF_MANAGED_NODE_IDS = set()
    sys.modules["services.compose_fleet"] = compose_stub

    spec = importlib.util.spec_from_file_location("_roles_fh_test", roles_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod._classify_fleet_health, mod._get_active_role_names


_classify_fleet_health, _get_active_role_names = _load_helpers_from_roles()


# ---------------------------------------------------------------------------
# _classify_fleet_health tests (pure function, no DB)
# ---------------------------------------------------------------------------


def test_all_required_active_is_healthy():
    roles = [_make_role("backend", True), _make_role("redis", True), _make_role("npu-worker", False)]
    result = _classify_fleet_health(roles, {"backend", "redis", "npu-worker"})
    assert result.health == "healthy"
    assert result.required_down == []
    assert result.optional_down == []


def test_required_role_missing_is_critical():
    roles = [_make_role("backend", True), _make_role("redis", True)]
    result = _classify_fleet_health(roles, {"backend"})  # redis missing
    assert result.health == "critical"
    assert "redis" in result.required_down
    assert result.optional_down == []


def test_optional_only_missing_is_degraded():
    roles = [_make_role("backend", True), _make_role("npu-worker", False)]
    result = _classify_fleet_health(roles, {"backend"})  # npu-worker missing
    assert result.health == "degraded"
    assert result.required_down == []
    assert "npu-worker" in result.optional_down


def test_all_roles_present_is_healthy():
    roles = [_make_role("backend", True), _make_role("npu-worker", False)]
    result = _classify_fleet_health(roles, {"backend", "npu-worker"})
    assert result.health == "healthy"


def test_no_roles_is_healthy():
    result = _classify_fleet_health([], set())
    assert result.health == "healthy"


# ---------------------------------------------------------------------------
# _get_active_role_names tests (async, uses mock DB session)
# ---------------------------------------------------------------------------


def _make_nr_result(role_names: list):
    """Mock DB execute result returning role_name scalars."""
    res = MagicMock()
    res.scalars.return_value.all.return_value = role_names
    return res


def _make_node_result(roles_lists: list):
    """Mock DB execute result returning (roles,) tuples for Node query."""
    res = MagicMock()
    res.all.return_value = [(r,) for r in roles_lists]
    return res


@pytest.mark.asyncio
async def test_online_self_managed_node_roles_count_as_active():
    """Roles in Node.roles for an ONLINE self-managed node are treated as active (#11360)."""
    sys.modules["services.compose_fleet"]._SELF_MANAGED_NODE_IDS = {"00-SLM-Manager"}

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_nr_result(["slm-backend"]),
            _make_node_result([["slm-backend", "backend", "redis", "postgres"]]),
        ]
    )

    active = await _get_active_role_names(db)
    assert "backend" in active
    assert "redis" in active
    assert "postgres" in active
    assert "slm-backend" in active


@pytest.mark.asyncio
async def test_offline_self_managed_node_roles_not_counted():
    """Roles on an OFFLINE self-managed node must not count as active."""
    sys.modules["services.compose_fleet"]._SELF_MANAGED_NODE_IDS = {"00-SLM-Manager"}

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_nr_result([]),
            _make_node_result([]),  # WHERE status=="online" returns nothing
        ]
    )

    active = await _get_active_role_names(db)
    assert active == set()


@pytest.mark.asyncio
async def test_no_self_managed_nodes_skips_node_query():
    """When _SELF_MANAGED_NODE_IDS is empty, no second DB query is issued."""
    sys.modules["services.compose_fleet"]._SELF_MANAGED_NODE_IDS = set()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_nr_result(["backend"]))

    active = await _get_active_role_names(db)
    assert "backend" in active
    assert db.execute.call_count == 1  # only one query; Node query skipped


@pytest.mark.asyncio
async def test_non_self_managed_node_requires_active_noderole_row():
    """Roles on regular VM nodes only count when NodeRole.status == active."""
    sys.modules["services.compose_fleet"]._SELF_MANAGED_NODE_IDS = {"00-SLM-Manager"}

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_nr_result(["backend"]),  # only backend is ACTIVE in NodeRole table
            _make_node_result([]),  # self-managed online node has no roles
        ]
    )

    active = await _get_active_role_names(db)
    assert "backend" in active
    assert "redis" not in active  # redis has no active NodeRole row


# ---------------------------------------------------------------------------
# _sync_slm_node_roles tests (services/node_seeder.py)
# ---------------------------------------------------------------------------


def _load_sync_fn():
    """Load sync_slm_node_roles from services/node_seeder.py with DB stubs."""
    seeder_py = _Path(__file__).parent.parent.parent / "services" / "node_seeder.py"

    class _RoleStatus:
        ACTIVE = types.SimpleNamespace(value="active")
        NOT_INSTALLED = types.SimpleNamespace(value="not_installed")

    # NodeRole must expose class-level column attributes (node_id, role_name)
    # as MagicMock so sqlalchemy select(...).where(NodeRole.node_id == x) chains work.
    _NodeRoleMeta = MagicMock()
    _NodeRoleMeta.node_id = MagicMock()
    _NodeRoleMeta.role_name = MagicMock()

    class _FakeNodeRole:
        node_id = _NodeRoleMeta.node_id
        role_name = _NodeRoleMeta.role_name

        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    models_db = MagicMock()
    models_db.RoleStatus = _RoleStatus
    models_db.NodeRole = _FakeNodeRole

    stubs: dict = {
        "sqlalchemy": MagicMock(),
        "sqlalchemy.ext": MagicMock(),
        "sqlalchemy.ext.asyncio": MagicMock(),
        "models": MagicMock(),
        "models.database": models_db,
    }
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)

    spec = _ilu.spec_from_file_location("_node_seeder_ut", seeder_py)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v

    return mod.sync_slm_node_roles, _FakeNodeRole, _RoleStatus


_sync_slm_node_roles, _FakeNodeRole, _FakeRoleStatus = _load_sync_fn()


@pytest.mark.asyncio
async def test_sync_inserts_active_for_detected_and_not_installed_for_others():
    """Detected roles get status=active; undetected assigned roles get not_installed."""
    added: list = []
    session = AsyncMock()
    session.add = lambda obj: added.append(obj)

    nr_result = MagicMock()
    nr_result.scalars.return_value.all.return_value = []  # no existing NodeRole rows
    session.execute = AsyncMock(return_value=nr_result)

    await _sync_slm_node_roles(session, "00-SLM-Manager", ["slm-backend", "backend"], ["slm-backend"])

    assert len(added) == 2
    by_name = {obj.role_name: obj for obj in added}
    assert by_name["slm-backend"].status == "active"
    assert by_name["backend"].status == "not_installed"


@pytest.mark.asyncio
async def test_sync_upgrades_not_installed_to_active_for_detected():
    """Existing not_installed row is upgraded to active when role is now detected."""
    existing_row = _FakeNodeRole(role_name="slm-backend", status="not_installed")

    session = AsyncMock()
    session.add = MagicMock()
    nr_result = MagicMock()
    nr_result.scalars.return_value.all.return_value = [existing_row]
    session.execute = AsyncMock(return_value=nr_result)

    await _sync_slm_node_roles(session, "00-SLM-Manager", ["slm-backend"], ["slm-backend"])

    assert existing_row.status == "active"
    session.add.assert_not_called()  # no new insert; existing row was updated


@pytest.mark.asyncio
async def test_sync_does_not_downgrade_active_to_not_installed():
    """Already-active row for undetected role is left unchanged (no downgrade)."""
    existing_row = _FakeNodeRole(role_name="backend", status="active")

    session = AsyncMock()
    session.add = MagicMock()
    nr_result = MagicMock()
    nr_result.scalars.return_value.all.return_value = [existing_row]
    session.execute = AsyncMock(return_value=nr_result)

    # backend not in detected_roles — sync should leave the active row intact
    await _sync_slm_node_roles(session, "00-SLM-Manager", ["backend"], [])

    assert existing_row.status == "active"
    session.add.assert_not_called()
