# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Builds the ``auth_middleware`` test stub (#14982, #13257).

Split out of ``conftest.py`` (#14982/#13257) so removing the module's
auto-vivifying ``__getattr__`` catch-all did not grow that file past its
grandfathered line-count ceiling. Behaviour is unchanged by the move; every
name below was already load-bearing before it lived here.

Every exported name must be a real callable (or class) with a real signature,
because routers capture them in ``Depends(...)`` at import time -- a bare
``MagicMock`` has signature ``(*args, **kwargs)``, and FastAPI's
``get_dependant()`` turns both into REQUIRED query parameters, 422ing every
request before the handler runs (#10472).

#14982: the module used to fall back to
``__getattr__ = lambda attr: MagicMock()`` for any name nobody stubbed above,
which made a missing stub indistinguishable from a working one --
``get_auth_middleware`` went unstubbed this way and twelve tests across three
shards asserted non-admin behaviour and passed on a MagicMock's stringified
repr rather than the auth logic they name. The catch-all is gone; an
unstubbed name now raises ``AttributeError`` naming itself, and
``repo_tests/conftest_stub_no_autovivify_test.py`` pins that it cannot return.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

# Module scope, deliberately. ``from __future__ import annotations`` above makes
# every annotation a lazy string, and FastAPI resolves ``get_current_user``'s
# against THIS MODULE's globals when it builds the OpenAPI schema. Imported
# inside the factory it was a local name, so the annotation stayed an
# unresolved ForwardRef and every schema build died with
# "`TypeAdapter[Annotated[ForwardRef('_FastAPIRequest') ...]]` is not fully
# defined" -- which took out repo_tests/conftest.py's SDK request oracle.
from fastapi import Request as _FastAPIRequest


def _current_user_payload() -> dict:
    """The dict shape ``get_current_user`` and ``get_user_from_request`` both hand back.

    Split out so it can be reused by a genuinely ``async def`` dependency
    (#13257, matching ``auth_middleware.py:856``'s real contract) and by the
    *sync* ``get_user_from_request`` mock below (its real counterpart,
    ``auth_middleware.py:729``, is not a coroutine) without either one
    awaiting the other's return value.
    """
    return {
        "username": "test-user",
        "user_id": "test-user",
        "role": "admin",
        "auth_method": "stub",
    }


def _auth_stub_getattr(attr: str):
    """#14982: name any missing stub instead of handing out a MagicMock.

    Dunders are unaffected: ``__doc__``/``__loader__``/``__name__``/
    ``__package__``/``__spec__`` are real entries in every
    ``types.ModuleType.__dict__`` and ``__path__`` is set explicitly by
    ``install()``, so none of them ever reach ``__getattr__`` -- this never
    needs to special-case them.
    """
    raise AttributeError(
        f"auth_middleware stub has no {attr!r} -- add a real stub for it in "
        "testkit/auth_middleware_stub.py; it must not fall through to an "
        "auto-vivifying MagicMock (#14982)."
    )


def build_auth_middleware_stub() -> types.ModuleType:
    """Construct the ``auth_middleware`` stub module. Does not touch ``sys.modules``."""
    auth_stub = types.ModuleType("auth_middleware")
    auth_stub.__path__ = []  # type: ignore[attr-defined]
    auth_stub.__package__ = "auth_middleware"

    # get_current_user: ``async def`` (#13257) -- the real function is a
    # coroutine (``auth_middleware.py:856``); PR #13254 deliberately kept this
    # stub sync, which left ``await get_current_user(...)`` broken at five
    # call sites (``api/openai_compat.py``, the four ``codebase_analytics``
    # endpoint modules) -- ``await <dict>`` raises ``TypeError`` there. Making
    # it a coroutine function also makes ``unittest.mock.patch`` autodetect
    # async and hand out an ``AsyncMock`` for every
    # ``@patch("...get_current_user")`` site (patch() has done this since
    # Python 3.8), so ``mock.return_value = {...}`` keeps working unchanged
    # everywhere it's used today. The ONE caller that is NOT ``patch()``-based
    # -- ``tests/integration/test_execution_snapshot_api.py``'s FastAPI
    # ``dependency_overrides`` delegate -- could not stay a bare sync lambda
    # calling this coroutine function without awaiting it; it was updated in
    # lockstep in the same commit to await it.
    # The ``request`` parameter is annotated ``Request`` so FastAPI injects it
    # instead of treating it as a request field, and defaults to None so
    # direct ``get_current_user()`` call sites keep working.
    async def _get_current_user_stub(request: _FastAPIRequest = None) -> dict:  # type: ignore[assignment]
        return _current_user_payload()

    auth_stub.get_current_user = _get_current_user_stub  # type: ignore[attr-defined]

    # check_admin_permission must be a proper no-arg callable so FastAPI can
    # inspect its signature at route-registration time without producing
    # spurious (*args, **kwargs) query parameters (#10472).
    def _check_admin_permission_stub():
        return True

    auth_stub.check_admin_permission = _check_admin_permission_stub  # type: ignore[attr-defined]

    # require_device_jwt is a dependency FACTORY (GH#9493/#11736) invoked at
    # module import time -- it must return a no-arg callable so FastAPI can
    # inspect the signature at route registration without producing spurious
    # (*args, **kwargs) query parameters (same rationale as above, #10472).
    def _require_device_jwt_stub(min_scope: str = "read"):
        def _device_jwt_dep():
            return {
                "username": "device:stub-device",
                "user_id": "stub-user",
                "role": "device",
                "device_id": "00000000-0000-0000-0000-000000000000",
                "scope": min_scope,
                "auth_method": "device_jwt",
            }

        return _device_jwt_dep

    auth_stub.require_device_jwt = _require_device_jwt_stub  # type: ignore[attr-defined]

    # get_auth_middleware must yield a middleware whose get_user_from_request()
    # returns a REAL dict -- #13253's rule applied to this module's sibling
    # accessor, which it missed (#14944, the gap #14982's guard now pins).
    #
    # Only get_user_from_request is pinned. The middleware carries a dozen
    # other attributes (create_jwt_token, security_layer, enable_auth, ...)
    # that tests legitimately auto-mock, so the object stays a MagicMock and
    # only the value whose *shape* is load-bearing is made real -- a fresh
    # dict per call, so a test mutating it cannot leak into the next.
    # get_user_from_request is sync on the real class
    # (``auth_middleware.py:729``), so its side_effect calls the shared sync
    # payload helper directly rather than the (now coroutine)
    # _get_current_user_stub.
    auth_middleware_stub_instance = MagicMock()
    auth_middleware_stub_instance.get_user_from_request.side_effect = lambda *_args, **_kwargs: _current_user_payload()

    def _get_auth_middleware_stub():
        return auth_middleware_stub_instance

    auth_stub.get_auth_middleware = _get_auth_middleware_stub  # type: ignore[attr-defined]

    # authenticate_websocket must be a real coroutine, matching
    # ``auth_middleware.py:1061`` (#14982). Default is a fail-closed ``None``
    # ("no authenticated user") rather than a MagicMock -- every websocket
    # route treats ``None`` as "reject the connection", so a test that forgets
    # to patch this gets a loud auth failure instead of a silently-truthy mock
    # object sailing through as if it were a user.
    async def _authenticate_websocket_stub(websocket) -> dict | None:
        return None

    auth_stub.authenticate_websocket = _authenticate_websocket_stub  # type: ignore[attr-defined]

    # verify_internal_api_key must be a real callable returning a real bool
    # (#14982), matching ``auth_middleware.py:959``. Default is ``False`` --
    # fail-closed, same rationale as authenticate_websocket above -- so an
    # unpatched caller never treats an absent internal key as trusted.
    def _verify_internal_api_key_stub(provided: str | None = None) -> bool:
        return False

    auth_stub.verify_internal_api_key = _verify_internal_api_key_stub  # type: ignore[attr-defined]

    # AuthenticationMiddleware must be a real class (#14982), matching
    # ``auth_middleware.py:44``. No production or test code constructs it
    # through this stub today (every consumer goes through
    # get_auth_middleware above, or through the real class via
    # ``real_auth_middleware`` / ``load_real_auth_middleware`` in
    # tests/conftest.py, which bypasses this stub entirely) -- it is here so
    # the name itself cannot resolve to a MagicMock, consistent with every
    # other export in this block.
    class _AuthenticationMiddlewareStub:
        def __init__(self, *_args, **_kwargs):
            pass

    auth_stub.AuthenticationMiddleware = _AuthenticationMiddlewareStub  # type: ignore[attr-defined]

    auth_stub.__getattr__ = _auth_stub_getattr  # type: ignore[attr-defined]
    return auth_stub


def install_auth_middleware_stub() -> None:
    """Install the stub into ``sys.modules`` unless something is there already."""
    if "auth_middleware" not in sys.modules:
        sys.modules["auth_middleware"] = build_auth_middleware_stub()
