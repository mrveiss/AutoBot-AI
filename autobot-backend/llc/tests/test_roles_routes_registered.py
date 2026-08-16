# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The role routes are reachable, not merely defined (#14221).

Steps 1-3 and 5 each shipped a service with no route, which made all four
unreachable — a sink with no surface. This asserts the opposite defect cannot
recur silently: a router that exists but is never ``include_router``-ed looks
exactly like a working one from inside its own module.

Asserts against the **assembled** LLC router, not against ``roles.py``, because
importing the module proves only that the file parses.
"""

from __future__ import annotations

from llc.api import router as llc_router

#: The assembled router carries prefix="/llc", so mounted paths include it.
_PREFIX = "/llc/roles"

_EXPECTED = {
    ("GET", f"{_PREFIX}/{{company_id}}"),
    ("POST", f"{_PREFIX}/{{company_id}}"),
    ("PATCH", f"{_PREFIX}/{{company_id}}/{{role_id}}"),
    ("DELETE", f"{_PREFIX}/{{company_id}}/{{role_id}}"),
    ("GET", f"{_PREFIX}/{{company_id}}/{{role_id}}/holders"),
    ("POST", f"{_PREFIX}/{{company_id}}/{{role_id}}/holders"),
    ("DELETE", f"{_PREFIX}/{{company_id}}/{{role_id}}/holders/{{assignment_id}}"),
    ("GET", f"{_PREFIX}/{{company_id}}/{{role_id}}/permissions"),
    ("POST", f"{_PREFIX}/{{company_id}}/{{role_id}}/permissions"),
    ("DELETE", f"{_PREFIX}/{{company_id}}/{{role_id}}/permissions/{{permission}}"),
    ("GET", f"{_PREFIX}/{{company_id}}/{{role_id}}/workflows"),
    ("POST", f"{_PREFIX}/{{company_id}}/{{role_id}}/workflows"),
    ("DELETE", f"{_PREFIX}/{{company_id}}/{{role_id}}/workflows/{{workflow_id}}"),
}


def _mounted() -> set:
    """(method, path) pairs reachable through the assembled LLC router.

    This FastAPI version defers inclusion: ``router.routes`` holds
    ``_IncludedRouter`` wrappers with no ``.path``, and the real routes live on
    ``.original_router.routes``. Walking the top level alone finds one route out
    of thirty-eight and reads as "nothing is mounted".

    Same idiom as ``api/codebase_analytics/endpoints/impact_endpoint_test.py``
    and ``api/self_capabilities_integration_test.py``, which both document this.
    The sub-router paths are relative to the parent, so the ``/llc`` prefix is
    prepended here rather than expected on the route itself.
    """
    found = set()
    for included in llc_router.routes:
        original = getattr(included, "original_router", None)
        subroutes = original.routes if original is not None else [included]
        for sub in subroutes:
            path = getattr(sub, "path", None)
            if not path:
                continue
            for method in getattr(sub, "methods", set()) or set():
                found.add((method, f"{llc_router.prefix}{path}"))
    return found


def test_every_role_route_is_mounted_on_the_llc_router() -> None:
    missing = _EXPECTED - _mounted()
    assert not missing, f"defined but never reachable: {sorted(missing)}"


def test_role_routes_require_authentication() -> None:
    """Every role route carries the auth dependencies.

    #14168 recorded unguarded ``/work-items`` routes; the cheapest guard against
    repeating that is asserting the dependency is present rather than trusting
    that each handler remembered it.
    """
    unguarded = []
    checked = 0
    for included in llc_router.routes:
        original = getattr(included, "original_router", None)
        for sub in original.routes if original is not None else []:
            path = f"{llc_router.prefix}{getattr(sub, 'path', '')}"
            if not path.startswith(_PREFIX):
                continue
            checked += 1
            dependant = getattr(sub, "dependant", None)
            names = {getattr(dep.call, "__name__", "") for dep in getattr(dependant, "dependencies", [])}
            if "get_current_user" not in names or "require_org_context" not in names:
                unguarded.append((sorted(getattr(sub, "methods", []) or []), path, sorted(names)))
    # Presence check first: with a wrong prefix this loop matches nothing and
    # the assertion below passes while having verified nothing at all — an
    # empty result reading as a clean result, which is how the first draft of
    # this file "passed".
    assert checked == len(_EXPECTED), f"expected {len(_EXPECTED)} role routes to inspect, saw {checked}"
    assert not unguarded, f"role routes missing auth/tenant dependencies: {unguarded}"
