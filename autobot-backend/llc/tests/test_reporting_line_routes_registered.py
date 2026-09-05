# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The reporting-line routes are reachable, and the write gate is declared (#15763).

Two separate claims, and the second is the one this file exists for.

Reachability, because a router that is never ``include_router``-ed looks exactly
like a working one from inside its own module — the defect this surface shipped
four times (#14221 steps 1-3 and 5).

**Gate visibility**, because the write gate is what makes re-parenting an
authority change (#15765). A gate called inside a handler body never enters the
``Dependant`` tree: #15743's fix closed its hole while the posture suite kept
reporting the route as merely authenticated, for exactly that reason (#15737).
So this asserts the dependency is *declared*, not merely that unauthorised
callers are refused — a service-layer check would satisfy the second and fail
the first, and only the first is auditable from outside.
"""

from __future__ import annotations

from autobot_shared.api_routing.router_routes import effective_routes
from llc.api import router as llc_router

_PREFIX = "/llc/reporting-lines"

_EXPECTED = {
    ("GET", f"{_PREFIX}/{{company_id}}/{{subject_type}}/{{subject_id}}"),
    ("GET", f"{_PREFIX}/{{company_id}}/{{subject_type}}/{{subject_id}}/reports"),
    ("PUT", f"{_PREFIX}/{{company_id}}/{{subject_type}}/{{subject_id}}"),
    ("DELETE", f"{_PREFIX}/{{company_id}}/{{subject_type}}/{{subject_id}}"),
}

#: The methods that change the hierarchy, and therefore change who holds
#: authority over whom. Reads are not gated by this.
_WRITE_METHODS = {"PUT", "DELETE"}

#: The exact dependency the mutating routes must declare (#15793). Named rather
#: than pattern-matched: the whole point of the permission is that it is
#: narrower than an admin check, so a test accepting "something admin-ish"
#: would not notice it being swapped for one.
_GATE = "require_reporting_line_write"


def _mounted() -> set:
    return {
        (method, m.path) for m in effective_routes(llc_router) for method in m.methods
    }


def test_every_reporting_line_route_is_mounted() -> None:
    missing = _EXPECTED - _mounted()
    assert not missing, f"defined but never reachable: {sorted(missing)}"


def test_reads_carry_auth_and_tenant_dependencies() -> None:
    unguarded = []
    checked = 0
    for m in effective_routes(llc_router):
        if not m.path.startswith(_PREFIX):
            continue
        checked += 1
        dependant = getattr(m.route, "dependant", None)
        names = {
            getattr(d.call, "__name__", "")
            for d in getattr(dependant, "dependencies", [])
        }
        if "get_current_user" not in names or "require_org_context" not in names:
            unguarded.append((sorted(m.methods), m.path, sorted(names)))
    # Presence first: a wrong prefix matches nothing and the assertion below
    # passes having verified nothing at all.
    assert checked == len(_EXPECTED), (
        f"expected {len(_EXPECTED)} routes to inspect, saw {checked}"
    )
    assert not unguarded, f"routes missing auth/tenant dependencies: {unguarded}"


def test_the_write_gate_is_a_declared_dependency() -> None:
    """Every mutating route carries the gate in its ``Dependant`` tree.

    This is the assertion that a service-layer check cannot satisfy.

    It names the gate **exactly**. While the permission was still being minted
    this also accepted a narrower company-admin placeholder, which was right
    then and is wrong now: a loose match would keep passing if someone replaced
    the permission with a generic admin check, and that is a real regression —
    ``admin.reporting_line.write`` exists precisely because company admin is
    not the right authority for re-parenting.
    """
    ungated = []
    checked = 0
    for m in effective_routes(llc_router):
        if not m.path.startswith(_PREFIX):
            continue
        if not (m.methods & _WRITE_METHODS):
            continue
        checked += 1
        dependant = getattr(m.route, "dependant", None)
        names = {
            getattr(d.call, "__name__", "")
            for d in getattr(dependant, "dependencies", [])
        }
        if _GATE not in names:
            ungated.append((sorted(m.methods), m.path, sorted(names)))
    assert checked == 2, f"expected 2 mutating routes, saw {checked}"
    assert not ungated, f"mutating routes with no declared write gate: {ungated}"
