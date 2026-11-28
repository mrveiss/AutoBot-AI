# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19770: the stage wait tells the verdict whether the run is alive."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Through that module: its header prepares the imports `api.code_sync` needs under this package's conftest.
from test_fleet_node_update_11511 import (  # noqa: E402
    _AFTER_FIRING,
    _TARGET,
    _fired_job,
    _reconcile_self_update_stage,
    _run,
)


@pytest.mark.parametrize("alive", [False, None])
def test_the_stage_wait_tells_the_verdict_whether_the_run_is_alive(alive) -> None:
    """Without this a run that ended with no recap fails its stage as "state unknown"."""
    job = _fired_job()
    verdict = SimpleNamespace(degraded=True, failed_hosts=0, unreachable_hosts=0, reason="did not finish")
    read = MagicMock(return_value=verdict)
    with (
        patch("api.code_sync._await_self_update_completion", AsyncMock(return_value=_AFTER_FIRING)),
        patch("api.code_sync.read_deploy_activity", AsyncMock(return_value=SimpleNamespace(in_progress=alive))),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
        patch("api.code_sync._read_last_self_update_verdict", read),
    ):
        _run(_reconcile_self_update_stage(job, _TARGET, ["node-a"]))
    assert read.call_args.kwargs["run_alive"] is alive
