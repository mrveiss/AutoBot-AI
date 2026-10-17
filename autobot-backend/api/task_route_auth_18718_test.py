# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: task ``status/{task_id}`` and ``clear-stuck`` routes carry an auth gate (#18718).

Walks the real routers' ``.routes`` (``dependant.dependencies`` already merges
router-level and route-level dependencies). Explicit module list, no tree scan.
"""

import importlib
import re

import pytest
from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute

from auth_middleware import check_admin_permission, get_current_user

ROUTER_MODULES = [
    "api.analytics",
    "api.analytics_bug_prediction",
    "api.code_intelligence",
    "api.codebase_analytics.endpoints.dependencies",
    "api.codebase_analytics.endpoints.duplicates",
    "api.codebase_analytics.endpoints.import_tree",
    "api.codebase_analytics.endpoints.indexing",
    "api.codebase_analytics.endpoints.pattern_analysis",
]
_TASK_PATH = re.compile(r"/status/\{task_id\}$|/clear-stuck$")
_GATES = {get_current_user, check_admin_permission}


def _task_routes(router):
    return [r for r in router.routes if isinstance(r, APIRoute) and _TASK_PATH.search(r.path)]


def _is_gated(route) -> bool:
    return any(d.call in _GATES for d in route.dependant.dependencies)


def ungated_task_routes(router) -> list:
    """Return ``METHOD path`` of every status/clear-stuck route lacking a gate."""
    return [f"{sorted(r.methods)[0]} {r.path}" for r in _task_routes(router) if not _is_gated(r)]


def _ungated_paths(module):
    router = importlib.import_module(module).router
    assert _task_routes(router), f"{module}: no status/clear-stuck routes found (matcher drift?)"
    return {r.path for r in _task_routes(router) if not _is_gated(r)}


@pytest.mark.parametrize("module", ROUTER_MODULES)
def test_task_routes_are_gated(module):
    assert _ungated_paths(module) == set()


def test_clear_stuck_gates_are_admin():
    for module in ROUTER_MODULES:
        for r in _task_routes(importlib.import_module(module).router):
            calls = {d.call for d in r.dependant.dependencies}
            if r.path.endswith("/clear-stuck"):
                assert check_admin_permission in calls, f"{module} {r.path}"


def test_planted_control_ungated_route_is_flagged():
    fake = APIRouter()

    @fake.get("/x/status/{task_id}")
    async def _bare(task_id: str):
        return {}

    @fake.post("/x/tasks/clear-stuck", dependencies=[Depends(get_current_user)])
    async def _gated():
        return {}

    assert ungated_task_routes(fake) == ["GET /x/status/{task_id}"]
