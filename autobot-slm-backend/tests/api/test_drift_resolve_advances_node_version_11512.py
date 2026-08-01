# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #11512: node code_version marker stays stale while the
node runs the latest code, because drift-resolve/component-resync + restart
never advanced ``Node.code_version`` (only a completed Ansible self-update
did).

Covers the new ``_advance_node_version_if_fully_synced`` helper:
  - Advances the node marker when a fresh, forced stale-components scan
    shows nothing stale (the node is genuinely fully current).
  - Does NOT advance when a sibling component is still stale — a single
    component resolving clean must not falsely mark a partially-stale node
    current (the safer variant called for by the issue).
  - Does NOT advance when the local SLM node cannot be resolved.
  - Never raises — a failure here must not turn an otherwise-successful
    resolve into a reported failure.
  - ``_get_local_slm_node_id`` resolves via IP match against
    ``settings.external_url`` (the same pattern used by /self-update).

And the two call sites that were the actual root cause:
  - POST /drift/resolve (``resolve_drift``): advances on success, not on
    rsync/pip failure.
  - The async job (``_run_component_resolve_job``): advances AFTER the
    deferred restart, not on rsync failure.

Real-load prologue mirrors tests/api/test_drift_resolve.py: the root
conftest stubs ``models.schemas`` / ``services.drift_checker`` as
MagicMocks, so this module swaps in the REAL sqlalchemy/models/drift
modules, execs a PRIVATE copy of api/code_sync.py against them, restores
the stubs, and pins that private module into ``sys.modules["api.code_sync"]``
per-test so ``patch("api.code_sync.…")`` targets resolve to it.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_BACKEND_ROOT), str(_BACKEND_ROOT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SWAP_KEYS = (
    "models.database",
    "models.schemas",
    "services.deploy_artifacts",
    "services.drift_checker",
)


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
for _name in list(_orig_modules):
    del sys.modules[_name]
try:
    for _name in ("sqlalchemy", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"):
        importlib.import_module(_name)

    _load_real_module("models.database", _BACKEND_ROOT / "models" / "database.py")
    _real_schemas = _load_real_module("models.schemas", _BACKEND_ROOT / "models" / "schemas.py")
    _load_real_module("services.deploy_artifacts", _BACKEND_ROOT / "services" / "deploy_artifacts.py")
    _real_dc = _load_real_module("services.drift_checker", _BACKEND_ROOT / "services" / "drift_checker.py")

    _cs_spec = importlib.util.spec_from_file_location("_code_sync_advance_test", _BACKEND_ROOT / "api" / "code_sync.py")
    _CS = importlib.util.module_from_spec(_cs_spec)  # type: ignore[arg-type]
    _cs_spec.loader.exec_module(_CS)  # type: ignore[union-attr]

    DriftResolveRequest = _real_schemas.DriftResolveRequest
finally:
    for _name in [name for name in sys.modules if _is_swap_key(name)]:
        del sys.modules[_name]
    for _name, _mod in _orig_modules.items():
        sys.modules[_name] = _mod


@pytest.fixture(autouse=True)
def _pin_private_code_sync():
    """Resolve patch("api.code_sync.…") / in-test imports to the private module."""
    saved = {
        "api.code_sync": sys.modules.get("api.code_sync"),
        "services.drift_checker": sys.modules.get("services.drift_checker"),
    }
    sys.modules["api.code_sync"] = _CS
    sys.modules["services.drift_checker"] = _real_dc
    saved_attrs = {}
    for _parent, _child, _mod in (("api", "code_sync", _CS), ("services", "drift_checker", _real_dc)):
        _pkg = sys.modules.get(_parent)
        if _pkg is not None:
            saved_attrs[(_parent, _child)] = getattr(_pkg, _child, None)
            setattr(_pkg, _child, _mod)
    try:
        yield
    finally:
        for _k, _m in saved.items():
            if _m is None:
                sys.modules.pop(_k, None)
            else:
                sys.modules[_k] = _m
        for (_parent, _child), _prev_attr in saved_attrs.items():
            _pkg = sys.modules.get(_parent)
            if _pkg is None:
                continue
            if _prev_attr is None:
                with contextlib.suppress(AttributeError):
                    delattr(_pkg, _child)
            else:
                setattr(_pkg, _child, _prev_attr)


_FAKE_USER = {"username": "tester", "is_admin": True}


def _run(coro):
    # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
    # running before any async test on its worker had no current loop for get_event_loop().
    return asyncio.run(coro)


class _FakeJobRow:
    """Mutable stand-in for a ComponentSyncJob DB row."""

    def __init__(self):
        self.status = "running"
        self.success = None
        self.deps_changed = False
        self.post_steps = None
        self.message = None
        self.completed_at = None


def _make_db_service_mock(row):
    """db_service mock whose session().execute() always resolves to *row*."""
    db_service_mock = MagicMock()

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, _stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = row
            return result

        async def commit(self):
            pass

        def add(self, _obj):
            pass

    db_service_mock.session.return_value = _FakeSession()
    return db_service_mock


# ---------------------------------------------------------------------------
# _advance_node_version_if_fully_synced — guard logic
# ---------------------------------------------------------------------------


def test_advances_when_fully_synced():
    """stale=[] + node found -> _update_fleet_node_version IS called."""
    with (
        patch.object(_CS, "_compute_stale_components", AsyncMock(return_value=[])),
        patch.object(_CS, "_get_local_slm_node_id", AsyncMock(return_value="slm-node-1")),
        patch.object(_CS, "_update_fleet_node_version", AsyncMock()) as update_mock,
    ):
        _run(_CS._advance_node_version_if_fully_synced("autobot-slm-backend"))

    update_mock.assert_awaited_once_with("slm-node-1")


def test_does_not_advance_when_sibling_component_still_stale():
    """A single component resolving clean must NOT mark a partially-stale
    node current — the safer variant required by #11512 (a sibling component,
    e.g. autobot_shared, could still be drifted).
    """
    with (
        patch.object(_CS, "_compute_stale_components", AsyncMock(return_value=["autobot_shared"])),
        patch.object(_CS, "_get_local_slm_node_id", AsyncMock()) as node_id_mock,
        patch.object(_CS, "_update_fleet_node_version", AsyncMock()) as update_mock,
    ):
        _run(_CS._advance_node_version_if_fully_synced("autobot-slm-backend"))

    update_mock.assert_not_called()
    node_id_mock.assert_not_called()


def test_does_not_advance_when_local_node_not_found():
    """stale=[] but the local SLM node can't be resolved -> no advance, no crash."""
    with (
        patch.object(_CS, "_compute_stale_components", AsyncMock(return_value=[])),
        patch.object(_CS, "_get_local_slm_node_id", AsyncMock(return_value=None)),
        patch.object(_CS, "_update_fleet_node_version", AsyncMock()) as update_mock,
    ):
        _run(_CS._advance_node_version_if_fully_synced("autobot-slm-backend"))

    update_mock.assert_not_called()


def test_swallows_exceptions_without_propagating():
    """A failure inside the guard (DB hiccup, bad settings, ...) must never
    turn an otherwise-successful resolve into a reported failure.
    """
    with patch.object(_CS, "_compute_stale_components", AsyncMock(side_effect=RuntimeError("boom"))):
        _run(_CS._advance_node_version_if_fully_synced("autobot-slm-backend"))  # must not raise


# ---------------------------------------------------------------------------
# _get_local_slm_node_id — IP-match lookup (same pattern as /self-update)
# ---------------------------------------------------------------------------


def test_get_local_slm_node_id_resolves_via_ip_match():
    fake_node = MagicMock()
    fake_node.node_id = "slm-node-42"
    db_mock = _make_db_service_mock(fake_node)

    with patch.object(_CS, "settings") as mock_settings:
        mock_settings.external_url = "http://10.0.0.5:8000"
        with patch.dict(sys.modules, {"services.database": MagicMock(db_service=db_mock)}):
            node_id = _run(_CS._get_local_slm_node_id())

    assert node_id == "slm-node-42"


def test_get_local_slm_node_id_returns_none_without_external_url():
    with patch.object(_CS, "settings") as mock_settings:
        mock_settings.external_url = ""
        node_id = _run(_CS._get_local_slm_node_id())

    assert node_id is None


def test_get_local_slm_node_id_returns_none_when_node_not_found():
    db_mock = _make_db_service_mock(None)

    with patch.object(_CS, "settings") as mock_settings:
        mock_settings.external_url = "http://10.0.0.5:8000"
        with patch.dict(sys.modules, {"services.database": MagicMock(db_service=db_mock)}):
            node_id = _run(_CS._get_local_slm_node_id())

    assert node_id is None


# ---------------------------------------------------------------------------
# POST /drift/resolve wiring — resolve_drift advances on success only
# ---------------------------------------------------------------------------


def _setup_dir_mocks(component="autobot-slm-backend"):
    return (
        patch.object(_CS, "get_default_source_dir", return_value=f"/opt/autobot/code_source/{component}"),
        patch.object(_CS, "get_default_deployed_dir", return_value=f"/opt/autobot/{component}"),
    )


def test_resolve_drift_success_advances_node_version():
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch.object(_CS, "_rsync_component_local", AsyncMock(return_value=(True, "")))
    post_sync_patch = patch.object(
        _CS,
        "_run_post_sync_steps",
        AsyncMock(return_value=(False, [], True)),
    )
    advance_patch = patch.object(_CS, "_advance_node_version_if_fully_synced", AsyncMock())

    with src_patch, dep_patch, rsync_patch, post_sync_patch, advance_patch as advance_mock:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(_CS.resolve_drift(req, _FAKE_USER))

    assert resp.success is True
    advance_mock.assert_awaited_once_with("autobot-slm-backend")


def test_resolve_drift_pip_failure_does_not_advance_node_version():
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch.object(_CS, "_rsync_component_local", AsyncMock(return_value=(True, "")))
    post_sync_patch = patch.object(
        _CS,
        "_run_post_sync_steps",
        AsyncMock(return_value=(False, ["pip install: FAILED"], False)),
    )
    advance_patch = patch.object(_CS, "_advance_node_version_if_fully_synced", AsyncMock())

    with src_patch, dep_patch, rsync_patch, post_sync_patch, advance_patch as advance_mock:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(_CS.resolve_drift(req, _FAKE_USER))

    assert resp.success is False
    advance_mock.assert_not_called()


def test_resolve_drift_rsync_failure_does_not_advance_node_version():
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch.object(_CS, "_rsync_component_local", AsyncMock(return_value=(False, "rsync failed")))
    advance_patch = patch.object(_CS, "_advance_node_version_if_fully_synced", AsyncMock())

    with src_patch, dep_patch, rsync_patch, advance_patch as advance_mock:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(_CS.resolve_drift(req, _FAKE_USER))

    assert resp.success is False
    advance_mock.assert_not_called()


def test_invalid_component_never_advances():
    """Guard: request validation failure (400) happens before any advance call."""
    advance_patch = patch.object(_CS, "_advance_node_version_if_fully_synced", AsyncMock())
    with advance_patch as advance_mock:
        req = DriftResolveRequest(component="../../etc/passwd")
        with pytest.raises(HTTPException):
            _run(_CS.resolve_drift(req, _FAKE_USER))
    advance_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Async job wiring — _run_component_resolve_job advances AFTER the restart
# ---------------------------------------------------------------------------


def test_component_resolve_job_advances_after_restart():
    row = _FakeJobRow()
    db_mock = _make_db_service_mock(row)
    call_order: list[str] = []

    async def _fake_restart(component, steps):
        call_order.append("restarted")

    async def _fake_advance(component):
        call_order.append("advanced")

    with (
        patch.object(_CS, "get_default_source_dir", return_value="/src/autobot-slm-backend"),
        patch.object(_CS, "get_default_deployed_dir", return_value="/opt/autobot/autobot-slm-backend"),
        patch.object(_CS, "_rsync_component_local", AsyncMock(return_value=(True, ""))),
        patch.object(
            _CS,
            "_run_post_sync_steps",
            AsyncMock(return_value=(False, ["post-sync: restart deferred"], True)),
        ),
        patch.object(_CS, "_restart_component_services", side_effect=_fake_restart),
        patch.object(_CS, "_advance_node_version_if_fully_synced", side_effect=_fake_advance),
        patch.object(_CS, "_running_tasks", {}),
    ):
        with patch.dict(sys.modules, {"services.database": MagicMock(db_service=db_mock)}):
            _run(_CS._run_component_resolve_job("job-11512", "autobot-slm-backend"))

    assert call_order == ["restarted", "advanced"], f"expected restart before advance, got {call_order}"
    assert row.status == "completed"


def test_component_resolve_job_rsync_failure_does_not_advance():
    row = _FakeJobRow()
    db_mock = _make_db_service_mock(row)
    advance_mock = AsyncMock()

    with (
        patch.object(_CS, "get_default_source_dir", return_value="/src/autobot-slm-backend"),
        patch.object(_CS, "get_default_deployed_dir", return_value="/opt/autobot/autobot-slm-backend"),
        patch.object(_CS, "_rsync_component_local", AsyncMock(return_value=(False, "rsync boom"))),
        patch.object(_CS, "_advance_node_version_if_fully_synced", advance_mock),
        patch.object(_CS, "_running_tasks", {}),
    ):
        with patch.dict(sys.modules, {"services.database": MagicMock(db_service=db_mock)}):
            _run(_CS._run_component_resolve_job("job-11512-fail", "autobot-slm-backend"))

    assert row.status == "failed"
    advance_mock.assert_not_called()
