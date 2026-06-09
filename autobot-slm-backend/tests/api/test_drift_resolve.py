# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for POST /api/code-sync/drift/resolve (#7149, #7224).

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


def _setup_dir_mocks():
    """Patch the dir-resolution helpers and return source/deployed paths."""
    return (
        patch("api.code_sync.get_default_source_dir", return_value="/opt/autobot/code_source/autobot-slm-backend"),
        patch("api.code_sync.get_default_deployed_dir", return_value="/opt/autobot/autobot-slm-backend"),
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
        return_value=_run_async_return((True, "")),
    )
    with src_patch, dep_patch, rsync_patch:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))
    assert resp.success is True
    assert resp.component == "autobot-slm-backend"
    assert resp.source_dir == "/opt/autobot/code_source/autobot-slm-backend"
    assert resp.deployed_dir == "/opt/autobot/autobot-slm-backend"
    assert "Resynced" in resp.message


def test_rsync_failure_returns_success_false(stub_user):
    """rsync failure → success=False with the rsync error message surfaced."""
    src_patch, dep_patch = _setup_dir_mocks()
    rsync_patch = patch(
        "api.code_sync._rsync_component_local",
        return_value=_run_async_return((False, "local rsync failed: permission denied")),
    )
    with src_patch, dep_patch, rsync_patch:
        req = DriftResolveRequest(component="autobot-slm-backend")
        resp = _run(resolve_drift(req, stub_user))
    assert resp.success is False
    assert "permission denied" in resp.message


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
    with src_patch, dep_patch, rsync_patch:
        req = DriftResolveRequest(component="autobot-slm-backend")
        _run(resolve_drift(req, stub_user))

    assert len(captured_excludes) == 1
    excludes = captured_excludes[0]
    # autobot-slm-backend's excludes from _SLM_COMPONENTS should include venv
    assert "venv" in excludes
    assert "__pycache__" in excludes


def _run_async_return(value):
    """Build an awaitable that resolves to the given value (for patch return_value).

    Required because _rsync_component_local is async — patch.return_value
    must itself be awaitable.
    """

    async def _awaitable():
        return value

    return _awaitable()
