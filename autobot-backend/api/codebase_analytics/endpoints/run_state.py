# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run-state endpoint: did the newest indexing run finish? (#21003).

The one place a reader asks whether the stored findings come from a run that
was interrupted.  Mount point: /api/analytics/codebase (via router.py).
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling

from ..indexing_executor import _SUBPROCESS_HARD_TIMEOUT
from ..run_status import describe_run_state

router = APIRouter()


@router.get("/index/run-state")
@bounded(60.0)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_index_run_state",
    error_code_prefix="CODEBASE",
)
async def get_index_run_state(source_id: str | None = None):
    """Return the newest run's terminal status and the last completed run.

    ``partial`` is true when the newest run did not complete: the findings in
    storage may be from an interrupted run and must be shown labelled.
    A run left ``running`` past its hard timeout is reported ``abandoned``.
    """
    state = await describe_run_state(source_id, _SUBPROCESS_HARD_TIMEOUT)
    return JSONResponse({"status": "success", "run": state})
