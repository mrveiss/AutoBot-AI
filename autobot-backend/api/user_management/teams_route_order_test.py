# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-order tests for ``GET /teams/my-teams`` (#16277).

``GET /teams/{team_id}`` used to be declared first. Starlette sends a request
to the first route whose path matches, and ``{team_id}`` matches the segment
``my-teams`` as well, so every ``/my-teams`` request became a failed
UUID parse (422) inside ``get_team``. This asks the router itself which route
a request reaches, which is the question the bug was about.

The router is walked through ``effective_routes`` rather than ``.routes``
(``repo_tests/router_routes_traversal_test.py``, #15093). On the FastAPI that
CI pins, ``include_router`` defers: the user-management router's ``.routes``
holds one wrapper per child router, so a ``.routes`` walk would match nothing.
``effective_routes`` descends into each child in place, so its order is
Starlette's dispatch order.
"""

from starlette.routing import Match

from api.user_management.router import router as user_management_router
from autobot_shared.api_routing.router_routes import effective_routes


def _first_route_for(method: str, path: str):
    """Return the route Starlette would dispatch *method* *path* to, or None.

    On the deferred shape a child route's own ``path`` lacks the including
    router's prefix, which ``effective_routes`` reports as ``known_prefix``.
    So each route is matched against the request path with that prefix
    removed. On the eager shape ``known_prefix`` is empty, and this reduces to
    matching the full path.
    """
    for mounted in effective_routes(user_management_router):
        if not path.startswith(mounted.known_prefix):
            continue
        scope = {"type": "http", "method": method, "path": path[len(mounted.known_prefix) :], "root_path": ""}
        match, _ = mounted.route.matches(scope)
        if match == Match.FULL:
            return mounted.route
    return None


def test_my_teams_reaches_get_my_teams():
    route = _first_route_for("GET", "/user-management/teams/my-teams")
    assert route is not None, "no route matched GET /user-management/teams/my-teams"
    assert route.endpoint.__name__ == "get_my_teams", f"shadowed by {route.endpoint.__name__} (#16277)"


def test_a_team_id_still_reaches_get_team():
    """The contrast case: moving ``/my-teams`` up must not take ``/{team_id}`` with it."""
    route = _first_route_for("GET", "/user-management/teams/00000000-0000-0000-0000-000000000001")
    assert route is not None, "no route matched GET /user-management/teams/{team_id}"
    assert route.endpoint.__name__ == "get_team", f"dispatched to {route.endpoint.__name__}"
