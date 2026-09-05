# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The repeatable sweep #15745 asked for: every router `load_core_routers()`
mounts either carries a real auth dependency, or is a recorded exemption.

#15745's own sweep found this by hand: read `app_factory.py`, confirm no
`include_router(...)` call passes `dependencies=`, then read all 97 routers'
own files one at a time. That is not repeatable -- the ninety-eighth router a
future PR adds gets no such reading unless someone remembers to do it again.
This file is that reading, automated, so a router reaching
``load_core_routers()`` with no gate and no recorded exemption fails CI at
the point it is *added*, not at the next manual audit.

## Router-level, not route-level

#15737's own posture test (``api/user_management/user_management_route_posture_test.py``)
asserts the posture of every *route* inside one router, because that router's
individual routes disagree with each other (some open, some admin-only) and
that disagreement is the point being pinned. This guard answers a coarser,
repo-wide question instead: does *this router*, as a whole, contain at least
one route with a recognisable gate? A router that gates nine routes and
leaves a tenth open is a #15737-shaped defect (route-level), not a #15745-
shaped one (router-level) -- catching it needs a posture test like #15737's
for that specific router, which is a decision for whoever owns it, not
something this guard should silently paper over by getting stricter than the
finding it was asked to encode.

## What "recognisable gate" means here

Reused from #15737's own working example
(``_flatten_dependency_names``/``_classify`` in the posture test above):

1. **Walk the full ``Dependant`` tree**, not one hop -- ``autobot_shared.
   api_routing.router_routes.effective_routes`` for the router-to-route walk
   (the shared traversal #15093 already centralised, see that module's own
   docstring for why a one-hop or FastAPI-version-specific reader silently
   finds nothing on the deferred-inclusion shape), then a stack walk of
   ``route.dependant.dependencies`` for the dependency-to-dependency hop,
   because ``get_current_user`` sits two or three hops down a chain
   (``get_user_service`` -> ``get_tenant_context`` -> ``get_current_user``)
   on plenty of routes in this sweep, same as #15737's own finding.

