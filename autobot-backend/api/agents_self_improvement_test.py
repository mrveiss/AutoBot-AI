# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests that the self-improvement API enforces authentication (#11060).

The router was previously mounted with no auth: any unauthenticated caller could
read cross-tenant task outcomes and wipe learned state via reset-learning. Every
endpoint must now require an authenticated user; the destructive reset endpoint
must require admin.
"""

from auth_middleware import check_admin_permission, get_current_user


def _dependency_calls(route) -> set:
    """Flatten every dependency callable wired into a route's dependant tree."""
    calls = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            calls.add(dep.call)
        stack.extend(dep.dependencies)
    return calls


def _route(path_suffix: str):
    from api.agents_self_improvement import router

    for r in router.routes:
        if r.path.endswith(path_suffix):
            return r
    raise AssertionError(f"route ending {path_suffix!r} not found")


def test_outcomes_endpoint_requires_authenticated_user():
    assert get_current_user in _dependency_calls(_route("/outcomes"))


def test_learned_strategies_endpoint_requires_authenticated_user():
    assert get_current_user in _dependency_calls(_route("/learned-strategies"))


def test_reset_learning_requires_admin():
    calls = _dependency_calls(_route("/reset-learning"))
    assert check_admin_permission in calls, "destructive reset must require admin"


def test_no_endpoint_is_unauthenticated():
    from api.agents_self_improvement import router

    for r in router.routes:
        calls = _dependency_calls(r)
        assert calls & {get_current_user, check_admin_permission}, f"{r.path} has no auth dependency"
