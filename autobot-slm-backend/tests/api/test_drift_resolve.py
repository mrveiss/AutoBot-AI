# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for POST /api/code-sync/drift/resolve (#7149, #7224, #9982).

Calls the route handler directly with mocked rsync + dir helpers so we
don't need a running app, DB, or actual filesystem operations.
"""

from __future__ import annotations

import asyncio

# Add autobot-slm-backend to path so api.code_sync imports resolve.
import sys
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from api.code_sync import resolve_drift  # noqa: E402
from models.schemas import DriftResolveRequest  # noqa: E402

# Stub user — endpoint only checks authentication via Depends(get_current_user)
_FAKE_USER = {"username": "tester", "is_admin": True}


def _run(coro):
    """Helper to run async route handlers synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


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
    """Patch _run_post_sync_steps to do nothing (deps_changed=False, no steps)."""
    return patch(
        "api.code_sync._run_post_sync_steps",
        side_effect=lambda comp, src, dep: _async_return((False, [])),
    )


def _async_return(value):
    """Build an awaitable that resolves to the given value."""

    async def _awaitable():
        return value

    return _awaitable()


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
        return_value=_async_return((True, "")),
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
        return_value=_async_return((False, "local rsync failed: permission denied")),
    )
    post_sync_calls: List[str] = []

    async def spy_post_sync(comp, src, dep):
        post_sync_calls.append(comp)
        return False, []

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
    """rsync receives the per-component exclude list from _SLM_COMPONENTS."""
    src_patch, dep_patch = _setup_dir_mocks()
    captured_excludes: List[List[str]] = []

    async def fake_rsync(src, comp, excludes):
        captured_excludes.append(excludes)
        return True, ""

    rsync_patch = patch("api.code_sync._rsync_component_local", side_effect=fake_rsync)
    with src_patch, dep_patch, rsync_patch, _noop_post_sync():
        req = DriftResolveRequest(component="autobot-slm-backend")
        _run(resolve_drift(req, stub_user))

    assert len(captured_excludes) == 1
    excludes = captured_excludes[0]
    # autobot-slm-backend's excludes from _SLM_COMPONENTS should include venv
    assert "venv" in excludes
    assert "__pycache__" in excludes


# =============================================================================
# Post-sync steps tests (#9982)
# =============================================================================


def test_happy_path_includes_post_steps(stub_user):
    """Successful rsync → response includes deps_changed and post_steps (#9982)."""
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch(
        "api.code_sync._rsync_component_local",
        return_value=_async_return((True, "")),
    )
    post_patch = patch(
        "api.code_sync._run_post_sync_steps",
        side_effect=lambda comp, src, dep: _async_return(
            (True, ["pip: install succeeded", "restart autobot-slm-backend: ok"])
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
        return_value=_async_return((True, "")),
    )
    captured: List[tuple] = []

    async def spy(comp, src, dep):
        captured.append((comp, src, dep))
        return False, []

    post_patch = patch("api.code_sync._run_post_sync_steps", side_effect=spy)
    with src_patch, dep_patch, rsync_patch, post_patch:
        req = DriftResolveRequest(component=component)
        _run(resolve_drift(req, stub_user))

    assert len(captured) == 1
    assert captured[0][0] == component
    assert component in captured[0][1]  # source_dir contains component name
    assert component in captured[0][2]  # deployed_dir contains component name


def test_python_backend_post_steps(stub_user):
    """autobot-backend resolve triggers pip install + service restart (#9982)."""
    from api.code_sync import _run_post_sync_steps

    pip_calls: List[str] = []
    restart_calls: List[str] = []
    frontend_calls: List[str] = []

    async def fake_pip(comp, steps):
        pip_calls.append(comp)
        steps.append("pip: install succeeded")

    async def fake_restart(comp, steps):
        restart_calls.append(comp)
        steps.append("restart autobot-backend: ok")

    async def fake_frontend(comp, steps):
        frontend_calls.append(comp)

    deps_patch = patch("api.code_sync._compute_deps_changed", return_value=_async_return(True))
    pip_patch = patch("api.code_sync._install_pip_deps_for_component", side_effect=fake_pip)
    restart_patch = patch("api.code_sync._restart_component_services", side_effect=fake_restart)
    frontend_patch = patch("api.code_sync._build_npm_frontend_for_component", side_effect=fake_frontend)

    with deps_patch, pip_patch, restart_patch, frontend_patch:
        deps_changed, steps = _run(
            _run_post_sync_steps(
                "autobot-backend",
                "/opt/autobot/code_source/autobot-backend",
                "/opt/autobot/autobot-backend",
            )
        )

    assert deps_changed is True
    assert pip_calls == ["autobot-backend"]
    assert restart_calls == ["autobot-backend"]
    assert frontend_calls == [], "npm build must not be called for a Python backend"
    assert any("pip" in s for s in steps)


def test_frontend_post_steps(stub_user):
    """autobot-frontend resolve triggers npm build + nginx restart — no pip (#9982)."""
    from api.code_sync import _run_post_sync_steps

    pip_calls: List[str] = []
    frontend_calls: List[str] = []
    restart_calls: List[str] = []

    async def fake_pip(comp, steps):
        pip_calls.append(comp)

    async def fake_frontend(comp, steps):
        frontend_calls.append(comp)
        steps.append("npm build: succeeded")

    async def fake_restart(comp, steps):
        restart_calls.append(comp)
        steps.append("restart nginx: ok")

    deps_patch = patch("api.code_sync._compute_deps_changed", return_value=_async_return(False))
    pip_patch = patch("api.code_sync._install_pip_deps_for_component", side_effect=fake_pip)
    frontend_patch = patch("api.code_sync._build_npm_frontend_for_component", side_effect=fake_frontend)
    restart_patch = patch("api.code_sync._restart_component_services", side_effect=fake_restart)

    with deps_patch, pip_patch, frontend_patch, restart_patch:
        deps_changed, steps = _run(
            _run_post_sync_steps(
                "autobot-frontend",
                "/opt/autobot/code_source/autobot-frontend",
                "/opt/autobot/autobot-frontend",
            )
        )

    assert deps_changed is False
    assert pip_calls == [], "pip install must not run for a frontend component"
    assert frontend_calls == ["autobot-frontend"]
    assert restart_calls == ["autobot-frontend"]
    assert any("npm" in s for s in steps)


def test_shared_lib_post_steps_noop():
    """autobot_shared resolve runs no service or build steps (#9982)."""
    from api.code_sync import _run_post_sync_steps

    deps_patch = patch("api.code_sync._compute_deps_changed", return_value=_async_return(False))
    with deps_patch:
        deps_changed, steps = _run(
            _run_post_sync_steps(
                "autobot_shared",
                "/opt/autobot/code_source/autobot_shared",
                "/opt/autobot/autobot_shared",
            )
        )

    assert deps_changed is False
    assert any("no service" in s for s in steps)


def _run_async_return(value):
    """Backward-compat alias for _async_return."""
    return _async_return(value)
