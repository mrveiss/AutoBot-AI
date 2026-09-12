# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-route authorization posture for ``/api/settings/*`` (#16278).

#16278 found nine core config routes that checked nothing. An anonymous
caller could read the full merged config and write it. Every router-level
sweep still counted the router as gated, because its rbac and update
sub-routes are. ``initialization/router_registry/core_router_auth_guard_test.py``
judges a router by whether ANY of its routes is gated, and its docstring says
a partly-open router needs a per-router posture test to catch the rest.

This is that test for the settings router, using the #15737 method from
``api/user_management/user_management_route_posture_test.py``: every mounted
route and its posture, read from the ``Dependant`` tree the application
resolves.

Gates are compared by identity, not ``__name__``. Under test,
``auth_middleware`` is a stub (``testkit/auth_middleware_stub.py``) whose
callables carry names like ``_check_admin_permission_stub``. The objects
imported here are the same ones the routes captured, whether stub or real.
"""

from api.settings import router as settings_router
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.api_routing.router_routes import effective_routes

_OPEN = "open"
_AUTHENTICATED = "authenticated"
_ADMIN = "admin"

#: The nine routes #16278 found open. They now live in ``api/settings_config.py``.
_CONFIG_ROUTES_16278 = frozenset(
    {
        ("GET", "/"),
        ("GET", "/settings"),
        ("POST", "/"),
        ("POST", "/settings"),
        ("GET", "/backend"),
        ("POST", "/backend"),
        ("GET", "/config"),
        ("POST", "/config"),
        ("POST", "/clear-cache"),
    }
)

#: Every route mounted on ``api.settings:router``, with its posture. A route
#: missing from this table, or an entry with no matching route, fails
#: ``TestSettingsRoutePostureIsComplete``.
_EXPECTED_POSTURE = {
    **{key: _ADMIN for key in _CONFIG_ROUTES_16278},
    ("POST", "/rbac/initialize"): _ADMIN,
    ("GET", "/rbac/status/{task_id}"): _ADMIN,
    ("GET", "/rbac/status"): _ADMIN,
    ("POST", "/updates/run"): _ADMIN,
    ("GET", "/updates/status/{task_id}"): _ADMIN,
    ("GET", "/updates/worker-status"): _ADMIN,
    ("POST", "/updates/check"): _ADMIN,
    ("GET", "/updates/status"): _ADMIN,
    ("POST", "/sync"): _ADMIN,
    ("PATCH", "/hardware-priority"): _ADMIN,
    # Deliberately open. Gating it behind login caused spurious 401s
    # (#10750 A13); see get_telemetry_settings in api/settings.py.
    ("GET", "/telemetry"): _OPEN,
    ("POST", "/telemetry"): _ADMIN,
    ("POST", "/telemetry/prompt-shown"): _AUTHENTICATED,
}


def _dependency_calls(dependant) -> list:
    """Every dependency callable reachable from *dependant*, at any depth.

    This is the same walk as ``core_router_auth_guard_test.py``'s
    ``_flatten_dependency_calls``. It is copied rather than imported, because
    importing that module would load its whole router sweep.
    ``check_admin_permission`` sits one hop down, inside
    ``require_settings_admin``, so a flat read of the route would miss it.
    """
    calls: list = []
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
                calls.append(call)
            stack.append(dep)
    return calls


def _classify(calls: list) -> str:
    """Return the route's tier, ``open`` / ``authenticated`` / ``admin``, from its dependency callables."""
    if any(call is check_admin_permission for call in calls):
        return _ADMIN
    if any(call is get_current_user for call in calls):
        return _AUTHENTICATED
    return _OPEN


def _observed_posture() -> dict[tuple[str, str], str]:
    """Map each mounted (method, path) to its observed posture, from a clean in-process import."""
    posture: dict[tuple[str, str], str] = {}
    for mounted in effective_routes(settings_router):
        tier = _classify(_dependency_calls(mounted.route.dependant))
        for method in mounted.methods - {"HEAD"}:
            posture[(method, mounted.path)] = tier
    return posture


class TestSettingsRoutePostureIsComplete:
    """Every route in the table exists, and no mounted route is missing from it."""

    def test_every_expected_route_is_mounted(self):
        missing = set(_EXPECTED_POSTURE) - set(_observed_posture())
        assert not missing, f"expected but not mounted: {sorted(missing)}"

    def test_no_mounted_route_is_missing_from_the_table(self):
        extra = set(_observed_posture()) - set(_EXPECTED_POSTURE)
        assert not extra, f"mounted but absent from the posture table: {sorted(extra)}"


class TestSettingsRoutePosture:
    """Each route's observed posture matches the one on record."""

    def test_every_route_observes_its_recorded_posture(self):
        observed = _observed_posture()
        wrong = {key: (tier, observed.get(key)) for key, tier in _EXPECTED_POSTURE.items() if observed.get(key) != tier}
        assert not wrong, f"(expected, observed) per route: {wrong}"

    def test_the_16278_config_routes_are_admin_gated(self):
        observed = _observed_posture()
        assert len(_CONFIG_ROUTES_16278) == 9, "the #16278 route set changed size -- re-read the issue"
        for key in sorted(_CONFIG_ROUTES_16278):
            assert observed.get(key) == _ADMIN, f"{key}: expected admin-gated (#16278), observed {observed.get(key)!r}"

    def test_the_only_open_route_is_the_documented_telemetry_read(self):
        open_routes = sorted(key for key, tier in _observed_posture().items() if tier == _OPEN)
        assert open_routes == [("GET", "/telemetry")], f"open settings routes: {open_routes}"


class _FakeDependant:
    """The two attributes ``_dependency_calls`` reads from FastAPI's ``Dependant``, and nothing else."""

    def __init__(self, call, dependencies=None):
        self.call = call
        self.dependencies = dependencies or []


def _unrelated_dependency():
    """A dependency that is neither a login nor an admin gate: the walker's null case."""
    return None


class TestClassifierContrastPair:
    """Proof that the classifier can tell the tiers apart, and that it reaches past the first hop."""

    def test_no_gate_classifies_as_open(self):
        assert _classify(_dependency_calls(_FakeDependant(call=_unrelated_dependency))) == _OPEN

    def test_login_alone_classifies_as_authenticated(self):
        route = _FakeDependant(call=_unrelated_dependency, dependencies=[_FakeDependant(call=get_current_user)])
        assert _classify(_dependency_calls(route)) == _AUTHENTICATED

    def test_an_admin_gate_two_hops_down_classifies_as_admin(self):
        """Mirrors the real shape: a route -> require_settings_admin -> check_admin_permission."""
        helper = _FakeDependant(call=_unrelated_dependency, dependencies=[_FakeDependant(call=check_admin_permission)])
        route = _FakeDependant(call=_unrelated_dependency, dependencies=[helper])
        assert _classify(_dependency_calls(route)) == _ADMIN
