# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
TDD tests for services/token_denylist.py + jti integration in auth.

Covers:
- jti present in minted tokens
- (the store itself -- PostgreSQL since #18663 -- is tested in test_auth_revocation_store_18663.py)
- decode_token_async rejects revoked HS256 jti
- decode_token_async accepts non-revoked HS256 token
- decode_token_async denies (401) when the jti-denylist check cannot run
- decode_token_async denies (401) when the password-epoch check cannot run
- decode_token_async accepts a valid token when both checks succeed (control)
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Pre-populate sys.modules stubs BEFORE loading the real service modules via
# spec_from_file_location so their top-level imports resolve cleanly.
#
# #13084: snapshot sys.modules (and the ``services`` module's own
# ``token_denylist`` attribute) BEFORE the stub-heavy bootstrap so everything
# can be rolled back afterward. Previously ``sys.modules["config"] = MagicMock()``
# and the stub loop below ran unconditionally with no restore — in a
# whole-backend sweep this silently shadowed the REAL ``config`` module for
# every test collected afterward in the same session, including
# ``autobot-backend/utils/thread_safety_test.py::test_concurrent_config_saves``,
# whose own config-file redirect then resolved against this throwaway stub
# instead of the real ``ConfigService`` singleton and wrote unpatched to the
# developer's real ``config/config.yaml`` (#13083, the severity bar for this
# issue).
# ---------------------------------------------------------------------------
# #16387: import the REAL fastapi (+ fastapi.security) before the snapshot
# below, so the stub loop's `if _mod_name not in sys.modules` guard for those
# two names is already satisfied and never replaces them with a MagicMock.
# Unlike api/auth.py (test_auth_logout.py's target), services/auth.py has no
# decorated routes or response models, so there is no FastAPIError risk from
# using the real package here -- and the fail-closed tests below need a real,
# raise-able ``HTTPException`` from ``decode_token_async``, not a MagicMock
# call that would raise TypeError instead of the intended 401.
import fastapi  # noqa: E402,F401
import fastapi.security  # noqa: E402,F401

_PRE_BOOTSTRAP_MODULES = dict(sys.modules)
_PRE_BOOTSTRAP_SERVICES_HAD_DENYLIST = "services" in sys.modules and hasattr(sys.modules["services"], "token_denylist")

_SECRET_KEY = "test-secret-key-for-jti-tests-32chars"
_EXPIRE_MINUTES = 30

# config.settings stub — ensure a real MagicMock is in place with the test key
_cfg_mod = MagicMock()
_cfg_mod.settings = MagicMock()
_cfg_mod.settings.secret_key = _SECRET_KEY
_cfg_mod.settings.access_token_expire_minutes = _EXPIRE_MINUTES
sys.modules["config"] = _cfg_mod

_settings = _cfg_mod.settings

for _mod_name in [
    "models.schemas",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "user_management.services",
    "services.jwks_verifier",
    "fastapi",
    "fastapi.security",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# autobot_shared.auth — real modules (on path)
from autobot_shared.auth.jwt_core import decode_jwt_or_none  # noqa: E402

# sqlalchemy stubs (auth.py imports select + AsyncSession)
for _sa in ["sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"]:
    if _sa not in sys.modules:
        sys.modules[_sa] = MagicMock()

# ---------------------------------------------------------------------------
# Load services/token_denylist.py directly via spec
# ---------------------------------------------------------------------------
_DENYLIST_PY = _BACKEND / "services" / "token_denylist.py"
_dl_spec = importlib.util.spec_from_file_location("_token_denylist_under_test", _DENYLIST_PY)
_dl_mod = importlib.util.module_from_spec(_dl_spec)  # type: ignore[arg-type]
_dl_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]

revoke_jti = _dl_mod.revoke_jti
is_jti_revoked = _dl_mod.is_jti_revoked

# Register the real token_denylist module under both canonical names so that
# `from services.token_denylist import ...` inside auth.py resolves correctly
# when auth.py is exec'd below (the root conftest stubs 'services' as a
# MagicMock package; we overwrite the sub-module slot here).
sys.modules["services.token_denylist"] = _dl_mod  # type: ignore[assignment]
setattr(sys.modules["services"], "token_denylist", _dl_mod)

# ---------------------------------------------------------------------------
# Load services/auth.py directly via spec so jti enforcement is real code
# ---------------------------------------------------------------------------
_AUTH_PY = _BACKEND / "services" / "auth.py"
_auth_spec = importlib.util.spec_from_file_location("_auth_under_test", _AUTH_PY)
_auth_mod = importlib.util.module_from_spec(_auth_spec)  # type: ignore[arg-type]
_auth_spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]

AuthService = _auth_mod.AuthService

# ---------------------------------------------------------------------------
# #13084: restore the pre-bootstrap sys.modules state (see snapshot above).
# Tests only use the module/attribute references captured above (_dl_mod,
# _auth_mod, revoke_jti, is_jti_revoked, AuthService), so none
# of the forced stubs — including ``config`` — may outlive this module's
# import.
# ---------------------------------------------------------------------------
for _k in list(sys.modules):
    if _k not in _PRE_BOOTSTRAP_MODULES:
        del sys.modules[_k]
    elif sys.modules[_k] is not _PRE_BOOTSTRAP_MODULES[_k]:
        sys.modules[_k] = _PRE_BOOTSTRAP_MODULES[_k]
