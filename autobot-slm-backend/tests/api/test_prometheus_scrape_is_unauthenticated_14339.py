# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The prometheus scrape route must not require authentication (#14339).

Prometheus reported the `slm` job `down` with `server returned HTTP status 401
Unauthorized`. The route sat on the performance router, which `main.py` mounts
with `dependencies=_SM`, and a scraper cannot authenticate — so the job had
never yielded a single sample and anything built on SLM performance metrics had
never had data to show. The only visible symptom was an empty panel, which looks
exactly like a quiet system.

The fix puts the scrape route on its own router mounted without that dependency,
matching what the backend already does for the same reason (#1288). The path is
unchanged, so a deployed scrape config needs no rewrite.

Both directions are asserted. Checking only that the metrics route is reachable
would stay green if someone dropped the dependency from the whole performance
router, which would expose every service-management endpoint on this service.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from api import performance  # noqa: E402

_SCRAPE_PATH = "/performance/metrics/prometheus"
_MOUNTED_AT = "/api/performance/metrics/prometheus"


def _paths(router) -> set[str]:
    return {route.path for route in router.routes}


def test_the_scrape_route_lives_on_the_unauthenticated_router():
    assert _SCRAPE_PATH in _paths(performance.metrics_router)


def test_the_scrape_route_is_not_also_on_the_authenticated_router():
    """Registered twice, the authenticated copy could win and restore the 401."""
    assert _SCRAPE_PATH not in _paths(performance.router)


def test_the_authenticated_router_still_serves_everything_else():
    """The split must move one route, not empty the router.

    If the fix had moved more than the scrape surface, those endpoints would
    silently lose their auth — a far worse outcome than the bug being fixed.
    """
    remaining = _paths(performance.router)
    assert len(remaining) > 5, f"the authenticated performance router has only {remaining}"


def test_the_two_routers_share_a_prefix_so_the_path_is_unchanged():
    """The deployed scrape config points at the existing path.

    Changing it would mean the fix only takes effect after the monitoring role
    is also redeployed — two coupled deployments instead of one.
    """
    assert performance.metrics_router.prefix == performance.router.prefix


def _mount_calls() -> dict[str, ast.Call]:
    """Every `app.include_router(<name>, ...)` in main.py, keyed by router name.

    Read structurally rather than executed: importing `main` works from a shell
    but not under pytest, where `api` resolves as a different namespace package
    and the import dies on an unrelated router. Parsing gets at the same wiring
    without depending on which of the two import environments is in play.

    This asserts on the shape of the call — which keywords it carries — not on
    the text of the line, so reformatting cannot make it pass or fail.

    Scope limit, stated because review demonstrated it: `ast.walk` finds the call
    wherever it sits, so wrapping the mount in a branch that never runs leaves
    these tests green. What is verified is that the wiring is *declared*
    correctly, not that it *executes*. The direction of that blind spot is
    "looks mounted but is not" — a 404, not an exposure — so it cannot hide a
    leak. Closing it means making `main` importable under pytest, which is a
    separate problem from this one.
    """
    tree = ast.parse((Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8"))
    calls: dict[str, ast.Call] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "include_router" or not node.args:
            continue
        if isinstance(node.args[0], ast.Name):
            calls[node.args[0].id] = node
    return calls


def _keywords(call: ast.Call) -> set[str]:
    return {kw.arg for kw in call.keywords if kw.arg}


def test_the_app_mounts_the_scrape_router_without_auth_and_the_rest_with_it():
    """The mount is where the defect lived — the route was always fine, the
    router-level dependency it inherited was not."""
    calls = _mount_calls()
    assert "performance_metrics_router" in calls, "the scrape router is never mounted on the app"
    assert "performance_router" in calls, "the authenticated performance router is not mounted"

    assert "dependencies" not in _keywords(calls["performance_metrics_router"]), (
        "the scrape router is mounted with a router-level dependency; prometheus "
        "cannot authenticate and every scrape will 401 again (#14339)"
    )
    assert "dependencies" in _keywords(
        calls["performance_router"]
    ), "the authenticated performance router lost its service-management dependency"


def test_the_scrape_router_is_mounted_under_the_same_prefix(tmp_path):
    """A different mount prefix moves the endpoint out from under the deployed
    scrape config, and every other assertion here would still pass."""
    calls = _mount_calls()

    def prefix_of(name: str) -> str | None:
        for kw in calls[name].keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                return kw.value.value
        return None

    assert prefix_of("performance_metrics_router") == prefix_of("performance_router") == "/api"


def test_the_mounted_path_is_the_one_prometheus_scrapes():
    """Guard the guard: the route path already carries the router's own prefix,
    so only the app-level mount prefix is added to reach the scraped URL."""
    assert f"/api{_SCRAPE_PATH}" == _MOUNTED_AT


def test_every_ungated_router_is_named_in_the_registry():
    """`main.py` keeps a list of routers deliberately mounted without the gate.

    Nothing enforced it, and it had already gone stale before this change — a
    public surface that is not in the one inventory the file maintains is a
    public surface nobody reviewing auth will see. So the list is checked here
    rather than trusted: mount a router without `dependencies` and this fails
    until it is declared, which makes adding public surface a visible act.

    Deliberately keyed on the mount, not on the comment. A name can be removed
    from the list and the test still fails, because the mount is what decides
    who can reach the route.
    """
    source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
    registry = source.split("# Routers intentionally left open", 1)
    assert len(registry) == 2, "the public-router registry comment block is gone from main.py"
    declared = registry[1].split("# Service-management gate", 1)[0]

    ungated = {name for name, call in _mount_calls().items() if "dependencies" not in _keywords(call)}
    undeclared = sorted(name for name in ungated if name not in declared)
    assert not undeclared, (
        f"mounted without the service-management gate but not declared in the registry: "
        f"{undeclared}. Add each with the reason it must be reachable unauthenticated, "
        f"or mount it with `dependencies=_SM` (#14339)."
    )


def test_the_registry_check_actually_sees_the_ungated_mounts():
    """An empty `ungated` set would make the assertion above vacuous.

    If the mount matcher stopped matching — a rename, a different idiom — every
    router would look gated and the registry check would pass over all of them.
    """
    ungated = {name for name, call in _mount_calls().items() if "dependencies" not in _keywords(call)}
    assert "performance_metrics_router" in ungated
    assert len(ungated) >= 3, f"only {len(ungated)} ungated mounts found — the matcher is broken"
