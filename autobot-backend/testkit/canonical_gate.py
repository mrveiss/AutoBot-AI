# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run user_management's ``get_current_user`` through the REAL canonical gate (#18688).

``api.user_management.dependencies.get_current_user`` delegates to
``auth_middleware.get_current_user``. Under pytest ``auth_middleware`` is the
conftest stub (``testkit/auth_middleware_stub.py``), whose ``get_current_user``
answers ``test-user`` for everyone -- so a test that wants a REAL refusal
(no credential, a revoked token, a service key) has to point the delegate at the
real module and give that module the middleware it should see.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

_DELEGATE = "api.user_management.dependencies._canonical_get_current_user"
_HUMAN_DELEGATE = "api.user_management.dependencies._canonical_resolve_human_user"


def no_user_middleware() -> MagicMock:
    """A middleware that resolves no user by any route: JWT, session, run JWT or device JWT."""
    middleware = MagicMock()
    middleware.get_user_from_request.return_value = None
    middleware._extract_user_from_run_jwt = AsyncMock(return_value=None)
    middleware._extract_user_from_device_jwt = AsyncMock(return_value=None)
    return middleware


def install_canonical_resolver(monkeypatch, target: str, middleware):
    """Bind *target* (a module's ``resolve_human_user``) to the REAL one, seeing *middleware*.

    The real resolver applies password-change revocation to a JWT user (#18688), so a
    test that wants it to pass hands in a user whose ``auth_method`` is not ``jwt``, or
    patches the epoch check. Returns the real module.
    """
    from tests.conftest import load_real_auth_middleware  # noqa: PLC0415

    real = load_real_auth_middleware()
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(target, real.resolve_human_user)
    return real


@contextmanager
def canonical_resolver(target: str, middleware):
    """Within the block, *target* is the REAL ``resolve_human_user``, seeing *middleware*."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        yield install_canonical_resolver(monkeypatch, target, middleware)


def install_canonical_gate(monkeypatch, middleware):
    """Point the delegate at the real gate, seeing *middleware*. Returns the real module."""
    real = install_canonical_resolver(monkeypatch, _HUMAN_DELEGATE, middleware)
    monkeypatch.setattr(_DELEGATE, real.get_current_user)
    return real


@contextmanager
def unauthenticated_canonical_gate():
    """Within the block, the real canonical gate sees a caller with no credential."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        install_canonical_gate(monkeypatch, no_user_middleware())
        yield
