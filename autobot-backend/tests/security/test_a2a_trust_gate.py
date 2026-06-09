# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for GH#8743 / MVA-1249.

Before the fix in api/a2a.py, callers that omitted X-A2A-Agent-Id bypassed
all capability checks entirely.  The fix adds a mandatory header check:
missing header → 401 Unauthorized before any trust evaluation fires.

Import note: a2a.task_manager creates a TaskManager singleton at module
level (Redis-backed).  We pre-stub it in sys.modules before any import of
the a2a package to prevent socket connections during test collection.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pre-stub a2a.task_manager so the a2a package can be imported without
# triggering the module-level TaskManager() Redis initialisation.
# ---------------------------------------------------------------------------

if "a2a.task_manager" not in sys.modules:
    _tm_stub = types.ModuleType("a2a.task_manager")
    _tm_stub.__path__ = []  # type: ignore[attr-defined]
    _tm_stub.TaskManager = MagicMock  # type: ignore[attr-defined]
    _tm_stub.get_task_manager = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    _tm_stub.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
    sys.modules["a2a.task_manager"] = _tm_stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTrustCapabilityGateMissingHeader:
    """GH#8743 regression: missing X-A2A-Agent-Id must be default-denied."""

    @pytest.mark.asyncio
    async def test_missing_agent_id_returns_401(self):
        """No X-A2A-Agent-Id header → 401 before any trust check runs."""
        from unittest.mock import AsyncMock, patch

        from fastapi import HTTPException

        from api.a2a import submit_task
        from api.schemas_agent import TaskSendRequest

        body = TaskSendRequest(message="do something", context=None)
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        background_tasks = MagicMock()

        with patch("api.a2a._a2a_limiter") as mock_limiter, patch("api.a2a.get_trust_manager") as mock_trust:
            mock_limiter.check_or_429 = AsyncMock()
            with pytest.raises(HTTPException) as exc_info:
                await submit_task(
                    body=body,
                    background_tasks=background_tasks,
                    request=request,
                    x_a2a_agent_id=None,
                    authorization=None,
                )

        assert exc_info.value.status_code == 401
        assert "X-A2A-Agent-Id" in exc_info.value.detail
        # Trust manager must never be consulted for anonymous callers.
        mock_trust.assert_not_called()

    @pytest.mark.asyncio
    async def test_untrusted_peer_returns_403(self):
        """An identified but UNTRUSTED peer must be denied with 403."""
        from unittest.mock import AsyncMock, patch

        from fastapi import HTTPException

        from a2a.trust_score import Capability, TrustAccessDenied, TrustLevel
        from api.a2a import submit_task
        from api.schemas_agent import TaskSendRequest

        body = TaskSendRequest(message="do something", context=None)
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.2"
        background_tasks = MagicMock()

        mock_mgr = MagicMock()
        mock_mgr.require_capability.side_effect = TrustAccessDenied(
            "untrusted-peer", Capability.SUBMIT_TASKS, TrustLevel.UNTRUSTED
        )

        with patch("api.a2a._a2a_limiter") as mock_limiter, patch("api.a2a.get_trust_manager", return_value=mock_mgr):
            mock_limiter.check_or_429 = AsyncMock()
            with pytest.raises(HTTPException) as exc_info:
                await submit_task(
                    body=body,
                    background_tasks=background_tasks,
                    request=request,
                    x_a2a_agent_id="untrusted-peer",
                    authorization=None,
                )

        assert exc_info.value.status_code == 403
        mock_mgr.require_capability.assert_called_once_with("untrusted-peer", Capability.SUBMIT_TASKS)
