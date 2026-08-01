# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for POST /api/code-sync/drift/resolve (#7149, #7224, #9982).

Calls the route handler directly with mocked rsync + dir helpers so we
don't need a running app, DB, or actual filesystem operations.

Real-load prologue (#11798, pattern: tests/services/code_version_test.py):
the root conftest stubs ``models.schemas`` / ``services.drift_checker`` as
MagicMocks, so the shared in-sweep ``api.code_sync`` module holds a
MagicMock ``DriftResolveRequest``/``DriftResolveResponse`` and an
empty-iterating ``ALLOWED_COMPONENTS`` — every request 400s with
"Must be one of: []" and no response field is assertable.  This module
instead swaps in the REAL sqlalchemy/models/drift modules, execs a PRIVATE
copy of api/code_sync.py against them, restores the stubs, and pins that
private module into ``sys.modules["api.code_sync"]`` per-test (autouse
fixture) so the existing ``patch("api.code_sync.…")`` targets resolve to it.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util

# Add autobot-slm-backend to path so api.code_sync imports resolve.
import sys
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_BACKEND_ROOT), str(_BACKEND_ROOT.parent)):  # + repo root (autobot_shared)
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
    """Exec *path* under canonical *name* (registered so relative imports work)."""
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
    # services.git_tracker stays the conftest stub — drift_checker only reads
    # DEFAULT_REPO_PATH from it, and the dir helpers are patched per-test.
    _real_dc = _load_real_module("services.drift_checker", _BACKEND_ROOT / "services" / "drift_checker.py")

    # Private exec of api/code_sync.py against the REAL modules above (all its
    # other services.* imports resolve to the root-conftest stubs, as designed).
    _cs_spec = importlib.util.spec_from_file_location("_code_sync_drift_test", _BACKEND_ROOT / "api" / "code_sync.py")
    _CS = importlib.util.module_from_spec(_cs_spec)  # type: ignore[arg-type]
    _cs_spec.loader.exec_module(_CS)  # type: ignore[union-attr]

    DriftResolveRequest = _real_schemas.DriftResolveRequest
    resolve_drift = _CS.resolve_drift
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
    # #9780: mock.patch resolves the target via getattr on the PARENT package,
    # so the parent attribute must point at the same module as sys.modules.
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


# Stub user — endpoint only checks authentication via Depends(get_current_user)
_FAKE_USER = {"username": "tester", "is_admin": True}


def _run(coro):
    """Helper to run async route handlers synchronously in tests."""
    # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
    # running before any async test on its worker had no current loop for get_event_loop().
    return asyncio.run(coro)


@pytest.fixture
def stub_user():
    return _FAKE_USER


def _setup_dir_mocks(component="autobot-slm-backend"):
    """Patch the dir-resolution helpers and return source/deployed paths."""
    return (
        patch(
            "api.code_sync.get_default_source_dir",
            return_value=f"/opt/autobot/code_source/{component}",
        ),
        patch(
            "api.code_sync.get_default_deployed_dir",
            return_value=f"/opt/autobot/{component}",
        ),
    )


def _noop_post_sync():
    """Patch _run_post_sync_steps to do nothing (deps_changed=False, no steps).

    The patch targets are real coroutine functions now (#11798), so patch()
    selects AsyncMock — plain values / sync side_effects become the awaited
    result (the old ``_async_return`` coroutine wrapper would double-wrap).
    """
    return patch(
        "api.code_sync._run_post_sync_steps",
        side_effect=lambda comp, src, dep: (False, [], True),
    )


def test_invalid_component_raises_400(stub_user):
    """ALLOWED_COMPONENTS guard rejects path-traversal attempts (#3427)."""
    req = DriftResolveRequest(component="../../etc/passwd")
    with pytest.raises(HTTPException) as exc_info:
        _run(resolve_drift(req, stub_user))
    assert exc_info.value.status_code == 400
    assert "Invalid component" in exc_info.value.detail


def test_unknown_component_raises_400(stub_user):
    """Component name outside ALLOWED_COMPONENTS gets 400, not silent rsync."""
    req = DriftResolveRequest(component="autobot-nonexistent")
    with pytest.raises(HTTPException) as exc_info:
        _run(resolve_drift(req, stub_user))
    assert exc_info.value.status_code == 400


