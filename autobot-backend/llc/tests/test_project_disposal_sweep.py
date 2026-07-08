# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Beat sweep disposes only due + approved pending_disposal projects (#11129 P2)."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.project_disposal_sweep import _async_sweep


@pytest.mark.asyncio
async def test_sweep_disposes_due_projects():
    due = [SimpleNamespace(id=uuid.uuid4(), code_source_id=None, disposal_approval_id=None)]
    session = AsyncMock()
    scal = MagicMock()
    scal.scalars.return_value.all.return_value = due
    session.execute = AsyncMock(return_value=scal)
    session.commit = AsyncMock()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    with patch("llc.scheduler.project_disposal_sweep.get_async_session_factory", return_value=_Factory()), patch(
        "llc.scheduler.project_disposal_sweep.dispose", AsyncMock()
    ) as disp, patch(
        "llc.scheduler.project_disposal_sweep._is_disposal_allowed", AsyncMock(return_value=True)
    ):
        count = await _async_sweep()
    assert count == 1
    disp.assert_awaited_once()
