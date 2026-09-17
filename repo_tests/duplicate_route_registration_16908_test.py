# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nothing registers the same (method, path) twice on the backend (#16908).

FastAPI matches routes in registration order: the first module to claim a
``(method, path)`` pair serves it, and every later registration at the same
pair is dead code that reads as a live endpoint. #16908 found four such pairs
by hand (``core_routers.py``/``feature_routers.py`` parsed for both
registration-tuple forms, 71% coverage) and fixed them; this guard is what
stops a fifth.

## Why this walks real router objects instead of parsing source

The first two candidate designs for this guard both produced confirmed false
positives, found the hard way rather than assumed away:

1. A **text-based prefix parser** (``autobot_shared.api_routing.router_prefixes``,
   the grammar ``scripts/audit_api_wiring.py`` and
   ``codebase_analytics/api_endpoint_scanner.py`` share, #12985) has a known
   blind spot: it cannot resolve ``from api.voice import realtime_router as
   voice_realtime_router``-style import aliases (#16917), so a real duplicate
   routed through an aliased import is invisible to it.
2. ``api/codebase_analytics/api_endpoint_scanner.py::BackendEndpointScanner``
   -- more mature, twice patched for package resolution (#12945/#12956), and
   what an earlier revision of this guard used -- still mis-resolved two
   prefixes when checked against source by hand: ``api/system.py``'s
   ``@router.get("/cache/stats")`` (registered at prefix ``/system``, so it
   actually serves ``/api/system/cache/stats``) was reported as colliding
   with ``api/cache_management.py``'s real ``/api/cache/stats``; the same
   shape misfired on ``api/redis_mcp/router.py``. A hand-written check
   (independently run by a peer session) made the mirror-image mistake:
   attributing every route in a file to that file's *first* ``APIRouter(...)``
   call, which misscored ``llc/api/runs.py``'s ``heartbeat_runs_router``
   (its own, later, differently-prefixed ``APIRouter``) as if it shared
   ``router``'s ``/agents`` prefix.

Both are **text re-derivations** of a fact FastAPI itself resolves at
registration time. This walks the real ``APIRouter`` objects
``load_core_routers()``/``load_optional_routers()`` return -- the exact same
objects ``app_factory.py``'s ``_register_routers()`` calls
``app.include_router()`` on -- via
``autobot_shared.api_routing.router_routes.effective_routes()`` (the one
FastAPI-version-safe route traversal, #15093), using each tuple's own
``prefix`` element rather than re-parsing it from source. It cannot
mis-resolve a prefix the way a text scanner can, because it never re-derives
one -- it reads the value the app itself would use.

Verified against both false-positive reports above: this walk reports
``cache/stats`` and ``mcp/tools`` as NOT colliding (confirmed by hand) and
``llc/agents`` as NOT colliding (also confirmed by hand, after the peer
session's parser was corrected) -- exactly the outcome direct source reading
gives, for all three.

## Scope boundary

Covers every router ``load_core_routers()``/``load_optional_routers()``
return -- 273 registrations, matching an independent peer session's
by-hand count of registry entries (273/273) per ``RATCHET_BASELINES.md``
rule 3. It does **not** cover the three routers
``app_factory.py``'s ``_register_routers()`` mounts directly
(``api/openai_compat.py``, ``api/anthropic_compat.py``,
``api/jwks.py::well_known_router``, all under ``/v1`` or ``/.well-known``,
outside the core/optional-router lists this function reads) -- a genuinely
different registration mechanism, not an oversight; nothing found so far
suggests they collide with anything under ``/api``, but this guard makes no
claim about them.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from unittest.mock import patch

import pytest
from repo_tests._paths import repo_root

_BACKEND = repo_root() / "autobot-backend"

# #16913: two duplicates this walk finds, not yet resolved -- each needs the
# same registration-order tracing #16908's body did for its own four rows
# before it can be fixed, not a guess here. Shrinks by one entry per pair
# #16913 resolves, down to empty; test_the_baseline_has_no_stale_entries below
# fails the moment one stops being a real duplicate, so a fix that forgets to
# remove its baseline line is caught rather than silently over-exempted.
KNOWN_DUPLICATE_BASELINE: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/llc/agent/context/{item_id}"),
        ("POST", "/api/voice/realtime/tools/call"),
    }
)


def _load_registered_routers() -> list[tuple[object, str, str]]:
    """(router, prefix, name) for every core + optional router.

    Mirrors app_factory.py's _register_routers(): the same two calls, in the
    same order, over the same tuples -- just without actually mounting them
    onto a FastAPI() app, which needs no DB/Redis/service dependency this
    guard would otherwise have to fake.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from initialization.router_registry.core_routers import load_core_routers
    from initialization.routers import load_optional_routers

    return [(router, prefix, name) for router, prefix, _tags, name in (*load_core_routers(), *load_optional_routers())]


def _scan_duplicates() -> dict[tuple[str, str], list[str]]:
    """{(method, path): [defining module, ...]} for every pair served by >1 module."""
    from autobot_shared.api_routing.router_routes import effective_routes

    registered = _load_registered_routers()
    # Floor, not a loose sanity threshold: load_core_routers()/load_optional_
    # routers() already swallow a per-module import failure internally (each
    # load_X_routers() helper catches and logs, so a broken module is simply
    # absent from the returned list rather than raising) -- the same silent-
    # drop shape #16917's `if module:` has. 273 is today's real count,
    # cross-checked once against an independent by-hand sweep of registry
    # entries (273/273). Only ever raise this floor when the real count
    # grows past it; never lower it to make a regression pass.
    assert len(registered) >= 273, (
        f"only {len(registered)} router registrations found, below the known "
        "floor of 273 -- load_core_routers()/load_optional_routers() population "
        "shrank (a module that used to import cleanly is now silently absent, "
        "or the tree genuinely lost routers); a guard silently sweeping fewer "
        "modules than it used to is worse than not running "
        "(see MEASUREMENT_DISCIPLINE.md)"
    )

    by_path: dict[tuple[str, str], list[str]] = defaultdict(list)
    incomplete: list[tuple[str, str]] = []
    for router, prefix, name in registered:
        for mounted in effective_routes(router):
            if not mounted.prefix_complete:
                # A prefix hidden above this route inside the router's own
                # nested include_router() calls -- effective_routes()'s own
                # documented limit, not resolvable here. Reported rather than
                # silently trusted with a possibly-short path.
                incomplete.append((name, mounted.path))
                continue
            endpoint = getattr(mounted.route, "endpoint", None)
            module_name = getattr(endpoint, "__module__", None) or name
            full_path = f"/api{prefix}{mounted.path}"
            methods = mounted.methods or frozenset({"WEBSOCKET"})
            for method in methods:
                by_path[(method, full_path)].append(module_name)

    assert not incomplete, (
        "these routers have a route whose full mount path could not be "
        "recovered (an inner include_router() hid its own prefix) -- this "
        "guard cannot judge whether they collide with anything, which is a "
        "coverage gap worth its own issue, not a silent pass:\n"
        + "\n".join(f"  {name}: {path}" for name, path in incomplete)
    )

    return {key: modules for key, modules in by_path.items() if len(set(modules)) > 1}


def test_no_new_duplicate_route_registration():
    duplicates = _scan_duplicates()
    unbaselined = {key: modules for key, modules in duplicates.items() if key not in KNOWN_DUPLICATE_BASELINE}

    assert not unbaselined, (
        "these (method, path) pairs are registered by more than one module. "
        "FastAPI matches in registration order, so only the first is reachable "
        "and every later one is dead code that reads as a live endpoint "
        "(#16908):\n"
        + "\n".join(
            f"  {method} {path}: {sorted(set(modules))}" for (method, path), modules in sorted(unbaselined.items())
        )
    )


def test_the_baseline_has_no_stale_entries():
    """A baseline entry that stops matching a real duplicate must be removed,
    not left to quietly exempt whatever future pair happens to reuse its
    (method, path) -- the exact blind spot RATCHET_BASELINES.md rule 1 warns
    freezing a detector's own baseline can hide.
    """
    duplicates = _scan_duplicates()
    stale = KNOWN_DUPLICATE_BASELINE - duplicates.keys()

    assert not stale, (
        "these baseline entries no longer match a real duplicate -- remove them "
        f"from KNOWN_DUPLICATE_BASELINE (#16913 progress): {sorted(stale)}"
    )


def test_a_deliberate_duplicate_is_caught_naming_both_modules():
    """Mutation proof (#16908 AC4): fabricate one collision and confirm the
    detector reports it, naming both sides -- not just that *some* assertion
    fails.

    Re-registering scheduler_toggles's own router object a second time is
    NOT a usable plant: _scan_duplicates() correctly keys on module identity
    (matching the real defect shape -- two DIFFERENT files claiming one
    path), so the same object walked twice collapses to one entry via
    set(modules) and is invisible by design, not by bug. The plant has to be
    a genuinely different module claiming an existing path.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from fastapi import APIRouter

    from initialization import routers as routers_module
    from initialization.router_registry.core_routers import load_core_routers

    real_core = load_core_routers()
    target_router, target_prefix, target_tags, target_name = next(t for t in real_core if t[3] == "audit")
    target_path = next(r.path for r in target_router.routes if getattr(r, "path", None))

    async def _planted_handler():
        return {}

    _planted_handler.__module__ = "api._test_planted_duplicate"
    fake_router = APIRouter()
    fake_router.add_api_route(target_path, _planted_handler, methods=["GET"])

    real_optional = routers_module.load_optional_routers()
    planted_entry = (fake_router, target_prefix, ["planted"], "_test_planted_duplicate")

    with patch.object(routers_module, "load_optional_routers", return_value=[*real_optional, planted_entry]):
        duplicates = _scan_duplicates()

    matches = {key: modules for key, modules in duplicates.items() if "api._test_planted_duplicate" in modules}
    assert matches, f"the planted duplicate was not detected; found {sorted(duplicates)}"
    ((key, modules),) = matches.items()
    assert any(m.endswith(f"api.{target_name}") for m in modules), (
        f"expected the real {target_name} registration alongside the plant at {key}, got {modules}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
