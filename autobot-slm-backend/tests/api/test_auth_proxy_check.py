# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for GET /api/auth/proxy-check (#16374 round 3).

The nginx internal-key gate in autobot-slm.conf.j2 used to auth_request
against GET /api/auth/me, which only proves the caller holds a *valid* SLM
session -- not that the session is an admin one. A backend login token is a
valid SLM session by design (epic #10193), so any authenticated backend
user, read-only included, passed the gate and nginx attached the
admin-equivalent X-Internal-API-Key on their behalf. /api/auth/proxy-check
closes that: it depends on require_permission(Permission.ADMIN_SYSTEM), so
it is 204 only for a session whose role grants that permission, 403 for an
authenticated caller without it -- SUPERADMIN included, since it holds no
granular permissions (#13854) and is refused here as on every other
permission-gated SLM admin route -- and 401 for a missing or
invalid/expired token.

Bootstrap strategy
-------------------
services/auth.py (get_current_user, require_permission, auth_service) is
loaded for REAL, with REAL fastapi + fastapi.security -- unlike
tests/api/test_auth_logout.py, which stubs fastapi wholesale and therefore
never exercises an HTTPException-raising path (a MagicMock "HTTPException"
is not a real raisable exception; see that file's docstring). Only the
heavy, unrelated dependencies (config, models.schemas, sqlalchemy,
user_management.models.user) are stubbed -- exactly the ones services/auth.py
never calls at runtime for the paths under test, only type-hints.

api/auth.py's own proxy_check endpoint function is exercised separately,
under an *identity*-decorator fastapi stub (mirrors
tests/api/test_sso_auth.py's _identity_deco): router.get/router.post become
no-ops that return the function unchanged, so proxy_check survives exec as a
real coroutine even though api/auth.py's OTHER decorated endpoints
(login/refresh/etc., which need real models.schemas Pydantic models for
their response_model=... to validate under real fastapi) are not exercised.
That block snapshots and restores sys.modules around the exec so nothing
leaks into later test files (#11478/#11794/#14535).
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

_SECRET_KEY = "test-proxy-check-secret-key-32chars"  # pragma: allowlist secret
_EXPIRE_MINUTES = 30

# ---------------------------------------------------------------------------
# Real-load services/auth.py with REAL fastapi/fastapi.security.
#
# Unlike test_auth_logout.py's bootstrap, "fastapi" and "fastapi.security"
# are deliberately NOT in this stub set: get_current_user/require_permission
# must raise genuine, catchable fastapi.HTTPException instances with real
# status_code ints for this module's assertions to mean anything.
# ---------------------------------------------------------------------------
_PRE_BOOTSTRAP_MODULES = dict(sys.modules)

_STUB_MODULE_NAMES = (
    "models.schemas",
    "models",
    "models.database",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
)
_REAL_LOADED_MODULE_NAMES = ("services.token_denylist", "services.auth")
_BOOTSTRAP_MANAGED_MODULES = frozenset(("config", *_STUB_MODULE_NAMES, *_REAL_LOADED_MODULE_NAMES))

_cfg_mod = MagicMock()
_cfg_mod.settings = MagicMock()
_cfg_mod.settings.secret_key = _SECRET_KEY
_cfg_mod.settings.access_token_expire_minutes = _EXPIRE_MINUTES
sys.modules["config"] = _cfg_mod

for _mod_name in _STUB_MODULE_NAMES:
    sys.modules[_mod_name] = MagicMock()

_DENYLIST_PY = _BACKEND / "services" / "token_denylist.py"
_dl_spec = importlib.util.spec_from_file_location("services.token_denylist", _DENYLIST_PY)
_dl_mod = importlib.util.module_from_spec(_dl_spec)  # type: ignore[arg-type]
_dl_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]
sys.modules["services.token_denylist"] = _dl_mod  # type: ignore[assignment]

_AUTH_PY = _BACKEND / "services" / "auth.py"
_auth_spec = importlib.util.spec_from_file_location("services.auth", _AUTH_PY)
_auth_mod = importlib.util.module_from_spec(_auth_spec)  # type: ignore[arg-type]
_auth_spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]
sys.modules["services.auth"] = _auth_mod  # type: ignore[assignment]

for _k in list(sys.modules):
    if _k not in _BOOTSTRAP_MANAGED_MODULES:
        continue
    if _k not in _PRE_BOOTSTRAP_MODULES:
        del sys.modules[_k]
    elif sys.modules[_k] is not _PRE_BOOTSTRAP_MODULES[_k]:
        sys.modules[_k] = _PRE_BOOTSTRAP_MODULES[_k]
del _PRE_BOOTSTRAP_MODULES

get_current_user = _auth_mod.get_current_user
require_permission = _auth_mod.require_permission
Permission = _auth_mod.Permission
auth_service = _auth_mod.auth_service
security = _auth_mod.security  # module-level HTTPBearer() instance

# The gate GET /api/auth/proxy-check depends on (#16374 round 3).
_admin_system_gate = require_permission(Permission.ADMIN_SYSTEM)


def _mint_token(admin: bool, role: str, username: str = "tester") -> str:
    return auth_service.create_access_token(data={"sub": username, "admin": admin, "role": role})


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ---------------------------------------------------------------------------
# require_permission(ADMIN_SYSTEM)/get_current_user: the gate GET
# /api/auth/proxy-check depends on (#16374 round 3) -- admin/non-admin/
# superadmin/invalid/missing, real JWT round-trip.
# ---------------------------------------------------------------------------


class TestProxyCheckGate:
    @pytest.mark.asyncio
    async def test_admin_token_passes(self):
        """An admin session reaches proxy_check's body -- the endpoint's 204 path."""
        token = _mint_token(admin=True, role="admin", username="admin1")
        current_user = await get_current_user(_credentials(token))
        result = await _admin_system_gate(current_user)
        assert result["sub"] == "admin1"
        assert result["admin"] is True

    @pytest.mark.asyncio
    async def test_non_admin_user_role_token_gets_403(self):
        """An authenticated but non-admin session is rejected with 403, not 401."""
        token = _mint_token(admin=False, role="user", username="u1")
        current_user = await get_current_user(_credentials(token))
        with pytest.raises(HTTPException) as exc:
            await _admin_system_gate(current_user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_token_gets_403(self):
        """A read-only session -- the case the old /me gate let through -- is rejected with 403."""
        token = _mint_token(admin=False, role="readonly", username="ro1")
        current_user = await get_current_user(_credentials(token))
        with pytest.raises(HTTPException) as exc:
            await _admin_system_gate(current_user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_superadmin_token_gets_403(self):
        """SUPERADMIN holds no granular permissions (#13854), so it is refused
        here as on every other permission-gated SLM admin route -- despite
        the legacy "admin" flag it also carries."""
        token = _mint_token(admin=True, role="superadmin", username="sa1")
        current_user = await get_current_user(_credentials(token))
        with pytest.raises(HTTPException) as exc:
            await _admin_system_gate(current_user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_token_gets_401(self):
        """A garbage/unparseable token is rejected by get_current_user itself, with 401."""
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_credentials("not-a-real-jwt"))
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_gets_401(self):
        """An expired-but-otherwise-valid token is rejected, with 401."""
        from datetime import timedelta

        expired = auth_service.create_access_token(
            data={"sub": "expired1", "admin": True, "role": "admin"},
            expires_delta=timedelta(minutes=-5),
        )
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_credentials(expired))
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_credentials_gets_401(self):
        """No Authorization header at all -- fastapi's own HTTPBearer(), 401.

        Verifies the *actual* library behaviour rather than assuming it: an
        older FastAPI answered a missing bearer header with 403, which would
        have silently broken the "missing -> 401" half of the contract this
        module exists to pin. See services/auth.py's `security = HTTPBearer()`.
        """
        fake_request = SimpleNamespace(headers=SimpleNamespace(get=lambda key, default=None: default))
        with pytest.raises(HTTPException) as exc:
            await security(fake_request)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# proxy_check itself: extracted from a real (identity-decorated) exec of
# api/auth.py, reusing the SAME require_permission/get_current_user tested
# above (sys.modules["services.auth"] already holds _auth_mod at this point).
# ---------------------------------------------------------------------------

_AUTH_ROUTER_PY = _BACKEND / "api" / "auth.py"

_API_AUTH_STUB_MODULE_NAMES = (
    "config",
    "models.schemas",
    "models",
    "models.database",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "user_management.models.sso",
    "user_management.services",
    "user_management.database",
    "services.jwks_verifier",
    "services.database",
    "autobot_shared.proxy_utils",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "api.security",
)


def _identity_deco(*_args, **_kwargs):
    """A router.get/router.post replacement that returns the function unchanged.

    Mirrors tests/api/test_sso_auth.py's _identity_deco: lets a decorated
    endpoint stay a real, callable coroutine after exec, without triggering
    real fastapi's response_model validation against stubbed (MagicMock)
    Pydantic types on this module's OTHER endpoints (login/refresh/etc.),
    which is exactly why test_auth_logout.py stubs fastapi wholesale too --
    the difference here is only that .get/.post preserve identity instead of
    swallowing the function into a fresh MagicMock.
    """

    def decorator(fn):
        return fn

    return decorator


def _load_real_proxy_check():
    """Exec api/auth.py with an identity-decorator fastapi stub; return proxy_check."""
    pre = dict(sys.modules)

    fake_router = MagicMock()
    fake_router.get = _identity_deco
    fake_router.post = _identity_deco

    fastapi_stub = MagicMock()
    fastapi_stub.APIRouter = MagicMock(return_value=fake_router)
    # Depends(x) only needs to make the wrapped callable reachable again --
    # proxy_check's own dependants call it directly, never through FastAPI's
    # DI, so identity is all that's required.
    fastapi_stub.Depends = lambda dep: dep

    stubs = {name: MagicMock() for name in _API_AUTH_STUB_MODULE_NAMES}
    stubs["fastapi"] = fastapi_stub
    # fastapi.security stays real: _bearer = HTTPBearer() at module scope
    # must construct cleanly, and it does -- HTTPBearer() takes no required
    # args.
    #
    # services.auth is pinned to the SAME real module already exercised by
    # TestProxyCheckGate above, not a stub and not a fresh import -- a fresh
    # `from services.auth import ...` here would re-execute services/auth.py
    # against whatever "config" happens to be in sys.modules at that moment,
    # which by the time a test FUNCTION runs is no longer the secret_key
    # stub the top-level bootstrap set (that bootstrap restores sys.modules
    # before collection finishes, per #11478/#14535). Pinning it here is
    # simpler than re-deriving a second correct stub set, and keeps
    # proxy_check's require_permission(Permission.ADMIN_SYSTEM) identical to
    # the one under test above.
    stubs["services.auth"] = _auth_mod

    sys.modules.update(stubs)
    try:
        router_ns: dict = {"__name__": "api.auth_under_test_proxy_check", "__file__": str(_AUTH_ROUTER_PY)}
        src = _AUTH_ROUTER_PY.read_text(encoding="utf-8")
        exec(compile(src, str(_AUTH_ROUTER_PY), "exec"), router_ns)  # nosec B102
        return router_ns["proxy_check"]
    finally:
        for key in list(sys.modules):
            if key not in stubs:
                continue
            if key in pre:
                sys.modules[key] = pre[key]
            else:
                del sys.modules[key]


class TestProxyCheckEndpoint:
    @pytest.mark.asyncio
    async def test_admin_returns_none_the_204_body(self):
        """proxy_check returns None (empty body) for an admin caller -- FastAPI
        renders that as 204 via the route's status_code=204 declaration
        (asserted statically below, since the identity-decorator stub used to
        extract this function discards that kwarg)."""
        proxy_check = _load_real_proxy_check()
        token = _mint_token(admin=True, role="admin", username="admin2")
        current_user = await get_current_user(_credentials(token))
        gated = await _admin_system_gate(current_user)
        assert await proxy_check(_=gated) is None

    def test_route_declares_204_and_depends_on_admin_system_permission(self):
        """Static pin on the decorator: the two facts the runtime test above cannot see."""
        src = _AUTH_ROUTER_PY.read_text(encoding="utf-8")
        assert '@router.get("/proxy-check", status_code=status.HTTP_204_NO_CONTENT)' in src
        assert "Depends(require_permission(Permission.ADMIN_SYSTEM))" in src