del _PRE_BOOTSTRAP_MODULES

if not _PRE_BOOTSTRAP_SERVICES_HAD_DENYLIST and "services" in sys.modules:
    if hasattr(sys.modules["services"], "token_denylist"):
        delattr(sys.modules["services"], "token_denylist")


# ---------------------------------------------------------------------------
# token_denylist: revoke_jti
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# token_denylist: is_jti_revoked
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# jti in minted tokens
# ---------------------------------------------------------------------------


class TestJtiInMintedToken:
    def test_create_access_token_includes_jti(self):
        """Every SLM HS256 token must carry a 'jti' claim."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "alice", "admin": False, "role": "user"})
        claims = decode_jwt_or_none(token, secret=_SECRET_KEY)
        assert claims is not None
        assert "jti" in claims
        assert isinstance(claims["jti"], str)
        assert len(claims["jti"]) > 0

    def test_each_token_gets_unique_jti(self):
        service = AuthService()
        payload = {"sub": "alice", "admin": False, "role": "user"}
        t1 = service.create_access_token(data=payload)
        t2 = service.create_access_token(data=payload)
        c1 = decode_jwt_or_none(t1, secret=_SECRET_KEY)
        c2 = decode_jwt_or_none(t2, secret=_SECRET_KEY)
        assert c1 is not None and c2 is not None
        assert c1["jti"] != c2["jti"]


# ---------------------------------------------------------------------------
# decode_token_async jti revocation enforcement
# ---------------------------------------------------------------------------


class TestDecodeTokenAsyncRevocation:
    @pytest.mark.asyncio
    async def test_revoked_jti_returns_none(self):
        """decode_token_async must return None when jti is denylisted."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "bob", "admin": False, "role": "user"})

        # Patch is_jti_revoked directly on the loaded auth module namespace
        with patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=True)):
            result = await service.decode_token_async(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_non_revoked_jti_decodes_correctly(self):
        """decode_token_async must succeed for a valid, non-revoked token."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "carol", "admin": True, "role": "admin"})

        # The epoch check fails closed without Redis (#16411), so it is stubbed too.
        with (
            patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)),
            patch.object(_auth_mod, "is_token_revoked_by_password_change", new=AsyncMock(return_value=False)),
        ):
            result = await service.decode_token_async(token)

        assert result is not None
        assert result["sub"] == "carol"

    @pytest.mark.asyncio
    async def test_both_checks_healthy_accepts_valid_token(self):
        """Control case (#16387): with both revocation checks healthy and
        returning "not revoked", a valid token is still accepted."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "dave", "admin": False, "role": "user"})

        with (
            patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)),
            patch.object(_auth_mod, "is_token_revoked_by_password_change", new=AsyncMock(return_value=False)),
        ):
            result = await service.decode_token_async(token)

        assert result is not None
        assert result["sub"] == "dave"

    @pytest.mark.asyncio
    async def test_jti_denylist_exception_denies_token(self):
        """#16387: when is_jti_revoked raises, decode_token_async fails
        CLOSED -- refused with 503 (store unavailable, #18892), never a fail-open pass-through."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "eve", "admin": False, "role": "user"})

        with patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(side_effect=ConnectionError("redis down"))):
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await service.decode_token_async(token)

        assert exc_info.value.status_code == fastapi.status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_password_epoch_exception_denies_token(self):
        """#16387: when is_token_revoked_by_password_change raises,
        decode_token_async fails CLOSED -- 503 (#18892), never a fail-open pass-through."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "frank", "admin": False, "role": "user"})

        with (
            patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)),
            patch.object(
                _auth_mod,
                "is_token_revoked_by_password_change",
                new=AsyncMock(side_effect=TimeoutError("redis timed out")),
            ),
        ):
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await service.decode_token_async(token)

        assert exc_info.value.status_code == fastapi.status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_a_real_epoch_store_error_denies_token(self):
        """#16659: the epoch store's own Redis read raising reaches the REAL
        get_password_epoch, which raises RevocationCheckUnavailable, and
        decode_token_async denies (503, #18892). Unlike the test above, nothing between
        decode_token_async and the Redis client is mocked."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "grace", "admin": False, "role": "user"})

        with (
            patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)),
            _epoch_store_answering(error=ConnectionError("redis refused")),
        ):
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await service.decode_token_async(token)

        assert exc_info.value.status_code == fastapi.status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_a_healthy_epoch_store_with_no_marker_accepts_token(self):
        """Control for the test above: the same wiring with a store that answers
        "no marker" admits the token, so the 401 there comes from the Redis
        error, not from the fake failing to reach the real helper."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "grace", "admin": False, "role": "user"})

        with (
            patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)),
            _epoch_store_answering(),
        ):
            result = await service.decode_token_async(token)

        assert result is not None
        assert result["sub"] == "grace"


def _epoch_store_answering(error: Exception | None = None):
    """Patch the REAL password-epoch module's Redis client with one whose get()
    returns no marker, or raises *error* (#16659)."""
    import autobot_shared.user_management.password_epoch as password_epoch_mod

    client = MagicMock()
    client.get = AsyncMock(return_value=None, side_effect=error)
    return patch.object(password_epoch_mod, "get_async_redis_client", AsyncMock(return_value=client))


# ---------------------------------------------------------------------------
# token_denylist: bounded Redis access + negative cache (#11443)
# ---------------------------------------------------------------------------
