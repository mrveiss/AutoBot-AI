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

## #15738 and #16276, landed

Until these landed, six ``users`` routes (``_GATED_BY_15738``) and nine
``teams`` routes observed as ``_AUTHENTICATED``: logged in, but with no admin
or ownership gate. That was a confirmed privilege-escalation path. The gates
were added in the routes themselves, and the table below changed as a
consequence, which is the order the guardrail here always asked for.
``/teams/my-teams`` alone stays login-only, because it returns only the
caller's own teams.
"""

from __future__ import annotations

from api.user_management.dependencies import get_current_user, require_platform_admin, require_self_or_admin
from api.user_management.password_change import authorize_password_change
from api.user_management.router import router as user_management_router
from autobot_shared.api_routing.router_routes import effective_routes

_OPEN = "open"
_AUTHENTICATED = "authenticated"
_ADMIN = "admin"
#: Authenticated, and additionally gated on being the target OR a platform admin.
#: A conditional posture the flat tiers above cannot express: change-password is
#: reachable by any authenticated caller but only ACTS for self or an admin (#15743),
#: and reading or updating a user follows the same rule (#15738).
_SELF_OR_ADMIN = "self-or-admin"

#: #15738's six routes and the gate its decision chose for each. Creating,
#: deleting and re-roling an account is admin-only, matching the SLM backend's
#: ADMIN_USERS_WRITE on the same capability. Reading or updating one account
#: is self-or-admin, the #15743 shape.
_GATED_BY_15738 = {
    ("POST", "/user-management/users"): _ADMIN,  # create_user
    ("GET", "/user-management/users/{user_id}"): _SELF_OR_ADMIN,  # get_user
    ("PATCH", "/user-management/users/{user_id}"): _SELF_OR_ADMIN,  # update_user
    ("DELETE", "/user-management/users/{user_id}"): _ADMIN,  # delete_user
    ("POST", "/user-management/users/{user_id}/roles/{role_id}"): _ADMIN,  # assign_role
    ("DELETE", "/user-management/users/{user_id}/roles/{role_id}"): _ADMIN,  # revoke_role
}

#: The nine team routes #16276 found checking no role, now admin-only (owner
#: ruling 2026-09-11, matching the SLM backend's /api/autobot-teams).
_ADMIN_ONLY_BY_16276 = frozenset(
    {
        ("GET", "/user-management/teams"),
        ("POST", "/user-management/teams"),
        ("GET", "/user-management/teams/{team_id}"),
        ("PATCH", "/user-management/teams/{team_id}"),
        ("DELETE", "/user-management/teams/{team_id}"),
        ("GET", "/user-management/teams/{team_id}/members"),
        ("POST", "/user-management/teams/{team_id}/members/{user_id}"),
        ("DELETE", "/user-management/teams/{team_id}/members/{user_id}"),
        ("PATCH", "/user-management/teams/{team_id}/members/{user_id}"),
    }
)

#: Every route mounted under ``api.user_management.router:router``, and its
#: observed posture. A route missing here, or an entry here with no matching
#: route, both fail in ``TestUserManagementRoutePostureIsComplete``.
_EXPECTED_POSTURE = {
    ("GET", "/user-management/users"): _AUTHENTICATED,  # list_users
    # search_users_for_sharing: login and the caller's own org (#16279). It was open (#2072).
    ("GET", "/user-management/users/search"): _AUTHENTICATED,
    ("POST", "/user-management/users"): _ADMIN,  # create_user (#15738)
    ("GET", "/user-management/users/me"): _AUTHENTICATED,  # get_current_user_profile
    ("GET", "/user-management/users/{user_id}"): _SELF_OR_ADMIN,  # get_user (#15738)
    ("PATCH", "/user-management/users/{user_id}"): _SELF_OR_ADMIN,  # update_user (#15738)
    ("DELETE", "/user-management/users/{user_id}"): _ADMIN,  # delete_user (#15738)
    ("POST", "/user-management/users/{user_id}/activate"): _AUTHENTICATED,
    ("POST", "/user-management/users/{user_id}/deactivate"): _AUTHENTICATED,
    # #15743 closed: the gate is a declared dependency, so it is visible here.
    ("POST", "/user-management/users/{user_id}/change-password"): _SELF_OR_ADMIN,
    ("POST", "/user-management/users/{user_id}/roles/{role_id}"): _ADMIN,  # assign_role (#15738)
    ("DELETE", "/user-management/users/{user_id}/roles/{role_id}"): _ADMIN,  # revoke_role (#15738)
    ("PUT", "/user-management/users/{user_id}/role"): _ADMIN,  # set_user_role (#1801)
    ("GET", "/user-management/teams"): _ADMIN,  # #16276
    ("POST", "/user-management/teams"): _ADMIN,  # #16276
    ("GET", "/user-management/teams/{team_id}"): _ADMIN,  # #16276
    ("PATCH", "/user-management/teams/{team_id}"): _ADMIN,  # #16276
    ("DELETE", "/user-management/teams/{team_id}"): _ADMIN,  # #16276
    ("GET", "/user-management/teams/{team_id}/members"): _ADMIN,  # #16276
    ("POST", "/user-management/teams/{team_id}/members/{user_id}"): _ADMIN,  # #16276
    ("DELETE", "/user-management/teams/{team_id}/members/{user_id}"): _ADMIN,  # #16276
    ("PATCH", "/user-management/teams/{team_id}/members/{user_id}"): _ADMIN,  # #16276
    ("GET", "/user-management/teams/my-teams"): _AUTHENTICATED,  # the caller's own teams only (#16276)
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
    """open / authenticated / self-or-admin / admin, from one route's dependency names.

    ``_SELF_OR_ADMIN`` is checked BEFORE ``_ADMIN``: a self-or-admin gate reaches
    ``require_platform_admin`` on one of its branches, so testing for admin first
    would report the conditional gate as unconditionally admin-only and hide the
    self-service branch entirely.
    """
    if names & {authorize_password_change.__name__, require_self_or_admin.__name__}:
        return _SELF_OR_ADMIN
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

    def test_no_route_is_open(self):
        """Every user-management route requires at least a login. #16279 closed the last open one, ``/users/search``.

        This check can't pass vacuously: it reads the observed posture of every
        mounted route, and ``TestUserManagementRoutePostureIsComplete`` pins
        that set to the table.
        """
        posture = _observed_posture()
        assert posture, "no routes observed -- the check below would be vacuous"
        open_routes = sorted(key for key, tier in posture.items() if tier == _OPEN)
        assert not open_routes, f"open user-management routes: {open_routes}"
        assert _OPEN not in _EXPECTED_POSTURE.values(), "the table still records an _OPEN route"

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

    def test_self_or_admin_routes_carry_the_identity_gate(self):
        posture = _observed_posture()
        self_routes = [k for k, v in _EXPECTED_POSTURE.items() if v == _SELF_OR_ADMIN]
        assert self_routes, "table lists no _SELF_OR_ADMIN route -- the check below would be vacuous"
        for key in self_routes:
            assert posture.get(key) == _SELF_OR_ADMIN, f"{key}: expected self-or-admin, observed {posture.get(key)!r}"

    def test_the_15738_routes_carry_the_gate_its_decision_chose(self):
        """None of #15738's six routes may slide back to login-only."""
        posture = _observed_posture()
        assert len(_GATED_BY_15738) == 6, "the #15738 route set changed size -- re-read the issue"
        for key, tier in _GATED_BY_15738.items():
            assert _EXPECTED_POSTURE[key] == tier, f"{key}: the table disagrees with the #15738 decision"
            assert posture.get(key) == tier, f"{key}: expected {tier} (#15738), observed {posture.get(key)!r}"

    def test_the_16276_team_routes_are_admin_only(self):
        """Every team route but ``/my-teams`` is admin-only, and ``/my-teams`` stays reachable by login."""
        posture = _observed_posture()
        assert len(_ADMIN_ONLY_BY_16276) == 9, "the #16276 route set changed size -- re-read the issue"
        for key in sorted(_ADMIN_ONLY_BY_16276):
            assert posture.get(key) == _ADMIN, f"{key}: expected admin-only (#16276), observed {posture.get(key)!r}"
        my_teams = ("GET", "/user-management/teams/my-teams")
        assert posture.get(my_teams) == _AUTHENTICATED, f"{my_teams}: observed {posture.get(my_teams)!r}"


class _FakeDependant:
    """Minimal stand-in for FastAPI's ``Dependant``, for the classifier's unit tests.

    Only ``call`` and ``dependencies`` are read by ``_flatten_dependency_names``,
    so a real ``Dependant`` is unnecessary here -- and using a fake keeps these
    cases independent of FastAPI's internal shape.
    """

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

    def test_a_self_or_admin_gate_outranks_the_admin_name_it_contains(self):
        """The ordering case for ``_SELF_OR_ADMIN`` (#15743).

        ``authorize_password_change`` reaches ``require_platform_admin`` on its
        non-self branch, so both names appear on the route. Classifying admin
        first would report the route as unconditionally admin-only and erase
        the self-service branch -- a posture claim that is simply false, and
        one that would then "pass" for the wrong reason. The pair below pins
        both directions: together they are self-or-admin, admin alone is admin.
        """
        assert _classify({"authorize_password_change", "require_platform_admin", "get_current_user"}) == _SELF_OR_ADMIN
        assert _classify({"require_self_or_admin", "get_tenant_context", "get_current_user"}) == _SELF_OR_ADMIN
        assert _classify({"require_platform_admin", "get_current_user"}) == _ADMIN
