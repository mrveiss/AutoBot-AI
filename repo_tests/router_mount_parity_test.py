# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A router gated on one mount and wide open on another (#15098).

``api/terminal_tools.py`` owns four routes that install packages and run system
commands. It was mounted twice:

* ``api/terminal.py`` — into ``admin_router``, which carries
  ``dependencies=[Depends(check_admin_permission)]``. Correctly gated.
* ``initialization/router_registry/terminal_routers.py`` — as a **top-level
  registry entry with an empty prefix**, which ``app_factory`` mounts at
  ``/api`` with **no** ``dependencies=``.

So ``/api/install-tool``, ``/api/check-tool``, ``/api/validate-command`` and
``/api/package-managers`` were reachable with no admin check
(#15084, fixed by #15096). ``SERVICE_ONLY_PATHS`` in the service-auth
middleware never covered them — it lists ``/api/npu/*``, ``/api/ai-stack/*``
and ``/api/browser/*`` only.

**Why every existing test stayed green.** Each one asserted the gate on the
``terminal.py`` mount. None enumerated *where else* the router is mounted. A
per-mount assertion is structurally blind to a second mount: it passes forever
while the same routes are served ungated from another path.

This guard closes that class rather than that instance. It derives the mount
graph from source and fails when a router is reachable through a mount that
lacks protection its other mounts carry.

Static, not runtime
-------------------

Under fastapi 0.141.1 (what CI resolves) ``include_router`` defers: neither the
prefix nor an inherited ``dependencies=`` is readable off the route object, so
runtime introspection cannot see what this guard needs (#15093). This box
resolves 0.135.2 (#15091), where some of it *is* readable — a runtime guard
would therefore mean one thing locally and another in CI, which is worse than
no guard. Parsing the registration sites is version-independent and answers the
question actually being asked: *is this router mounted somewhere that skips a
gate its other mounts apply?*

The trade this accepts: a gate applied by something other than a
``dependencies=`` argument (middleware path matching, a decorator, an in-body
``Depends``) is invisible here. Those are named in ``EXEMPT_ROUTERS`` with a
reason each — never counted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from autobot_shared.api_routing.mount_graph import APP_ROOT, MountGraph, build_graph, registry_dirname

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"
_REGISTRY_DIRNAME = registry_dirname()

# The mount graph itself lives in `autobot_shared/api_routing/mount_graph.py`
# (#15093): `repo_tests/router_routes_traversal_test.py` needs the same three
# facts, and a second AST resolver would drift from this one exactly as the two
# `include_router` regexes drifted before #12985 consolidated them.

# Routers that legitimately reach the app through a mount carrying less than
# another mount of theirs. Each needs a reason; a bare count is not evidence
# and would hide the next `terminal_tools`.
# Empty, and it retired itself. The one entry here named `api.terminal_tools:router`
# for #15084 -- gated through `api/terminal.py`'s `admin_router`, ungated through the
# terminal registry entry. #15096 (`6cc5505ef`) moved the gate onto that router's own
# constructor, so both mounts now carry it, and
# `test_exemptions_are_named_and_still_real` failed on the next run demanding the line
# be removed. That is the intended lifecycle: an exemption here cannot outlive its
# reason, because a stale one is a hole nothing reports.
EXEMPT_ROUTERS: Dict[str, str] = {}

# Names that read as a gate when they appear in a `dependencies=` list. Used
# only for the non-vacuity check below — the parity comparison itself is
# name-agnostic and compares whatever dependency names it finds.
_GATE_HINTS = ("permission", "auth", "admin", "rbac", "require", "verify", "current_user")


@pytest.fixture(scope="module")
def graph() -> MountGraph:
    return build_graph(_BACKEND)


# --- non-vacuity ------------------------------------------------------------
#
# A discovery step that silently finds nothing reports success while inspecting
# nothing. Each assertion below fails loudly instead.


def test_discovery_found_routers(graph: MountGraph):
    assert len(graph.routers) >= 50, (
        f"non-vacuity: only {len(graph.routers)} APIRouter definitions discovered under "
        f"{_BACKEND.name}. Discovery is broken; the parity check below would inspect nothing."
    )


def test_discovery_found_mounts(graph: MountGraph):
    assert len(graph.edges) >= 100, (
        f"non-vacuity: only {len(graph.edges)} mount edges discovered. "
        "Expected include_router call sites plus every router_registry entry."
    )


def test_discovery_found_registry_mounts(graph: MountGraph):
    registry = [e for e in graph.edges if e.parent == APP_ROOT and _REGISTRY_DIRNAME in e.site]
    assert len(registry) >= 30, (
        f"non-vacuity: only {len(registry)} app-root mounts came from "
        f"initialization/{_REGISTRY_DIRNAME}/. That is where #15084's ungated mount lived."
    )


def test_discovery_can_see_a_gate(graph: MountGraph):
    """Guard detection must actually detect a guard somewhere.

    If ``dependencies=`` parsing broke, every mount would look equally ungated
    and the parity check would pass while comparing nothing but empty sets.
    """
    gated = {key: sorted(definition.own_guards) for key, definition in graph.routers.items() if definition.own_guards}
    gated_edges = [e for e in graph.edges if e.guards]
    assert gated or gated_edges, (
        "non-vacuity: no `dependencies=` was found on any APIRouter definition or any "
        "include_router call. Guard extraction is broken — every mount now compares as ungated."
    )
    hinted = [name for names in gated.values() for name in names if any(hint in name.lower() for hint in _GATE_HINTS)]
    assert hinted, f"non-vacuity: no discovered dependency reads as an auth gate. Found: {sorted(gated)[:10]}"


def test_terminal_tools_router_is_discovered(graph: MountGraph):
    """The #15084 router must be in the graph, whatever its mounts now are.

    #15096 removes its ungated registry entry; this asserts the *discovery*
    still reaches it, so the guard cannot go blind to the file it was built for.
    """
    assert "api.terminal_tools:router" in graph.routers
    mounts = [e for e in graph.edges if e.child == "api.terminal_tools:router"]
    assert mounts, "api.terminal_tools:router is defined but no mount of it was discovered"


def test_every_reference_resolved(graph: MountGraph):
    """An include_router whose target could not be resolved is a blind spot."""
    assert not graph.unresolved, "unresolvable router references:\n  " + "\n  ".join(sorted(graph.unresolved)[:20])


def test_dynamic_mounts_are_only_the_factory_loop(graph: MountGraph):
    """The one mount whose target is runtime-only must stay the factory loop.

    ``app_factory`` includes each loaded registry tuple through a loop
    variable; those mounts are modelled from the registry entries themselves.
    A dynamic ``include_router`` anywhere else is a mount this guard cannot
    see, so it fails here rather than being quietly skipped.
    """
    assert graph.dynamic, "non-vacuity: app_factory's registry loop was not discovered at all"
    stray = sorted({site for site in graph.dynamic if not site.startswith("app_factory:")})
    assert not stray, "include_router on a runtime-computed target outside app_factory:\n  " + "\n  ".join(stray)


# --- the guard --------------------------------------------------------------


def test_no_router_is_mounted_past_a_gate_its_siblings_carry(graph: MountGraph):
    """Fails when one mount of a router skips protection another mount applies.

    This is the named assertion. It does not know about ``terminal_tools`` or
    any other router by name: it compares, for every mounted router, the guard
    sets on every path that reaches it from the app root.
    """
    bad = graph.inconsistent(EXEMPT_ROUTERS)
    if not bad:
        return
    report: List[str] = []
    for key, paths in sorted(bad.items()):
        weakest = sorted(frozenset.intersection(*paths))
        missing = sorted(frozenset.union(*paths) - frozenset.intersection(*paths))
        sites = [f"{e.parent} -> {e.child} @ {e.site}" for e in graph.edges if e.child == key]
        report.append(
            f"{key}: reachable with guards {weakest or '[]'} while another mount applies {missing}\n"
            + "\n".join(f"    mount: {s}" for s in sorted(sites))
        )
    pytest.fail(
        "router(s) reachable through a mount lacking protection their other mounts carry "
        "(#15098 — the #15084 class):\n" + "\n".join(report)
    )


def test_exemptions_are_named_and_still_real(graph: MountGraph):
    """Every exemption carries a reason, and names a router that still exists.

    A stale exemption is a hole that nothing reports, so it is an error rather
    than a no-op.
    """
    for key, reason in EXEMPT_ROUTERS.items():
        assert reason.strip(), f"exemption {key} has no reason"
        assert key in graph.routers, f"exemption {key} names a router that no longer exists — drop it"
        paths = graph.paths_to(key)
        assert len(paths) >= 2 and frozenset.intersection(*paths) != frozenset.union(
            *paths
        ), f"exemption {key} is no longer needed: its mounts now agree. Remove it."
