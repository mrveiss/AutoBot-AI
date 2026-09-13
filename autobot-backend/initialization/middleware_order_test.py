# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The order middleware actually runs in, not the order it is registered in (#15778).

`add_middleware` prepends, so the sequence of `configure_*` calls is the reverse
of the runtime order. A test that read the call order would have agreed with the
bug this file exists to catch: idempotency was registered after service auth,
which put it *outside* authentication, where `request.state.user` is unset. Every
caller then shared the "anonymous" replay scope, and a completed replay returned
before authentication ran at all -- one caller could be handed another caller's
cached creation response.

So the assertion is made against the built ASGI stack: `build_middleware_stack`
nests the layers the way a request traverses them, and walking `.app` from the
outside in reports what actually happens rather than what the source reads like.

Service auth registers a bare `BaseHTTPMiddleware` with a `dispatch=` function,
so layers are labelled by their dispatch function where they have one; matching
on `BaseHTTPMiddleware` alone would confuse three different layers.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from initialization.middleware import configure_middleware

AUDIT = "AuditMiddleware"
SERVICE_AUTH = "enforce_service_auth"
IDEMPOTENCY = "IdempotencyMiddleware"


def _runtime_order(app: FastAPI) -> list[str]:
    """Label every layer of the built stack, outermost first.

    Outermost is the layer a request reaches first; `user_middleware` order is
    an implementation detail of how the stack is assembled, the nesting is the
    behaviour.
    """
    labels: list[str] = []
    node = app.build_middleware_stack()
    while node is not None:
        dispatch = getattr(node, "dispatch_func", None)
        name = type(node).__name__
        labels.append(getattr(dispatch, "__name__", name) if name == "BaseHTTPMiddleware" else name)
        node = getattr(node, "app", None)
    return labels


@pytest.fixture(scope="module")
def order() -> list[str]:
    app = FastAPI()
    configure_middleware(app, allow_origins=["*"], enable_llm_awareness=False)
    return _runtime_order(app)


class TestEffectiveRuntimeOrder:
    def test_all_three_layers_are_present(self, order):
        """An absent layer would make every ordering assertion below vacuous."""
        for layer in (AUDIT, SERVICE_AUTH, IDEMPOTENCY):
            assert layer in order, f"{layer} never reached the stack; order was {order}"

    def test_service_auth_runs_before_idempotency(self, order):
        """The authorization gate.

        Idempotency namespaces its replay key by `request.state.user`. Running
        it ahead of authentication drops every caller into the shared
        "anonymous" scope, and a completed replay short-circuits -- so an
        unauthenticated caller would be handed a cached creation response
        belonging to someone else, without ever being authenticated.
        """
        assert order.index(SERVICE_AUTH) < order.index(
            IDEMPOTENCY
        ), f"idempotency runs before authentication; order was {order}"

    def test_audit_runs_before_idempotency(self, order):
        """A replayed creation must still appear in the audit trail; a replay
        short-circuits, so audit has to be the outer layer."""
        assert order.index(AUDIT) < order.index(
            IDEMPOTENCY
        ), f"a replayed creation would bypass the audit trail; order was {order}"

    def test_audit_runs_before_service_auth(self, order):
        """The relationship the previous comment got right, kept under test so
        fixing one ordering cannot silently break the other."""
        assert order.index(AUDIT) < order.index(SERVICE_AUTH)

    def test_the_order_is_not_the_registration_order(self, order):
        """The property that made the bug invisible.

        `configure_idempotency` is called *before* `configure_service_auth` in
        the source and runs *after* it at runtime. Asserting that inversion here
        is what stops someone "fixing" the call order back into the bug.
        """
        source_order = [IDEMPOTENCY, SERVICE_AUTH, AUDIT]
        runtime_order = sorted(source_order, key=order.index)

        assert runtime_order == [AUDIT, SERVICE_AUTH, IDEMPOTENCY]
