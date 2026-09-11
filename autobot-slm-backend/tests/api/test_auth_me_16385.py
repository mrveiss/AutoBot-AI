# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Direct test coverage for GET /api/auth/me (#16385).

#16374's nginx `auth_request` gate on `/autobot-api/` targets this route
(`api/auth.py`'s `get_current_user_info`) as its session-verify endpoint: 2xx
for a valid SLM session, 401/403 otherwise. Nothing exercised the route
directly before this file — other tests only touch `get_current_user`
indirectly, or extract `api/auth.py`'s pure helpers under a *stubbed* FastAPI
(see `test_auth_logout.py`), which overwrites decorated route functions like
`get_current_user_info` with a MagicMock and can never produce a real HTTP
status code.

Approach
--------
`services/auth.py` is loaded for REAL (exec'd by path, same technique
`test_auth_logout.py` uses) so `get_current_user` is the genuine dependency —
not a mock of it. Unlike that file, `fastapi`/`fastapi.security` are
deliberately left REAL (never stubbed) here: the whole point is to dispatch a
request through FastAPI's actual dependency-injection pipeline and observe
the real HTTP status code it produces, not to call the dependency function by
hand and inspect what it raises.

`get_current_user_info` itself is extracted from `api/auth.py` by AST (not
hand-copied) and exec'd into a fresh router bound to the real
`get_current_user` — so a future change to that route's body or decorator is
picked up automatically rather than silently drifting from the route this
test exists to guard. The rest of `api/auth.py` (login, users, logout,
refresh) is never imported: those routes' `response_model` unions need real
Pydantic stand-ins to survive real FastAPI's decoration-time validation, and
pulling that in is unrelated scope for a test of one route.

Covers (#16385 acceptance criteria):
- GET /api/auth/me returns 2xx for a valid session token
- GET /api/auth/me returns 403 for a missing token (HTTPBearer's own default)
- GET /api/auth/me returns 401 for an invalid token (rejected by
  get_current_user itself: malformed, and well-formed-but-wrong-signature)
"""

import ast
import importlib.util
import secrets
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typing_extensions import Annotated

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Module stubs — config first, then the light stand-ins services/auth.py
# needs at import time. See the module docstring for why fastapi itself is
# NOT in this list.
# ---------------------------------------------------------------------------
# #11478/#11794: snapshot sys.modules before the stub-heavy bootstrap (same
# pattern as test_auth_logout.py) so every forced stub below is rolled back
# once the objects this file actually uses have been extracted.
_PRE_BOOTSTRAP_MODULES = dict(sys.modules)

_SECRET_KEY = secrets.token_hex(32)
_WRONG_SECRET_KEY = secrets.token_hex(32)
_EXPIRE_MINUTES = 30

_STUB_MODULE_NAMES = (
    "models.schemas",
    "user_management.models.user",
    "services.jwks_verifier",
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

# ---------------------------------------------------------------------------
# Load real services.token_denylist, then real services.auth — both by path,
# same technique test_auth_logout.py uses.
# ---------------------------------------------------------------------------
_DENYLIST_PY = _BACKEND / "services" / "token_denylist.py"
_dl_spec = importlib.util.spec_from_file_location("services.token_denylist", _DENYLIST_PY)
_dl_mod = importlib.util.module_from_spec(_dl_spec)  # type: ignore[arg-type]
_dl_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]
sys.modules["services.token_denylist"] = _dl_mod  # type: ignore[assignment]

_AUTH_SERVICE_PY = _BACKEND / "services" / "auth.py"
_auth_spec = importlib.util.spec_from_file_location("services.auth", _AUTH_SERVICE_PY)
_auth_mod = importlib.util.module_from_spec(_auth_spec)  # type: ignore[arg-type]
_auth_spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]
sys.modules["services.auth"] = _auth_mod  # type: ignore[assignment]

get_current_user = _auth_mod.get_current_user
AuthService = _auth_mod.AuthService

# ---------------------------------------------------------------------------
# Extract the REAL production `/me` route by AST, exec it against a fresh
# router bound to the real get_current_user above. See the module docstring.
# ---------------------------------------------------------------------------
_AUTH_API_PY = _BACKEND / "api" / "auth.py"
_auth_api_tree = ast.parse(_AUTH_API_PY.read_text(encoding="utf-8"))
_me_route_node = next(
    node
    for node in _auth_api_tree.body
    if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_current_user_info"
)
_me_route_src = ast.unparse(ast.Module(body=[_me_route_node], type_ignores=[]))

import fastapi  # noqa: E402 -- real; deliberately not stubbed, see module docstring

_me_router = fastapi.APIRouter()
_me_ns: dict = {
    "router": _me_router,
    "Depends": fastapi.Depends,
    "Annotated": Annotated,
    "get_current_user": get_current_user,
    "dict": dict,
}
exec(compile(_me_route_src, str(_AUTH_API_PY), "exec"), _me_ns)  # nosec B102
get_current_user_info = _me_ns["get_current_user_info"]

# ---------------------------------------------------------------------------
# #11478/#11794: restore sys.modules to its pre-bootstrap state for exactly
# the modules this bootstrap managed. Only the objects captured above
# (_dl_mod, _auth_mod, get_current_user, AuthService, _me_router) are used
# from here on — see test_auth_logout.py for why this scoping matters.
# ---------------------------------------------------------------------------
for _k in list(sys.modules):
    if _k not in _BOOTSTRAP_MANAGED_MODULES:
        continue
    if _k not in _PRE_BOOTSTRAP_MODULES:
        del sys.modules[_k]
    elif sys.modules[_k] is not _PRE_BOOTSTRAP_MODULES[_k]:
        sys.modules[_k] = _PRE_BOOTSTRAP_MODULES[_k]
del _PRE_BOOTSTRAP_MODULES


# ---------------------------------------------------------------------------
# App under test — mounts ONLY the real /me route, at its real path.
# ---------------------------------------------------------------------------
app = fastapi.FastAPI()
app.include_router(_me_router, prefix="/api/auth")


def _mint_token(secret: str = _SECRET_KEY, **claims: object) -> str:
    """Mint an HS256 token. Defaults to the secret get_current_user verifies against."""
    data: dict = {"sub": "testuser", "admin": False, "role": "user"}
    data.update(claims)
    if secret == _SECRET_KEY:
        return AuthService().create_access_token(data=data)
    from autobot_shared.auth.jwt_core import encode_jwt  # noqa: PLC0415

    return encode_jwt(data, secret=secret, expires_delta=timedelta(minutes=_EXPIRE_MINUTES))


def _get_me(headers: dict | None = None):
    """Dispatch GET /api/auth/me with Redis calls patched to fail open.

    For a valid HS256 token, get_current_user's decode path consults the jti
    denylist (services.token_denylist.is_jti_revoked) and the password-epoch
    revocation check (autobot_shared...password_epoch.is_token_revoked_by_
    password_change); both already fail open when Redis is unavailable
    (#11443, #12924). Patching get_async_redis_client to return None exercises
    exactly that fail-open path deterministically, without a real network call
    racing or timing out.
    """
    from fastapi.testclient import TestClient

    import autobot_shared.user_management.password_epoch as password_epoch_mod

    with (
        patch.object(_dl_mod, "get_async_redis_client", AsyncMock(return_value=None)),
        patch.object(password_epoch_mod, "get_async_redis_client", AsyncMock(return_value=None)),
        TestClient(app) as client,
    ):
        return client.get("/api/auth/me", headers=headers or {})


class TestAuthMeValidToken:
    def test_valid_token_returns_2xx(self):
        token = _mint_token()
        resp = _get_me(headers={"Authorization": f"Bearer {token}"})
        assert 200 <= resp.status_code < 300, resp.text
        assert resp.json() == {"username": "testuser", "is_admin": False, "user_type": "slm_admin"}


class TestAuthMeMissingOrInvalidToken:
    def test_missing_token_returns_403(self):
        """No Authorization header: HTTPBearer's own auto_error default, not get_current_user."""
        resp = _get_me(headers=None)
        assert resp.status_code == 403, resp.text

    def test_garbage_token_returns_401(self):
        """A syntactically-invalid token is rejected by get_current_user itself."""
        resp = _get_me(headers={"Authorization": "Bearer not-a-real-jwt"})
        assert resp.status_code == 401, resp.text

    def test_wrong_signature_token_returns_401(self):
        """A well-formed HS256 token signed with the WRONG secret must still be rejected."""
        token = _mint_token(secret=_WRONG_SECRET_KEY)
        resp = _get_me(headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, resp.text
