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
"""

from starlette.routing import Match

from api.user_management.router import router as user_management_router


def _first_route_for(method: str, path: str):
    """Return the route Starlette would dispatch *method* *path* to, or None."""
    scope = {"type": "http", "method": method, "path": path, "root_path": ""}
    for route in user_management_router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
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
