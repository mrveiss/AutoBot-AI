# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Creating an API key with no pepper answers 503 with no internals (#19120, #19117 review).

The real ``api/api_keys.py`` handler is loaded by path against stand-ins for its
neighbours; the service raises the real ``APIKeyPepperNotConfiguredError``.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parents[1]


class _Svc:
    def __init__(self, db, context):
        pass

    async def create_key(self, **kw):
        raise sys.modules["_svc_errors"].APIKeyPepperNotConfiguredError(
            "API-key pepper is not configured: add the secret 'x' on the SLM page /p"
        )


def test_create_without_pepper_is_503_without_internals(monkeypatch):
    errors = types.ModuleType("_svc_errors")

    class APIKeyServiceError(Exception):
        pass

    class APIKeyPepperNotConfiguredError(APIKeyServiceError):
        pass

    errors.APIKeyServiceError = APIKeyServiceError
    errors.APIKeyPepperNotConfiguredError = APIKeyPepperNotConfiguredError
    errors.APIKeyNotFoundError = type("APIKeyNotFoundError", (APIKeyServiceError,), {})
    errors.APIKeyService = _Svc
    monkeypatch.setitem(sys.modules, "_svc_errors", errors)

    star = lambda *names: SimpleNamespace(**{n: type(n, (BaseModel,), {}) for n in names})  # noqa: E731
    fakes = {
        "services.auth": SimpleNamespace(get_current_user=lambda: None),
        "user_management.database": SimpleNamespace(get_slm_db=lambda: None),
        "user_management.models.api_key": SimpleNamespace(API_KEY_SCOPES={}),
        "user_management.models.user": star("User"),
        "user_management.schemas.api_key": star(
            "APIKeyCreate",
            "APIKeyCreateResponse",
            "APIKeyListResponse",
            "APIKeyResponse",
            "APIKeyUpdate",
            "APIScopesResponse",
        ),
        "user_management.services.api_key_service": errors,
        "user_management.services.base_service": SimpleNamespace(TenantContext=lambda **kw: None),
    }
    for name, mod in fakes.items():
        m = types.ModuleType(name)
        m.__dict__.update(vars(mod))
        monkeypatch.setitem(sys.modules, name, m)
    spec = importlib.util.spec_from_file_location("_api_keys_19120", _ROOT / "api/api_keys.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    async def _user(*a, **k):
        return SimpleNamespace(id=1)

    mod._get_user_by_username = _user
    req = SimpleNamespace(name="n", scopes=[], description=None, expires_days=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.create_api_key(req, {"sub": "u"}, object()))
    assert exc.value.status_code == 503
    assert "pepper" not in exc.value.detail.lower() and "/p" not in exc.value.detail