2. **Compare callables by identity, not by ``__name__``.** ``auth_middleware``
   is globally stubbed for every backend test run
   (``conftest.py``'s module-level ``install_auth_middleware_stub()``), and
   that stub's real functions are named ``_get_current_user_stub`` /
   ``_check_admin_permission_stub`` -- neither string equals the production
   name they stand in for. A test that compared ``call.__name__ ==
   "get_current_user"`` would misclassify every router gated through
   ``auth_middleware`` the moment it ran under pytest (#15728's shape:
   passed locally against the real module, failed in CI against the stub).
   Importing the *same* name this module's own top-level import binds --
   whichever object ``auth_middleware.get_current_user`` currently is, stub
   or real -- and comparing by ``is`` sidesteps the mismatch entirely: the
   router file and this guard both resolve the one name FastAPI/Python
   currently has bound to it, in the same process, at the same time.

3. **Recognise a dependency *factory*'s product without a name string.**
   ``auth_rbac.require_permission(...)`` and ``auth_rbac.require_role(...)``
   both return a closure literally named ``dependency`` -- a fresh, distinct
   function object per call site, so no single import can stand in for "the"
   product the way (2) does for ``get_current_user``. Matched instead by
   ``__module__`` + the ``<locals>`` qualname the interpreter itself assigns,
   which identifies *which factory* produced this closure without relying on
   a name a mock could rewrite.

4. **Recognise gates that never reach the ``Dependant`` tree at all.**
   ``authenticate_websocket`` is called *inside* a WebSocket handler's body
   (``api/websockets.py:812``, ``api/live_events.py:396``), not through
   ``Depends(...)``, so no amount of ``Dependant``-tree walking sees it.
   ``api/files.py``, ``api/audit.py`` and ``api/service_messages.py`` do the
   analogous thing for HTTP routes: each defines its own local
   ``_check_file_permission`` / ``check_admin_permission`` / ``_check_admin``
   helper that calls ``get_auth_middleware()`` directly from inside the
   handler body and raises on failure, rather than being wired through
   ``Depends(...)``. Both shapes are caught the same way: read the route's
   own ``endpoint`` code object (unwrapped through any ``functools.wraps``
   decorator, e.g. ``with_error_handling``) for a direct reference to
   ``authenticate_websocket``, or -- one hop only, and only into a function
   defined in the *same module* as the endpoint, matching the actual pattern
   above -- for a reference to a helper whose own code references
   ``get_auth_middleware``/``get_user_from_request``. This is a structural
   reading of the real call graph, not a name guess: it is why ``files``
   (gated, via ``_check_file_permission``) and ``knowledge_cognition``
   (NOT gated -- see below) come out on opposite sides despite neither one
   using ``Depends(...)`` for its check.

## The exemption list is two different things, not one

``_INTENTIONALLY_OPEN``: documented in the file itself, the same shape as
``api/chat_embed.py:190``. ``jwks_auth`` (``api/jwks.py``) joins it here --
JWKS is meant to be publicly readable (RFC 7517) and the code already says so
in so many words; #15745's own sweep did not enumerate it, which this guard's
disagreement with that count reports rather than hides (see the module
docstring further down and the PR/report this guard shipped with).

``_TRACKED_BY_15745``: recorded, NOT certified -- the ten routers #15745
found with no gate and no documented reason. Same treatment #15737's posture
test gives its own tracked sets: a future fix adds ``Depends(...)`` (or an
equivalent gate) to the router itself and that removes the entry here as a
consequence of the fix landing, not a prerequisite edit to make this file
agree with a gate someone already added elsewhere.

``_TRACKED_BY_OTHER_ISSUES``: two more ungated routers this guard's own
construction surfaced, neither one part of #15745's ten and neither one the
same defect shape as those ten:

* ``knowledge_cognition`` -- #15759. ``api/knowledge_cognition.py``'s
  ``trigger_cognition_seed`` names ``_user=check_admin_permission`` with no
  ``Depends(...)``; the check is never invoked. Worse than an openly-absent
  gate, because it reads as present.
* ``transcriber`` -- #15758. #15745 rejected this one as "auth lives in
  nested sub-routers" (transcriber_router aggregates
  ``transcriber/routes/*.py``). Building this guard required tracing that
  claim rather than taking it on faith, and it does not hold: every
  transcriber route resolves its caller through
  ``getattr(request.state, "user", None)``, and nothing in production ever
  sets ``request.state.user`` for a transcriber request -- every caller
  resolves to the same ``DEFAULT_USER`` placeholder, unauthenticated.

A disagreement with #15745's own count is a finding this guard is supposed
to surface, not an error to paper over by force-fitting the exemption list
back to ten.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from api.user_management.dependencies import get_current_user as _um_get_current_user
from api.user_management.dependencies import require_platform_admin as _um_require_platform_admin
from auth_middleware import check_admin_permission as _amw_check_admin_permission
from auth_middleware import get_current_user as _amw_get_current_user
from autobot_shared.api_routing.router_routes import effective_routes
from initialization.router_registry.core_routers import load_core_routers

# Canonical, directly-imported gate callables. Compared by identity (2 in the
# module docstring), never by ``__name__`` -- see there for why.
_IDENTITY_GATES = (
    _amw_get_current_user,
    _amw_check_admin_permission,
    _um_get_current_user,
    _um_require_platform_admin,
)

# Modules whose ``require_permission``/``require_role`` return a per-call
# closure literally named ``dependency`` -- identified by factory, not by
# that shared inner name (3 in the module docstring).
_PERMISSION_FACTORY_MODULES = frozenset({"auth_rbac", "user_management.middleware.rbac_middleware"})
_PERMISSION_FACTORY_QUALNAME_PREFIXES = ("require_permission.<locals>", "require_role.<locals>")

# Low-level primitives a hand-rolled, in-body auth check calls before it
# raises -- the shape ``api/audit.py``, ``api/service_messages.py`` and
# ``api/files.py`` each use instead of ``Depends(...)`` (4 in the module
# docstring). Referencing one of these by name is what makes a helper an
# auth check rather than an unrelated ``Request``-taking function.
_AUTH_PRIMITIVE_NAMES = ("get_auth_middleware", "get_user_from_request")

_WEBSOCKET_AUTH_NAME = "authenticate_websocket"

# Documented, intentional, no fix pending -- see the module docstring.
_INTENTIONALLY_OPEN = {
    "chat_embed": "api/chat_embed.py:190 -- unauthenticated by design for embed contexts (GH#9047)",
    "jwks_auth": "api/jwks.py -- public key distribution (RFC 7517); documented unauthenticated by design",
}

# Recorded, not certified -- #15745's own ten. See the module docstring.
_TRACKED_BY_15745 = {
    "agent_org": "api/agent_org.py",
    "redis": "api/redis.py",
    "developer": "api/developer.py",
    "wake_word": "api/wake_word.py",
    "knowledge_sync": "services/knowledge_sync_service.py",
    "knowledge_suggestions": "api/knowledge_suggestions.py",
    "knowledge_search": "api/knowledge_search.py",
    "knowledge_search_aggregator": "api/knowledge_search_aggregator.py",
    "frontend_config": "api/frontend_config.py",
    "voice_stream": "api/voice_stream.py",
}

# Recorded, not certified -- found while building this guard, tracked by
# their own issues since neither is the same defect shape as #15745's ten.
# See the module docstring.
_TRACKED_BY_OTHER_ISSUES = {
    "knowledge_cognition": "#15759 -- admin check named but never Depends()-wired, so it never runs",
    "transcriber": "#15758 -- request.state.user is set nowhere in production; every caller is DEFAULT_USER",
}

_ALL_EXEMPTIONS = {**_INTENTIONALLY_OPEN, **_TRACKED_BY_15745, **_TRACKED_BY_OTHER_ISSUES}

# Bound to REACH (routers/routes actually enumerated), not to how many
# findings turn up -- a sweep that silently enumerates 3 routers instead of
# ~97 must fail even if all 3 happen to look gated. See the module docstring.
_MIN_EXPECTED_CORE_ROUTERS = 90
_MIN_EXPECTED_MOUNTED_ROUTES = 700


def _flatten_dependency_calls(dependant: Any) -> list[Callable]:
    """Every dependency callable reachable from *dependant*, at any depth.

    Mirrors ``user_management_route_posture_test.py``'s
    ``_flatten_dependency_names`` exactly, except it keeps the callable
    objects themselves rather than their ``__name__`` -- see (2) in the
    module docstring for why identity, not a name string, is what a caller
    here needs to compare against.
    """
    calls: list[Callable] = []
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


def _is_permission_factory_product(call: Any) -> bool:
    """True for a closure ``require_permission(...)``/``require_role(...)`` returned.

    See (3) in the module docstring: the closure is named ``dependency`` at
    every call site, so identity is unavailable and the ``<locals>``
    qualname the interpreter assigns is what actually distinguishes it.
    """
    module = getattr(call, "__module__", "") or ""
    qualname = getattr(call, "__qualname__", "") or ""
    return module in _PERMISSION_FACTORY_MODULES and qualname.startswith(_PERMISSION_FACTORY_QUALNAME_PREFIXES)


def _references_auth_primitive(call: Any) -> bool:
    """True if *call*'s own code references a low-level auth primitive.

    See (4) in the module docstring. A ``MagicMock`` has no ``__code__``, so
    this only ever matches a real function -- it cannot be fooled by a bare
    stub the way a ``__name__`` string comparison could.
    """
    code = getattr(call, "__code__", None)
    if code is None:
        return False
    return any(primitive in code.co_names for primitive in _AUTH_PRIMITIVE_NAMES)


def _dependant_tree_is_gated(dependant: Any) -> bool:
    """Does this route's assembled ``Dependant`` tree carry a recognised gate?"""
    calls = _flatten_dependency_calls(dependant)
    return any(
        (call in _IDENTITY_GATES) or _is_permission_factory_product(call) or _references_auth_primitive(call)
        for call in calls
    )


def _same_module_helper_is_gated(func: Any, code: Any) -> bool:
    """One hop into a same-module helper *func*'s own code references.

    Restricted to functions defined in the SAME module as *func* -- the
    actual shape every current case takes (``_check_file_permission``,
    ``check_admin_permission``, ``_check_admin``) -- rather than any global
    the endpoint happens to reference, so an unrelated helper that merely
    imports ``auth_middleware`` for some other reason cannot manufacture a
    false gate.
    """
    module_globals = getattr(func, "__globals__", {})
    own_module = getattr(func, "__module__", None)
    for referenced_name in code.co_names:
        candidate = module_globals.get(referenced_name)
        if (
            callable(candidate)
            and getattr(candidate, "__module__", None) == own_module
            and _references_auth_primitive(candidate)
        ):
            return True
    return False


def _endpoint_body_is_gated(endpoint: Any) -> bool:
    """Does the route's own handler body perform (rather than declare) a gate?

    Catches (4) in the module docstring: ``authenticate_websocket()`` called
    inline in a WebSocket handler, and a same-module private helper that
    itself references an auth primitive (see ``_same_module_helper_is_gated``).
    """
    try:
        func = inspect.unwrap(endpoint)
    except ValueError:
        func = endpoint
    code = getattr(func, "__code__", None)
    if code is None:
        return False
    if _WEBSOCKET_AUTH_NAME in code.co_names or any(p in code.co_names for p in _AUTH_PRIMITIVE_NAMES):
        return True
    return _same_module_helper_is_gated(func, code)


def _router_is_gated(router: Any) -> bool:
    """True if ANY route this router mounts carries a recognised gate.

    Router-level, not route-level -- see the module docstring for why a
    router with some open and some gated routes is a different, finer-
    grained finding this guard does not attempt to replace.
    """
    for mounted in effective_routes(router):
        if _dependant_tree_is_gated(mounted.route.dependant):
            return True
        if _endpoint_body_is_gated(getattr(mounted.route, "endpoint", None)):
            return True
    return False


def _ungated_core_router_names() -> set[str]:
    """Every ``load_core_routers()`` entry with no recognised gate anywhere in it."""
    return {name for router, _prefix, _tags, name in load_core_routers() if not _router_is_gated(router)}


class TestCoreRouterSweepIsNotVacuous:
    """A guard that silently enumerates nothing would report a clean sweep."""

    def test_load_core_routers_reach(self):
        core = load_core_routers()
        assert len(core) >= _MIN_EXPECTED_CORE_ROUTERS, (
            f"load_core_routers() returned {len(core)} routers, expected at least "
            f"{_MIN_EXPECTED_CORE_ROUTERS} -- this guard's findings are meaningless "
            "if the enumeration itself silently collapsed"
        )

    def test_mounted_route_reach(self):
        total_routes = sum(len(effective_routes(router)) for router, _p, _t, _n in load_core_routers())
        assert total_routes >= _MIN_EXPECTED_MOUNTED_ROUTES, (
            f"only {total_routes} routes were reachable from load_core_routers()'s "
            f"routers, expected at least {_MIN_EXPECTED_MOUNTED_ROUTES} -- a router "
            "returning zero routes would look 'gated' by having nothing to check"
        )


class TestCoreRouterAuthGuard:
    """Every router load_core_routers() mounts is gated, or a recorded exemption."""

    def test_every_ungated_router_is_a_recorded_exemption(self):
        ungated = _ungated_core_router_names()
        unrecorded = ungated - set(_ALL_EXEMPTIONS)
        assert not unrecorded, (
            f"{sorted(unrecorded)} reach load_core_routers() with no recognised auth "
            "dependency and no recorded exemption. Either add a gate to the router "
            "itself, or -- if it is genuinely intentional -- document it in the file "
            "the way api/chat_embed.py:190 does and add it to _INTENTIONALLY_OPEN "
            "here; do not add it to _TRACKED_BY_15745 (#15745), which is a closed "
            "record of that issue's own findings, not a place to file a new one"
        )

    def test_every_recorded_exemption_is_still_ungated(self):
        """A gate added to an exempted router must remove it from this file.

        Mirrors the posture test's own rule for its tracked sets: fixing the
        underlying router is what makes this row disappear, not editing this
        file to match a fix landed elsewhere.
        """
        ungated = _ungated_core_router_names()
        core_names = {name for _r, _p, _t, name in load_core_routers()}
        stale = set(_ALL_EXEMPTIONS) - ungated
        # A renamed/removed router falls out of core_names entirely -- that is
        # a different problem (rename the exemption key) from one that is
        # still a live router name but is no longer ungated (remove the entry).
        stale_and_live = stale & core_names
        assert not stale_and_live, (
            f"{sorted(stale_and_live)} are recorded as ungated exemptions but are "
            "no longer ungated -- a gate was added. Remove the entry from this "
            "file's exemption dict as a consequence of that fix; do not leave a "
            "stale record once the router it describes is actually protected"
        )


class _FakeDependant:
    """Minimal stand-in for FastAPI's ``Dependant`` -- only what the walker reads."""

    def __init__(self, call: Callable, dependencies: list["_FakeDependant"] | None = None):
        self.call = call
        self.dependencies = dependencies or []


def _open_endpoint() -> None:
    """An endpoint with no auth reference anywhere -- the SHOULD-fire half."""
    return None


def _gated_endpoint() -> None:
    """References a recognised auth primitive directly -- the must-NOT-fire half."""
    get_auth_middleware()
    return None


def get_auth_middleware() -> None:  # noqa: D401 - contrast-pair stand-in, not the real one
    """Stand-in with the primitive's exact name, so ``co_names`` matches it."""
    return None


class TestContrastPair:
    """A guard that never fires passes its own suite. This proves it can fire.

    Both halves run the SAME production code (``_router_is_gated`` via
    ``effective_routes``), not a reimplementation of it, on two minimal real
    ``fastapi.APIRouter`` instances -- one with no gate anywhere (must be
    reported ungated) and one gated only through the endpoint-body shape (4)
    in the module docstring, since that is the harder half to get right and
    the one most likely to regress silently.
    """

    def test_router_with_no_gate_is_reported_ungated(self):
        from fastapi import APIRouter

        router = APIRouter()
        router.get("/open")(_open_endpoint)
        assert _router_is_gated(router) is False

    def test_router_gated_only_via_endpoint_body_is_reported_gated(self):
        from fastapi import APIRouter

        router = APIRouter()
        router.get("/gated")(_gated_endpoint)
        assert _router_is_gated(router) is True

    def test_classify_helpers_agree_on_a_synthetic_dependant_tree(self):
        """Unit-level pair mirroring #15737's own ``TestClassifyHelperContrastPair``."""
        open_dependant = _FakeDependant(call=lambda: None)
        assert _dependant_tree_is_gated(open_dependant) is False

        inner = _FakeDependant(call=_amw_get_current_user)
        middle = _FakeDependant(call=lambda: None, dependencies=[inner])
        gated_dependant = _FakeDependant(call=lambda: None, dependencies=[middle])
        assert _dependant_tree_is_gated(gated_dependant) is True
