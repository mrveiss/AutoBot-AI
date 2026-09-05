# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The tool catalogue routes are reachable, not merely defined (#14852).

The same defect this guards against has landed four times on this surface: a
router that exists but is never ``include_router``-ed looks exactly like a
working one from inside its own module, and every unit test of the service
still passes.

Asserts against the **assembled** LLC router, not against ``tools.py``, because
importing the module proves only that the file parses.
"""

from __future__ import annotations

from autobot_shared.api_routing.router_routes import effective_routes
from llc.api import router as llc_router

#: The assembled router carries prefix="/llc", so mounted paths include it.
_PREFIX = "/llc/tools"

_EXPECTED = {
    ("GET", f"{_PREFIX}/{{company_id}}"),
    ("GET", f"{_PREFIX}/{{company_id}}/{{tool_name}}/usage"),
    ("PUT", f"{_PREFIX}/{{company_id}}/{{tool_name}}"),
}


def _mounted() -> set:
    """(method, path) pairs reachable through the assembled LLC router."""
    return {
        (method, mounted.path)
        for mounted in effective_routes(llc_router)
        for method in mounted.methods
    }


def test_every_tool_route_is_mounted_on_the_llc_router() -> None:
    missing = _EXPECTED - _mounted()
    assert not missing, f"defined but never reachable: {sorted(missing)}"


def test_tool_routes_require_authentication() -> None:
    """Every tool route carries the auth and tenant dependencies.

    Asserting the dependency is present is cheaper and more reliable than
    trusting each handler to have remembered it (#14168).
    """
    unguarded = []
    checked = 0
    for mounted in effective_routes(llc_router):
        if not mounted.path.startswith(_PREFIX):
            continue
        checked += 1
        dependant = getattr(mounted.route, "dependant", None)
        names = {
            getattr(dep.call, "__name__", "")
            for dep in getattr(dependant, "dependencies", [])
        }
        if "get_current_user" not in names or "require_org_context" not in names:
            unguarded.append((sorted(mounted.methods), mounted.path, sorted(names)))
    # Presence check first: with a wrong prefix this loop matches nothing and
    # the assertion below passes while having verified nothing at all — an
    # empty result reading as a clean result.
    assert checked == len(_EXPECTED), (
        f"expected {len(_EXPECTED)} tool routes to inspect, saw {checked}"
    )
    assert not unguarded, f"tool routes missing auth/tenant dependencies: {unguarded}"
