# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-route authorization posture for ``/api/user-management/*`` (#15737).

#15737's own finding was that the authorization posture of these routes is not
legible from the code: the route decorator names
``user_management_route_marker`` (formerly ``require_user_management_enabled``),
which performs no check at all, while the real gate --
``get_current_user`` -- sits two or three hops down a dependency chain
(``get_user_service``/``get_team_service``/``get_organization_service`` ->
``get_tenant_context`` -> ``get_current_user``). Reading the route decorator
alone answers the wrong question. This file answers the right one, from the
same place the application resolves it: the assembled ``Dependant`` tree.

## The #15738 guardrail

Six routes below (``_TRACKED_BY_15738``) observe as ``_AUTHENTICATED`` --
logged in, but with no admin or ownership gate. That is #15738's finding, a
confirmed privilege-escalation path, open and ``needs-decision``. Recording
their posture here is not certifying it: this suite asserts what the code
does today so a *silent* posture change fails loudly, not that the posture is
correct. Do not "fix" #15738 by editing this file's table -- add the gate in
the routes themselves and let the resulting posture change (to ``_ADMIN``)
update this file as a consequence, not a cause.
"""

from __future__ import annotations

from api.user_management.dependencies import get_current_user, require_platform_admin
from api.user_management.router import router as user_management_router
from autobot_shared.api_routing.router_routes import effective_routes

_OPEN = "open"
_AUTHENTICATED = "authenticated"
_ADMIN = "admin"

#: (method, path) pairs whose posture is #15738's confirmed finding: logged in,
#: no admin or ownership check. See the module docstring's guardrail.
_TRACKED_BY_15738 = frozenset(
    {
        ("POST", "/user-management/users"),  # create_user
        ("GET", "/user-management/users/{user_id}"),  # get_user
        ("PATCH", "/user-management/users/{user_id}"),  # update_user
        ("DELETE", "/user-management/users/{user_id}"),  # delete_user
        ("POST", "/user-management/users/{user_id}/roles/{role_id}"),  # assign_role
        ("DELETE", "/user-management/users/{user_id}/roles/{role_id}"),  # revoke_role
    }
)

#: Every route mounted under ``api.user_management.router:router``, and its
#: observed posture. A route missing here, or an entry here with no matching
#: route, both fail in ``TestUserManagementRoutePostureIsComplete``.
_EXPECTED_POSTURE = {
    ("GET", "/user-management/users"): _AUTHENTICATED,  # list_users
    ("GET", "/user-management/users/search"): _OPEN,  # search_users_for_sharing (#2072)
    ("POST", "/user-management/users"): _AUTHENTICATED,  # create_user
    ("GET", "/user-management/users/me"): _AUTHENTICATED,  # get_current_user_profile
    ("GET", "/user-management/users/{user_id}"): _AUTHENTICATED,  # get_user
    ("PATCH", "/user-management/users/{user_id}"): _AUTHENTICATED,  # update_user
    ("DELETE", "/user-management/users/{user_id}"): _AUTHENTICATED,  # delete_user
    ("POST", "/user-management/users/{user_id}/activate"): _AUTHENTICATED,
    ("POST", "/user-management/users/{user_id}/deactivate"): _AUTHENTICATED,
    ("POST", "/user-management/users/{user_id}/change-password"): _AUTHENTICATED,
    ("POST", "/user-management/users/{user_id}/roles/{role_id}"): _AUTHENTICATED,  # assign_role
    ("DELETE", "/user-management/users/{user_id}/roles/{role_id}"): _AUTHENTICATED,  # revoke_role
    ("PUT", "/user-management/users/{user_id}/role"): _ADMIN,  # set_user_role (#1801)
    ("GET", "/user-management/teams"): _AUTHENTICATED,
    ("POST", "/user-management/teams"): _AUTHENTICATED,
    ("GET", "/user-management/teams/{team_id}"): _AUTHENTICATED,
    ("PATCH", "/user-management/teams/{team_id}"): _AUTHENTICATED,
    ("DELETE", "/user-management/teams/{team_id}"): _AUTHENTICATED,
    ("GET", "/user-management/teams/{team_id}/members"): _AUTHENTICATED,
    ("POST", "/user-management/teams/{team_id}/members/{user_id}"): _AUTHENTICATED,
    ("DELETE", "/user-management/teams/{team_id}/members/{user_id}"): _AUTHENTICATED,
    ("PATCH", "/user-management/teams/{team_id}/members/{user_id}"): _AUTHENTICATED,
    ("GET", "/user-management/teams/my-teams"): _AUTHENTICATED,
    ("GET", "/user-management/organizations"): _ADMIN,
    ("POST", "/user-management/organizations"): _ADMIN,
    ("GET", "/user-management/organizations/{org_id}"): _AUTHENTICATED,
    ("GET", "/user-management/organizations/slug/{slug}"): _AUTHENTICATED,
    ("PATCH", "/user-management/organizations/{org_id}"): _ADMIN,
    ("DELETE", "/user-management/organizations/{org_id}"): _ADMIN,
    ("POST", "/user-management/organizations/{org_id}/deactivate"): _ADMIN,
    ("GET", "/user-management/organizations/{org_id}/stats"): _AUTHENTICATED,
}


def _flatten_dependency_names(dependant) -> set[str]:
    """Every dependency callable reachable from *dependant*, at any depth.

    ``dependant.dependencies`` is only one hop: ``get_current_user`` for these
    routes is reached through ``get_user_service``/``get_team_service``/
    ``get_organization_service`` -> ``get_tenant_context`` -> ``get_current_user``,
    so a flat read finds nothing and a route reads as unauthenticated when it
    is not -- the exact misreading #15737 documents ("traced four layers
    before resorting to a request"). This walks the full tree instead.
    """
    names: set[str] = set()
    stack = [dependant]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        for dep in getattr(node, "dependencies", None) or ():
            call = getattr(dep, "call", None)
            if call is not None:
                names.add(getattr(call, "__name__", "") or getattr(call, "__qualname__", ""))
            stack.append(dep)
    names.discard("")
    return names


def _classify(names: set[str]) -> str:
    """open / authenticated / admin, from the dependency names on one route."""
    if require_platform_admin.__name__ in names:
        return _ADMIN
    if get_current_user.__name__ in names:
        return _AUTHENTICATED
    return _OPEN


def _observed_posture() -> dict[tuple[str, str], str]:
    """(method, path) -> observed posture, from a clean in-process import.

    No subprocess is needed here (contrast
    ``api/terminal_router_dependency_wiring_test.py``, #15093): that isolation
    exists for an include-time ``dependencies=`` argument, which
    ``api/user_management/router.py`` never passes, and every dependency
    asserted below is declared at a route decorator or inside
    ``dependencies.py``'s own function signatures -- resolved into the static
    ``Dependant`` tree at import time, on every FastAPI shape this repo runs.
    """
    posture: dict[tuple[str, str], str] = {}
    for mounted in effective_routes(user_management_router):
        names = _flatten_dependency_names(mounted.route.dependant)
        tier = _classify(names)
        for method in mounted.methods - {"HEAD"}:
            posture[(method, mounted.path)] = tier
    return posture


class TestUserManagementRoutePostureIsComplete:
    """Every route this file's table describes exists, and nothing else does.

    A route dropped from the table without dropping its route, or added
    without a posture entry, is exactly the "discovered by probing" failure
    #15737 wants the suite -- not a prober -- to catch.
    """

    def test_every_expected_route_is_mounted(self):
        missing = set(_EXPECTED_POSTURE) - set(_observed_posture())
        assert not missing, f"expected but not mounted: {sorted(missing)}"

    def test_no_mounted_route_is_missing_from_the_table(self):
        extra = set(_observed_posture()) - set(_EXPECTED_POSTURE)
        assert not extra, f"mounted but absent from the posture table: {sorted(extra)}"


class TestUserManagementRoutePosture:
    """The observed posture of every route matches what is on record."""

    def test_open_routes_carry_no_login_requirement(self):
        posture = _observed_posture()
        open_routes = [k for k, v in _EXPECTED_POSTURE.items() if v == _OPEN]
        assert open_routes, "table lists no _OPEN route -- the check below would be vacuous"
        for key in open_routes:
            assert posture.get(key) == _OPEN, f"{key}: expected open, observed {posture.get(key)!r}"

    def test_admin_routes_require_platform_admin(self):
        posture = _observed_posture()
        admin_routes = [k for k, v in _EXPECTED_POSTURE.items() if v == _ADMIN]
        assert admin_routes, "table lists no _ADMIN route -- the check below would be vacuous"
        for key in admin_routes:
            assert posture.get(key) == _ADMIN, f"{key}: expected admin-gated, observed {posture.get(key)!r}"

    def test_authenticated_routes_require_login_but_no_admin_gate(self):
        posture = _observed_posture()
        auth_routes = [k for k, v in _EXPECTED_POSTURE.items() if v == _AUTHENTICATED]
        assert auth_routes, "table lists no _AUTHENTICATED route -- the check below would be vacuous"
        for key in auth_routes:
            assert (
                posture.get(key) == _AUTHENTICATED
            ), f"{key}: expected authenticated-only, observed {posture.get(key)!r}"

    def test_the_15738_tracked_routes_are_recorded_not_certified(self):
        """The six #15738 endpoints observe as authenticated-only today.

        This is a record of current behaviour, not a certification that it is
        correct: #15738 is the open, needs-decision finding that these six
        carry no admin or ownership gate at all. A future fix there (adding
        ``Depends(require_platform_admin)`` or a self-or-admin check) is
        expected to change these to ``_ADMIN`` and must update this file --
        that is #15738 landing, not a regression of this one.
        """
        posture = _observed_posture()
        assert _TRACKED_BY_15738, "the #15738 tracked-route set is empty"
        for key in _TRACKED_BY_15738:
            assert _EXPECTED_POSTURE[key] == _AUTHENTICATED, f"{key} must be on record as _AUTHENTICATED"
            assert posture.get(key) == _AUTHENTICATED, (
                f"{key}: expected the #15738-tracked posture (authenticated, no "
                f"admin gate) but observed {posture.get(key)!r} -- if a gate was "
                "added here, close #15738 with that change; do not edit this "
                "file to match a gate added elsewhere"
            )


class _FakeDependant:
    """Minimal stand-in for FastAPI's ``Dependant`` -- only what the walker reads."""

    def __init__(self, call, dependencies=None):
        self.call = call
        self.dependencies = dependencies or []


def _unrelated_dependency():
    """A dependency that is neither auth nor admin -- the walker's null case."""
    return None


class TestClassifyHelperContrastPair:
    """Unit-level proof the detector can tell tiers apart, independent of
    FastAPI's own ``Dependant`` shape -- and specifically that it descends
    more than one hop, since that is the exact bug shape #15737 documents.
    """

    def test_empty_tree_classifies_as_open(self):
        dependant = _FakeDependant(call=_unrelated_dependency, dependencies=[])
        assert _classify(_flatten_dependency_names(dependant)) == _OPEN

    def test_admin_dependency_one_hop_deep_classifies_as_admin(self):
        dependant = _FakeDependant(
            call=_unrelated_dependency,
            dependencies=[_FakeDependant(call=require_platform_admin)],
        )
        assert _classify(_flatten_dependency_names(dependant)) == _ADMIN

    def test_get_current_user_two_hops_deep_classifies_as_authenticated(self):
        """Mirrors the real shape: get_user_service -> get_tenant_context -> get_current_user."""
        inner = _FakeDependant(call=get_current_user)
        middle = _FakeDependant(call=_unrelated_dependency, dependencies=[inner])
        outer = _FakeDependant(call=_unrelated_dependency, dependencies=[middle])
        assert _classify(_flatten_dependency_names(outer)) == _AUTHENTICATED
