# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An MFA-pending temp token is not a session (#18321).

The MFA challenge token (``sub``, ``mfa_pending``, ``user_id``, ``admin``) is minted
BEFORE the second factor. ``get_current_user`` returned it as an ordinary caller, so a
platform admin's temp token passed ``require_admin``. ``get_current_user`` now refuses
any purpose-bound token (the shared #17049 predicate) with 401, which covers every
route depending on it. ``/mfa/verify-login`` is the one place that accepts the temp
token, and it reads it with ``decode_token``, not ``get_current_user``.
"""

import asyncio
import importlib.util
import secrets
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402

from autobot_shared.auth.permissions import Permission  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))
_MFA_PY = Path(__file__).resolve().parents[2] / "api" / "mfa.py"
_USER_ID = str(uuid.uuid4())


def _temp_token(admin: bool = True) -> str:
    """Exactly what api/auth.py mints for the MFA challenge."""
    data = {"sub": "admin1", "mfa_pending": True, "user_id": _USER_ID, "admin": admin}
    return _auth.auth_service.create_access_token(data=data, expires_delta=timedelta(minutes=5))


def _full_token() -> str:
    return _auth.auth_service.create_access_token(data={"sub": "admin1", "admin": True, "role": "admin"})


@pytest.fixture(autouse=True)
def _not_revoked():
    with (
        patch.object(_auth, "is_jti_revoked", AsyncMock(return_value=False)),
        patch.object(_auth, "is_token_revoked_by_password_change", AsyncMock(return_value=False)),
    ):
        yield


def _app() -> fastapi.FastAPI:
    app = fastapi.FastAPI()

    @app.get("/admin")
    async def admin(caller: dict = fastapi.Depends(_auth.require_admin)):
        return {"sub": caller["sub"]}

    @app.get("/permission")
    async def permission(caller: dict = fastapi.Depends(_auth.require_permission(Permission.ADMIN_SYSTEM))):
        return {"sub": caller["sub"]}

    @app.get("/session")
    async def session(caller: dict = fastapi.Depends(_auth.get_current_user)):
        return {"sub": caller["sub"]}

    return app


@pytest.mark.parametrize("path", ["/admin", "/permission", "/session"])
def test_a_temp_token_is_refused_with_401_everywhere(path):
    response = TestClient(_app()).get(path, headers={"Authorization": f"Bearer {_temp_token()}"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/admin", "/permission", "/session"])
def test_the_control_a_full_token_works_everywhere(path):
    response = TestClient(_app()).get(path, headers={"Authorization": f"Bearer {_full_token()}"})
    assert response.status_code == 200 and response.json() == {"sub": "admin1"}


def test_contrast_without_the_choke_point_the_temp_token_passes_require_admin():
    """What main did: the token decodes cleanly and carries the admin flag ``require_admin`` reads."""
    claims = asyncio.run(_auth.auth_service.decode_token_async(_temp_token()))
    assert claims["mfa_pending"] is True
    assert asyncio.run(_auth.require_admin(claims)) is claims


def _load_verify_login():
    """Exec api/mfa.py with identity route decorators and its DB-facing imports stood in for."""
    router = MagicMock(get=lambda *a, **k: (lambda f: f), post=lambda *a, **k: (lambda f: f))
    fastapi_stub = ModuleType("fastapi")
    fastapi_stub.APIRouter = MagicMock(return_value=router)
    fastapi_stub.Depends, fastapi_stub.HTTPException, fastapi_stub.status = (
        fastapi.Depends,
        fastapi.HTTPException,
        fastapi.status,
    )
    names = (
        "models.schemas", "user_management.database", "user_management.models.user",
        "user_management.schemas.mfa", "user_management.services.base_service",
        "user_management.services.mfa_service", "sqlalchemy", "sqlalchemy.ext.asyncio",
    )  # fmt: skip
    stubs = {name: MagicMock() for name in names}
    stubs.update({"fastapi": fastapi_stub, "services.auth": _auth})
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("mfa_under_test_18321", _MFA_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_mfa_verify_login_still_accepts_the_temp_token():
    mfa = _load_verify_login()
    user = SimpleNamespace(id=uuid.UUID(_USER_ID), username="admin1", is_platform_admin=True)
    mfa.MFAService = MagicMock(return_value=MagicMock(verify_login=AsyncMock(return_value=True)))
    with (
        patch.object(mfa, "_get_user_by_id", AsyncMock(return_value=user)),
        patch.object(_auth.auth_service, "create_access_token", wraps=_auth.auth_service.create_access_token) as mint,
    ):
        asyncio.run(mfa.verify_mfa_login(request=SimpleNamespace(code="123456"), temp_token=_temp_token(), db=None))
    assert mint.call_args.kwargs["data"]["role"] == "admin"


def test_mfa_verify_login_refuses_a_full_token():
    mfa = _load_verify_login()
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(mfa.verify_mfa_login(request=SimpleNamespace(code="1"), temp_token=_full_token(), db=None))
    assert exc.value.status_code == 401