def test_happy_path_returns_success(stub_user):
    """Valid component + successful rsync → success=True with paths populated."""
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch(
        "api.code_sync._rsync_component_local",
        return_value=(True, ""),
    )
    with src_patch, dep_patch, rsync_patch, _noop_post_sync():
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))
    assert resp.success is True
    assert resp.component == "autobot-slm-backend"
    assert resp.source_dir == "/opt/autobot/code_source/autobot-slm-backend"
    assert resp.deployed_dir == "/opt/autobot/autobot-slm-backend"
    assert "Resynced" in resp.message


def test_rsync_failure_returns_success_false(stub_user):
    """rsync failure → success=False with the rsync error message surfaced.

    _run_post_sync_steps must NOT be called when rsync fails (#9982).
    """
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch(
        "api.code_sync._rsync_component_local",
        return_value=(False, "local rsync failed: permission denied"),
    )
    post_sync_calls: List[str] = []

    async def spy_post_sync(comp, src, dep):
        post_sync_calls.append(comp)
        return False, [], True

    post_patch = patch("api.code_sync._run_post_sync_steps", side_effect=spy_post_sync)
    with src_patch, dep_patch, rsync_patch, post_patch:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))
    assert resp.success is False
    assert "permission denied" in resp.message
    assert post_sync_calls == [], "_run_post_sync_steps must not be called on rsync failure"


def test_source_dir_value_error_raises_500(stub_user):
    """get_default_source_dir raising ValueError → 500."""
    src_patch = patch(
        "api.code_sync.get_default_source_dir",
        side_effect=ValueError("misconfigured component path"),
    )
    with src_patch:
        req = DriftResolveRequest(component="autobot-slm-backend")
        with pytest.raises(HTTPException) as exc_info:
            _run(resolve_drift(req, stub_user))
    assert exc_info.value.status_code == 500


def test_excludes_for_known_component(stub_user):
    """rsync receives the per-component exclude list from _SLM_COMPONENTS.

    #11798: since #11459 standard artifacts (venv, __pycache__, …) are merged
    universally at the rsync chokepoint (_rsync_exclude_args), so the handler
    passes only the component-specific list.  Assert both halves of that
    contract instead of the pre-#11459 combined list.

    #11611: resolving a Python backend now rsyncs autobot_shared FIRST (shared-
    first ordering) and then the component — two rsync calls. The component call
    (the last one) still carries its _SLM_COMPONENTS exclude list.
    """
    src_patch, dep_patch = _setup_dir_mocks()
    captured: List[tuple] = []

    async def fake_rsync(src, comp, excludes, *, source_dir=None, dest_dir=None):
        captured.append((comp, excludes))
        return True, ""

    rsync_patch = patch("api.code_sync._rsync_component_local", side_effect=fake_rsync)
    with src_patch, dep_patch, rsync_patch, _noop_post_sync():
        req = DriftResolveRequest(component="autobot-slm-backend")
        _run(resolve_drift(req, stub_user))

    # #11611: autobot_shared is synced ahead of the backend.
    assert len(captured) == 2
    assert captured[0][0] == "autobot_shared"
    assert captured[1][0] == "autobot-slm-backend"
    # The handler passes exactly the component's _SLM_COMPONENTS entry …
    excludes = captured[1][1]
    expected = {comp: excl for comp, excl in _CS._SLM_COMPONENTS}["autobot-slm-backend"]
    assert excludes == expected
    # … and the rsync chokepoint injects the canonical artifact excludes.
    chokepoint_args = _CS._rsync_exclude_args(excludes)
    assert "--exclude=venv" in chokepoint_args
    assert "--exclude=__pycache__" in chokepoint_args


