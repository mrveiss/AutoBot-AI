# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every router gated under #16375 declares the *canonical* gate, by identity.

Why identity and not a name. Until #18688 three distinct functions were called
``check_admin_permission`` (``auth_middleware.py``, ``api/audit.py`` and
``api/redis_service.py``) and they disagreed on return type and enforcement. A
test asserting the string passes on any same-named function that happens to be
imported, so it cannot tell the gate from a lookalike. ``audit`` and
``redis_service`` now use the one canonical function;
``test_the_name_resolves_to_one_canonical_function`` pins that, and the identity
assertions below stay as the per-router guard against a lookalike coming back.

Why here and not in ``api/api_endpoint_migrations_test.py``. That file is PARKED
at module scope (#15173, #5359 Option C): nothing in it executes, in CI or
locally. Its #16375 assertion is kept correct for whoever unparks it, but it
proves nothing today. This file runs.

What this adds over ``repo_tests/config_router_auth_coverage_test.py``. That
guard reads the source with AST and can only match names -- which is the right
instrument for sweeping every config-registered router, and is why it cannot
make the assertion below. It proves *a* gate is declared; this proves *which*.
"""

from __future__ import annotations

import importlib

import pytest

#: (module, attribute of the expected dependency, module that exports it).
#: Only routers gated on this branch. ``api.chat_knowledge`` is gated by #17724
#: on its own branch and is asserted there; adding it here would fail this file
#: until that PR merges, which would say nothing about this one.
GATED_ROUTERS: tuple[tuple[str, str, str], ...] = (
    ("api.anti_pattern", "get_current_user", "api.user_management.dependencies"),
    ("api.error_monitoring", "check_admin_permission", "auth_middleware"),
    ("api.llm_awareness", "check_admin_permission", "auth_middleware"),
    ("api.project_state", "check_admin_permission", "auth_middleware"),
    ("api.realtime_session", "get_current_user", "api.user_management.dependencies"),
    ("api.state_tracking", "check_admin_permission", "auth_middleware"),
)


def _declared(dependencies) -> set:
    """The dependency callables a router/route declares, not their names."""
    return {d.dependency for d in (dependencies or [])}


def test_the_table_is_not_empty():
    """A table that silently emptied would make every case below vacuous."""
    assert len(GATED_ROUTERS) >= 6


def test_the_name_resolves_to_one_canonical_function():
    """``check_admin_permission`` is ONE function repo-wide (#18688), the SLM copies aside.

    This file used to assert three distinct same-named functions, which is why
    the identity assertions below are necessary: a Depends on a same-named local
    copy would have passed a by-name check. ``audit`` and ``redis_service`` now
    bind ``auth_middleware.check_admin_permission`` itself. If a local copy comes
    back this fails, and the identity assertions stay what catches it per router.
    """
    import api.audit
    import api.redis_service
    import auth_middleware

    candidates = {
        auth_middleware.check_admin_permission,
        api.audit.check_admin_permission,
        api.redis_service.check_admin_permission,
    }
    assert candidates == {auth_middleware.check_admin_permission}, "a same-named local copy has returned"
    for module in (api.audit, api.redis_service):
        defined_here = getattr(module.check_admin_permission, "__module__", None) == module.__name__
        assert not defined_here, f"{module.__name__} defines its own check_admin_permission"


@pytest.mark.parametrize(("module_name", "gate_name", "gate_module"), GATED_ROUTERS)
def test_router_declares_the_canonical_gate(module_name: str, gate_name: str, gate_module: str):
    module = importlib.import_module(module_name)
    gate = getattr(importlib.import_module(gate_module), gate_name)

    declared = _declared(module.router.dependencies)
    assert declared, f"{module_name}.router declares no dependencies at all"
    assert gate in declared, (
        f"{module_name}.router does not declare {gate_module}.{gate_name}; "
        f"declared: {sorted(getattr(d, '__name__', repr(d)) for d in declared)}"
    )


@pytest.mark.parametrize(("module_name", "gate_name", "gate_module"), GATED_ROUTERS)
def test_router_has_routes_to_gate(module_name: str, gate_name: str, gate_module: str):
    """A router with no routes would pass the assertion above and protect nothing."""
    module = importlib.import_module(module_name)
    assert len(module.router.routes) >= 1


def test_realtime_provider_switch_is_admin_not_merely_authenticated():
    """PATCH /voice/realtime/providers flips the provider for every session (#16375).

    The router gate is authentication, because the browser calls these routes as
    an ordinary user. This one route mutates process-global state, so it carries
    its own admin dependency on top.
    """
    from api.realtime_session import router
    from auth_middleware import check_admin_permission

    patch_routes = [
        r for r in router.routes if getattr(r, "path", "") == "/providers" and "PATCH" in getattr(r, "methods", set())
    ]
    assert len(patch_routes) == 1, f"expected exactly one PATCH /providers, found {len(patch_routes)}"
    assert check_admin_permission in _declared(patch_routes[0].dependencies)
