# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source-liveness reporting and sweeping (#17545).

#17538 orders the retention work detect -> measure -> build. This is where the
measurement is asked for:

- ``GET  /api/knowledge/source-liveness``       -- how many facts have lost their source
- ``POST /api/knowledge/source-liveness/sweep`` -- probe a page of locators

Admin-gated, because the sweep walks the fact table and touches every row it
probes, and because the census describes the whole knowledge base rather than
one user's facts.

There is no scheduler behind this yet, which is why ``source_checked_at`` exists
on the row: liveness is only as fresh as the last sweep somebody ran, and the
model says so rather than implying currency it does not have. The periodic half
belongs with #17548, where this subsystem already has a reconciler loop that
nothing starts -- hanging work on a task nothing starts is how an unwired
feature comes to read as working.
"""

from typing import Dict

from fastapi import APIRouter, Depends, Query

from api.feature_flags import require_admin
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.source_liveness import (
    DEFAULT_SWEEP_LIMIT,
    source_liveness_census,
    sweep_source_liveness,
)
from services.audit_logger import audit_log

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge/source-liveness", tags=["knowledge", "admin"])

#: Upper bound on one sweep request. A sweep orders by least-recently-probed, so
#: a bounded page called repeatedly walks the table; an unbounded one would hold
#: a write transaction open across it.
_MAX_SWEEP_LIMIT = 5000


@router.get("")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="source_liveness_census",
    error_code_prefix="SOURCE_LIVENESS",
)
async def get_source_liveness_census(_admin: Dict = Depends(require_admin)) -> Dict:
    """Per-ingest-class counts of every source state.

    ``never_checked`` and ``no_locator`` are their own buckets: *did not look*
    and *nothing to look at* are both different from *looked and found nothing*,
    and a retention decision made on a number that merged them would be acting
    on facts nobody has examined.
    """
    return {"success": True, "data": await source_liveness_census()}


@router.post("/sweep")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="source_liveness_sweep",
    error_code_prefix="SOURCE_LIVENESS",
)
async def post_source_liveness_sweep(
    limit: int = Query(DEFAULT_SWEEP_LIMIT, ge=1, le=_MAX_SWEEP_LIMIT),
    admin: Dict = Depends(require_admin),
) -> Dict:
    """Probe the least-recently-checked page of filesystem locators.

    Records an observation per fact. Deletes nothing and marks nothing gone --
    a witnessed deletion is the only thing that sets ``source_gone_at`` (#17546),
    and acting on a vanished source at all is an approval-gated decision (#17038).
    """
    result = await sweep_source_liveness(limit=limit)
    await audit_log(
        "knowledge.source_liveness.sweep",
        user_id=admin.get("username") or admin.get("id"),
        probed=result["probed"],
        outcomes=result["outcomes"],
        # What was probed and what was written can differ when two sweeps overlap
        # (#17615 review). An audit line carrying only `probed` would claim every
        # probe reached the row.
        superseded=result["superseded"],
    )
    return {"success": True, "data": result}