def test_shared_sync_failure_fails_resolve_and_skips_component_rsync(stub_user):
    """#11611 fail-safe: a failed autobot_shared sync fails the resolve BEFORE the
    component rsync — the component is NOT rsynced/restarted onto a stale shared tree.
    """
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_mock = AsyncMock(return_value=(True, ""))
    shared_patch = patch(
        "api.code_sync._ensure_autobot_shared_synced",
        AsyncMock(return_value=(False, "autobot_shared-first: resync failed")),
    )
    rsync_patch = patch("api.code_sync._rsync_component_local", rsync_mock)
    with src_patch, dep_patch, shared_patch, rsync_patch, _noop_post_sync():
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))

    assert resp.success is False
    assert "autobot_shared" in resp.message
    # Fail-safe: the component's own rsync must NOT run after a shared-sync failure.
    rsync_mock.assert_not_called()


# =============================================================================
# Post-sync steps tests (#9982)
# =============================================================================


def test_happy_path_includes_post_steps(stub_user):
    """Successful rsync → response includes deps_changed and post_steps (#9982)."""
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch(
        "api.code_sync._rsync_component_local",
        return_value=(True, ""),
    )
    post_patch = patch(
        "api.code_sync._run_post_sync_steps",
        side_effect=lambda comp, src, dep: (
            True,
            ["pip: install succeeded", "restart autobot-slm-backend: ok"],
            True,
        ),
    )
    with src_patch, dep_patch, rsync_patch, post_patch:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))
    assert resp.success is True
    assert resp.deps_changed is True
    assert "pip: install succeeded" in resp.post_steps
    assert any("restart" in s for s in resp.post_steps)


def test_post_sync_called_with_correct_args(stub_user):
    """_run_post_sync_steps receives the component, source_dir and deployed_dir (#9982)."""
    component = "autobot-backend"
    src_patch, dep_patch = _setup_dir_mocks(component)
    rsync_patch = patch(
        "api.code_sync._rsync_component_local",
        return_value=(True, ""),
    )
    captured: List[tuple] = []

    async def spy(comp, src, dep):
        captured.append((comp, src, dep))
        return False, [], True

    post_patch = patch("api.code_sync._run_post_sync_steps", side_effect=spy)
    with src_patch, dep_patch, rsync_patch, post_patch:
        req = DriftResolveRequest(component=component)
        _run(resolve_drift(req, stub_user))

    assert len(captured) == 1
    assert captured[0][0] == component
    assert component in captured[0][1]  # source_dir contains component name
    assert component in captured[0][2]  # deployed_dir contains component name


def test_python_backend_post_steps(stub_user):
    """autobot-backend resolve triggers pip install + service restart (#9982).

    #11798: _run_post_sync_steps grew snapshot/constraints/venv/alembic/health
    stages (#11322/#11323/#11377/#11378) and returns (deps_changed, steps,
    pip_ok) — every filesystem/service stage is patched so nothing real runs.
    """
    from api.code_sync import _run_post_sync_steps

    pip_calls: List[str] = []
    restart_calls: List[str] = []
    frontend_calls: List[str] = []

    async def fake_pip(comp, steps):
        pip_calls.append(comp)
        steps.append("pip: install succeeded")
        return True

    async def fake_restart(comp, steps):
        restart_calls.append(comp)
        steps.append("restart autobot-backend: ok")

    async def fake_frontend(comp, steps):
        frontend_calls.append(comp)
        return True

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", return_value=True))
        stack.enter_context(patch("api.code_sync._snapshot_component", return_value=None))
        stack.enter_context(patch("api.code_sync._deploy_constraints_dir"))
        stack.enter_context(patch("api.code_sync._deploy_repo_root_requirements"))
        stack.enter_context(patch("api.code_sync._ensure_target_python_installed"))
        stack.enter_context(patch("api.code_sync._ensure_venv_python", return_value=False))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", side_effect=fake_pip))
        stack.enter_context(patch("api.code_sync._run_alembic_migrations", return_value=True))
        stack.enter_context(patch("api.code_sync._ensure_autobot_shared_symlink"))
        stack.enter_context(patch("api.code_sync._restart_component_services", side_effect=fake_restart))
        stack.enter_context(patch("api.code_sync._wait_component_healthy", return_value=True))
        stack.enter_context(patch("api.code_sync._build_npm_frontend_for_component", side_effect=fake_frontend))
        deps_changed, steps, pip_ok = _run(
            _run_post_sync_steps(
                "autobot-backend",
                "/opt/autobot/code_source/autobot-backend",
                "/opt/autobot/autobot-backend",
            )
        )

    assert deps_changed is True
    assert pip_ok is True
    assert pip_calls == ["autobot-backend"]
    assert restart_calls == ["autobot-backend"]
    assert frontend_calls == [], "npm build must not be called for a Python backend"
    assert any("pip" in s for s in steps)


