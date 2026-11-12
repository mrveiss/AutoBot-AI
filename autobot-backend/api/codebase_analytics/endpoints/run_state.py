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

from api.source_scope import SourceIdQuery, require_source_id
from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling

from ..run_status import run_response_fields

router = APIRouter()


@router.get("/index/run-state")
@bounded(60.0)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_index_run_state",
    error_code_prefix="CODEBASE",
)
async def get_index_run_state(source_id: SourceIdQuery):
    """Return how the source's newest indexing run ended and when the last complete one finished.

    ``run`` is ``null`` (and ``partial`` false) for a source with no recorded run.
    ``partial`` is true when the newest run did not complete: the findings in
    storage may be from an interrupted run and must be shown labelled.
    A run left ``running`` past its hard timeout is reported ``abandoned``.
    """
    fields = await run_response_fields(require_source_id(source_id, "run state"))
    return JSONResponse({"status": "success", "source_id": source_id, **fields})
