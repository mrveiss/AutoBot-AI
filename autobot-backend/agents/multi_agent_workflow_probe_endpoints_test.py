# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every path the workflow validator probes must be one the backend serves (#15133).

``multi_agent_workflow_validation_test.py`` probed ``/api/intelligent-agent/deploy``
and ``/api/research/deploy`` from the day it was written. Neither prefix was
right, but that was not the defect: **no router has ever served a ``/deploy``
path under either name, at any commit.** ``git log -S '/deploy"'`` over
``autobot-backend/``, ``backend/`` and ``src/`` returns only the #926 restructure
moving this very file, plus one unrelated ``/api/nodes/{id}/certificate/deploy``
in the SLM backend. The probes asserted a capability that was never built.

It read as healthy for a year because the validator only runs against a live
backend, treats a non-200 as an agent that happens to be down, and -- being a
``*_test.py`` module with no ``test_`` function and no ``Test`` class -- collected
**zero** pytest items. Nothing ever executed the list, so nothing ever noticed.

This module is the missing execution. It resolves each probed path against the
router registry ``app_factory._register_routers`` mounts from, so a probe of a
path no router serves fails here, in CI, without a backend.

Cost note: importing ``core_routers`` pulls in every core router module (~25s
cold). That is the price of checking the real route table instead of a
transcription of it, and it is paid once per shard.
"""

from __future__ import annotations

import importlib

import pytest

from agents.multi_agent_workflow_validation_test import AGENT_ENDPOINTS

#: Core alone mounted 713 routes when this landed. The floor exists to catch the
#: enumeration collapsing -- an import that silently yields nothing would mark
#: every probe unserved, or worse, be read as "nothing to check".
MINIMUM_EXPECTED_ROUTES = 400

#: Paths that must stay absent. These are the two fictions this issue removed;
#: if one is ever served for real, this test is the thing that says so.
NEVER_SERVED = ("/api/intelligent-agent/deploy", "/api/research/deploy")


def _collect(served: set[tuple[str, str]], router, prefix: str) -> None:
    """Record every ``(method, full path)`` a router contributes under *prefix*."""
    for route in router.routes:
        path = getattr(route, "path", None)
        if path is None:  # an included sub-router carries no path of its own
            continue
        for method in getattr(route, "methods", None) or ("WEBSOCKET",):
            served.add((method, f"/api{prefix}{path}"))


@pytest.fixture(scope="module")
def served_routes() -> set[tuple[str, str]]:
    """The ``(method, path)`` pairs the app factory would mount.

    Core routers are enumerated in full. Feature routers are imported only when
    their declared prefix covers a probed path, because importing all 172 costs
    minutes. A probe served **only** by a feature router mounted at the root
    prefix would therefore read as unserved -- extend this fixture rather than
    the probe list if that ever happens.
    """
    from initialization.router_registry.core_routers import load_core_routers
    from initialization.router_registry.feature_routers import FEATURE_ROUTER_CONFIGS

    served: set[tuple[str, str]] = set()
    for router, prefix, _tags, _name in load_core_routers():
        _collect(served, router, prefix)

    probed = [path for path, _agent in AGENT_ENDPOINTS]
    for module_path, prefix, _tags, _name in FEATURE_ROUTER_CONFIGS:
        if not prefix or not any(path.startswith(f"/api{prefix}/") for path in probed):
            continue
        _collect(served, importlib.import_module(module_path).router, prefix)
    return served


class TestTheEnumerationsAreReal:
    """Neither side of the comparison may be empty, or the verdict is worthless."""

    def test_probe_list_is_not_empty(self):
        assert AGENT_ENDPOINTS, (
            "AGENT_ENDPOINTS is empty -- the coordination check would probe nothing and "
            "report every run as passing (#15133)"
        )

    def test_route_table_has_not_collapsed(self, served_routes):
        assert len(served_routes) >= MINIMUM_EXPECTED_ROUTES, (
            f"only {len(served_routes)} routes enumerated from the router registry, expected at "
            f"least {MINIMUM_EXPECTED_ROUTES}; an empty or truncated route table makes every "
            "assertion below vacuous"
        )


class TestEveryProbedPathIsServed:
    def test_each_probe_resolves_to_a_get_route(self, served_routes):
        unserved = [(path, agent) for path, agent in AGENT_ENDPOINTS if ("GET", path) not in served_routes]
        assert not unserved, (
            "these probed paths are not served as GET by any registered router:\n  "
            + "\n  ".join(f"{path}  ({agent})" for path, agent in unserved)
            + "\n\nThe validator would get a 404 and report it as an agent being down. "
            "Point the probe at a path the backend actually exposes, or drop it and name "
            "the capability it was checking (#15133)."
        )

    def test_agent_names_are_distinct(self):
        names = [agent for _path, agent in AGENT_ENDPOINTS]
        assert len(names) == len(set(names)), f"duplicate agent labels would double-count: {names}"


class TestTheRemovedProbesWereFiction:
    """Guards the guard: the paths this issue deleted must still be unserved."""

    @pytest.mark.parametrize("path", NEVER_SERVED)
    def test_deploy_path_is_served_by_nothing(self, served_routes, path):
        methods = sorted(method for method, served in served_routes if served == path)
        assert not methods, (
            f"{path} is now served ({', '.join(methods)}). An agent deployment endpoint has "
            "appeared since #15133 -- reinstate the probe deliberately instead of leaving "
            "this assertion to fail."
        )

    @pytest.mark.parametrize("path", NEVER_SERVED)
    def test_no_probe_points_at_a_removed_path(self, path):
        assert path not in [probed for probed, _agent in AGENT_ENDPOINTS]
