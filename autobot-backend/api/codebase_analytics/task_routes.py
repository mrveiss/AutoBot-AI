# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One implementation of the background-task ``clear-stuck`` route (#18718).

Celery recovers stuck tasks itself, so every ``.../tasks/clear-stuck`` route is
the same no-op. It mutates task state in principle, so it requires admin
(``check_admin_permission``), matching ``analytics_bug_prediction``.

The route ``name`` is the OpenAPI ``operationId`` base, so each caller passes
its historical handler name to keep the generated API types unchanged.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling

CLEAR_STUCK_DESCRIPTION = "No-op: Celery handles stuck-task recovery automatically (GH#6505)."
_CLEARED = {"cleared_count": 0, "message": "Celery handles task recovery automatically"}


def add_clear_stuck_route(
    router: APIRouter,
    path: str,
    *,
    name: str,
    bounded_s: Optional[float] = None,
    error_prefix: Optional[str] = None,
    response_model: Optional[Any] = None,
    description: str = CLEAR_STUCK_DESCRIPTION,
) -> None:
    """Register ``POST path`` as the admin-gated clear-stuck no-op.

    Exactly one wrapper, as the per-file handlers had: ``bounded_s`` applies
    ``bounded(bounded_s)``; ``error_prefix`` applies ``with_error_handling`` with
    ``operation=name``.
    """
    if (bounded_s is None) == (error_prefix is None):
        raise ValueError("pass exactly one of bounded_s or error_prefix")
    if bounded_s is not None:
        wrap = bounded(bounded_s)
    else:
        wrap = with_error_handling(category=ErrorCategory.SERVER_ERROR, operation=name, error_code_prefix=error_prefix)

    async def clear_stuck(
        force: bool = Query(default=False, description="Force clear ALL running tasks"),
    ):
        return dict(_CLEARED)

    clear_stuck.__name__ = name
    router.add_api_route(
        path,
        wrap(clear_stuck),
        methods=["POST"],
        name=name,
        response_model=response_model,
        description=description,
        dependencies=[Depends(check_admin_permission)],
    )