def test_frontend_post_steps(stub_user):
    """autobot-frontend resolve triggers npm build + nginx restart — no pip (#9982).

    #11798: patched for the snapshot/health stages and 3-tuple return (see
    test_python_backend_post_steps).
    """
    from api.code_sync import _run_post_sync_steps

    pip_calls: List[str] = []
    frontend_calls: List[str] = []
    restart_calls: List[str] = []

    async def fake_pip(comp, steps):
        pip_calls.append(comp)
        return True

    async def fake_frontend(comp, steps):
        frontend_calls.append(comp)
        steps.append("npm build: succeeded")
        return True

    async def fake_restart(comp, steps):
        restart_calls.append(comp)
        steps.append("restart nginx: ok")

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", return_value=False))
        stack.enter_context(patch("api.code_sync._snapshot_component", return_value=None))
        stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", side_effect=fake_pip))
        stack.enter_context(patch("api.code_sync._build_npm_frontend_for_component", side_effect=fake_frontend))
        stack.enter_context(patch("api.code_sync._restart_component_services", side_effect=fake_restart))
        stack.enter_context(patch("api.code_sync._wait_component_healthy", return_value=True))
        deps_changed, steps, pip_ok = _run(
            _run_post_sync_steps(
                "autobot-frontend",
                "/opt/autobot/code_source/autobot-frontend",
                "/opt/autobot/autobot-frontend",
            )
        )

    assert deps_changed is False
    assert pip_ok is True
    assert pip_calls == [], "pip install must not run for a frontend component"
    assert frontend_calls == ["autobot-frontend"]
    assert restart_calls == ["autobot-frontend"]
    assert any("npm" in s for s in steps)


def test_shared_lib_post_steps():
    """autobot_shared resolve runs no pip/npm step but restarts dependents.

    #11798: the original "noop" premise rotted — since #10248/#11496 the
    shared lib restores both backends' symlinks and restarts every dependent
    service with a health gate.  Assert the current contract instead.
    """
    from api.code_sync import _run_post_sync_steps

    symlink_calls: List[str] = []

    async def fake_symlink(comp, steps):
        symlink_calls.append(comp)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._compute_deps_changed", return_value=False))
        stack.enter_context(patch("api.code_sync._snapshot_component", return_value=None))
        stack.enter_context(patch("api.code_sync._ensure_autobot_shared_symlink", side_effect=fake_symlink))
        restart_dep = stack.enter_context(patch("api.code_sync._restart_dependents_with_health", return_value=True))
        deps_changed, steps, pip_ok = _run(
            _run_post_sync_steps(
                "autobot_shared",
                "/opt/autobot/code_source/autobot_shared",
                "/opt/autobot/autobot_shared",
            )
        )

    assert deps_changed is False
    assert pip_ok is True
    assert len(symlink_calls) == 2, "both backends' symlinks must be restored"
    restart_dep.assert_awaited_once()
    assert not any("pip:" in s or "npm" in s for s in steps)


def test_autobot_shared_is_syncable_and_restarts_dependents():
    """#10248: autobot_shared is a first-class syncable component whose resolve
    restarts every dependent service (so component code can't outrun the lib)."""
    from api.code_sync import _COMPONENT_SERVICES
    from services.drift_checker import ALLOWED_COMPONENTS

    assert "autobot_shared" in ALLOWED_COMPONENTS
    deps = _COMPONENT_SERVICES.get("autobot_shared", [])
    # Must restart the core Python services that import autobot_shared.
    assert "autobot-backend" in deps
    assert "autobot-slm-backend" in deps
    assert len(deps) >= 2
