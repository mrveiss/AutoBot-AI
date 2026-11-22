# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every marketplace route is authenticated; mutating routes are admin-gated (#17266).

Walks the real router's dependency graph, so a route added later without a
guard fails here.
"""

import pytest
from fastapi.routing import APIRoute

from api.marketplace import router
from auth_middleware import check_admin_permission, get_current_user

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _calls(dependant) -> set:
    found = set()
    for sub in dependant.dependencies:
        found.add(sub.call)
        found |= _calls(sub)
    return found


_ROUTES = [r for r in router.routes if isinstance(r, APIRoute)]


def _id(route: APIRoute) -> str:
    return f"{sorted(route.methods)} {route.path}"


def test_router_has_routes():
    assert _ROUTES, "marketplace router exposes no routes; the inventory below would be vacuous"


@pytest.mark.parametrize("route", _ROUTES, ids=_id)
def test_route_requires_authentication(route):
    calls = _calls(route.dependant)
    assert get_current_user in calls or check_admin_permission in calls, _id(route)


@pytest.mark.parametrize("route", [r for r in _ROUTES if r.methods & _MUTATING], ids=_id)
def test_mutating_route_requires_admin(route):
    assert check_admin_permission in _calls(route.dependant), _id(route)
