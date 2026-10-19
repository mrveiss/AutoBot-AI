# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared error boundaries reach the backend only through hooks (#18554)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import autobot_shared.error_boundaries as shared
import utils.error_boundaries as shim
from autobot_shared.error_boundaries.boundary_manager import ErrorBoundaryManager
from autobot_shared.error_boundaries.hooks import get_cancel_scope_provider
from utils import cancel_tokens

_REPO = Path(__file__).resolve().parents[3]


def test_the_shim_reexports_the_same_objects():
    names = [n for n in shared.__all__ if n != "register_backend_hooks"]
    assert names, "the shared package exports nothing"
    for name in names:
        assert getattr(shim, name) is getattr(shared, name), name


def test_registration_is_idempotent():
    shim.register_backend_hooks()
    first = get_cancel_scope_provider()
    shim.register_backend_hooks()
    shim.register_backend_hooks()
    assert get_cancel_scope_provider() is first is cancel_tokens


def test_bounded_signals_the_backend_cancel_scope_on_timeout():
    shim.register_backend_hooks()

    @shared.bounded(0.05, operation="hang")
    async def handler():
        await asyncio.sleep(5)

    with patch.object(cancel_tokens, "signal_cancel_scope") as signalled:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(handler())
    assert exc.value.status_code == 504
    signalled.assert_called_once()


def test_errors_are_recorded_through_the_backend_metric_function():
    shim.register_backend_hooks()
    manager = ErrorBoundaryManager()
    context = shared.ErrorContext(component="c", function="f")
    with patch("utils.error_metrics.record_error_metric", new=AsyncMock()) as record:
        with pytest.raises(Exception):
            asyncio.run(manager.handle_error(RuntimeError("boom"), context))
    assert record.await_count == 1
    assert record.await_args.kwargs["component"] == "c"


def test_an_unregistered_host_still_times_out_and_drops_metrics():
    """A fresh interpreter with only the repo root on the path: no backend, no hooks."""
    code = textwrap.dedent("""
        import asyncio, sys
        from fastapi import HTTPException
        from autobot_shared.error_boundaries import bounded, ErrorBoundaryManager, ErrorContext

        assert not any(m == "utils" or m.startswith("utils.") for m in sys.modules)

        @bounded(0.05, operation="hang")
        async def handler():
            await asyncio.sleep(5)

        try:
            asyncio.run(handler())
        except HTTPException as exc:
            assert exc.status_code == 504
        else:
            raise SystemExit("bounded did not time out")

        ctx = ErrorContext(component="c", function="f")
        try:
            asyncio.run(ErrorBoundaryManager().handle_error(RuntimeError("x"), ctx))
        except Exception:
            pass
        assert not any(m == "utils" or m.startswith("utils.") for m in sys.modules)
        print("ok")
        """)
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO),
        env={"PYTHONPATH": str(_REPO), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("ok"), done.stderr[-800:]
