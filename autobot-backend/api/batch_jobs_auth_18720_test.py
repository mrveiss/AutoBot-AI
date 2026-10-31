# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The batch-jobs literals made reachable by #18720 stay authenticated.

While ``GET /status`` and ``GET /chat-init`` were shadowed by ``GET /{job_id}``, an anonymous
request hit that route's ``get_current_user`` and got 401. Declaring them first must not
open them: ``/chat-init`` returns every chat id with its timestamps. ``POST /load`` (never
shadowed, anonymous on main too) runs several API calls on the caller's behalf, so it is gated in
the same change (#18718).
"""

import pytest

import api.batch_jobs as batch_jobs
from auth_middleware import get_current_user


def _route(path: str, method: str):
    for route in batch_jobs.router.routes:
        if route.path.endswith(path) and method in route.methods:
            return route
    raise AssertionError(f"{method} {path} not found in api.batch_jobs")


@pytest.mark.parametrize(
    ("path", "method"), [("/status", "GET"), ("/chat-init", "GET"), ("/chat-init", "POST"), ("/load", "POST")]
)
def test_reachable_batch_literal_requires_an_authenticated_user(path: str, method: str) -> None:
    calls = {dep.call for dep in _route(path, method).dependant.dependencies}
    assert get_current_user in calls, f"{method} {path} has no get_current_user dependency"


def test_the_literals_are_declared_before_the_job_route() -> None:
    order = [route.path for route in batch_jobs.router.routes]
    job_route = next(i for i, p in enumerate(order) if p.endswith("/{job_id}"))
    assert all(next(i for i, p in enumerate(order) if p.endswith(lit)) < job_route for lit in ("/status", "/chat-init"))
