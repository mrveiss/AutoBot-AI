# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every credential kind, resolved by production code, for route tests (#17042, #17052).

Each kind is presented the way a real client presents it and resolved by the
real ``AuthenticationMiddleware`` extraction, the real async
``auth_middleware.get_current_user`` and the real sync
``api.user_management.dependencies.get_current_user``. Only storage is stood in
for: the session store, the Redis password-revocation check, and the run/device
token validators, which still verify real signatures, using whichever secret
the case's deployment configures (a dedicated secret, or the platform-key
fallback that ``run_jwt._secret()`` and ``device_jwt._secret()`` both have).

Each forged or non-login token also carries a valid user id and org id, so only
the human-decider check (#17042) stands between it and a recorded decision.
"""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import api.user_management.dependencies as user_deps
from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE
from autobot_shared.auth.jwt_core import decode_jwt, encode_jwt

PLATFORM_SECRET = "p" * 40  # the platform user-session key
RUN_SECRET = "r" * 40
DEVICE_SECRET = "d" * 40
RUN_AUD, DEVICE_AUD = "autobot-run", "autobot-device"
INTERNAL_KEY = "internal-service-key-for-tests"
CALLER = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER = uuid.UUID("22222222-2222-2222-2222-222222222222")
ORG = uuid.UUID("33333333-3333-3333-3333-333333333333")
SESSION_ID = "session-17042"

#: The person every human kind resolves to: username ``alice``.
HUMAN = {
    "username": "alice",
    "role": "user",
    "email": "alice@example.test",
    "user_id": str(CALLER),
    "org_id": str(ORG),
}
ADVANTAGE = {"user_id": str(CALLER), "org_id": str(ORG)}
LOGIN = {**HUMAN, "token_type": LOGIN_TOKEN_TYPE}
DEVICE_CLAIMS = {"aud": DEVICE_AUD, "device_id": "dev-1", "scope": "write", **ADVANTAGE}
#: A run JWT's real shape (services/run_jwt.py): no user identity claim at all.
RUN_CLAIMS = {"aud": RUN_AUD, "run_id": "run-1", "agent_id": "agent-1", "tenant_id": str(ORG), "scope": []}


def bearer(claims: dict, secret: str = PLATFORM_SECRET) -> dict:
    return {"Authorization": f"Bearer {encode_jwt(claims, secret=secret, expiry_hours=1)}"}


def credentials() -> dict:
    """Credential kind -> request headers, as each is actually presented."""
    return {
        "login_jwt": bearer(LOGIN),
        # A person's login minted before 2026-09-18: no token_type, so no positive
        # evidence it is a login. Refused until the 24h token is re-issued.
        "pre_17042_login_jwt": bearer(HUMAN),
        "session": {"X-Session-ID": SESSION_ID},
        "internal_service_key": {"X-Internal-API-Key": INTERNAL_KEY},
        "run_jwt": bearer(RUN_CLAIMS, RUN_SECRET),
        # RUN_JWT_SECRET unset: run_jwt falls back to the platform key too.
        "run_jwt_on_platform_key": bearer(RUN_CLAIMS),
        "device_jwt": bearer(DEVICE_CLAIMS, DEVICE_SECRET),
        # DEVICE_JWT_SECRET unset: device_jwt falls back to the platform key.
        "device_jwt_on_platform_key": bearer(DEVICE_CLAIMS),
        # SLM_SECRET_KEY aligned with the platform key: its pre-MFA temp token.
        "slm_mfa_pending_token": bearer({"sub": "alice", "mfa_pending": True, "admin": True, **ADVANTAGE}),
        # The token the backend mints for itself to call the SLM.
        "slm_service_token": bearer({"sub": "service:backend", "service": True, **ADVANTAGE}),
        "dev_header": {"X-User-Role": "admin", "X-Organization-Id": str(ORG)},
        "auth_disabled": {"X-Organization-Id": str(ORG)},
        "llc_agent_api_key": {"Authorization": "Bearer llc-agent-key-not-a-jwt"},
    }


HUMAN_KINDS = ("login_jwt", "session")
REFUSED_BY_HUMAN_CHECK = "human"

#: (status, refuser) per non-human kind on a decision route behind the async
#: ``get_current_user``, outside the run/device path allow-lists. "human" means
#: the #17042 check refused it, so a test asserts its detail, not just a status.
ASYNC_ROUTE_EXPECTED = {
    "pre_17042_login_jwt": (403, REFUSED_BY_HUMAN_CHECK),
    "internal_service_key": (403, REFUSED_BY_HUMAN_CHECK),
    "run_jwt": (403, "run-JWT path allow-list"),
    "run_jwt_on_platform_key": (403, "run-JWT path allow-list"),
    "device_jwt": (403, "device-JWT path allow-list"),
    "device_jwt_on_platform_key": (403, REFUSED_BY_HUMAN_CHECK),
    "slm_mfa_pending_token": (403, REFUSED_BY_HUMAN_CHECK),
    "slm_service_token": (403, REFUSED_BY_HUMAN_CHECK),
    "dev_header": (403, REFUSED_BY_HUMAN_CHECK),
    "auth_disabled": (403, REFUSED_BY_HUMAN_CHECK),
    "llc_agent_api_key": (401, "resolution"),
}


def token_validator(secret_of, audience: str):
    """The run/device validator, verifying with whichever secret the deployment configured."""

    async def _validate(token: str) -> dict:
        return decode_jwt(token, secret_of(), audience=audience)

    return _validate


def real_middleware(real_auth_middleware, *, enable_auth: bool):
    """The real AuthenticationMiddleware, keyed to the test secrets, with one session stored."""
    cls = real_auth_middleware.AuthenticationMiddleware
    middleware = cls.__new__(cls)
    middleware.jwt_secret = PLATFORM_SECRET
    middleware.jwt_public_key = None
    middleware.failed_attempts = {}
    middleware.enable_auth = enable_auth
    sessions = {SESSION_ID: {"user_data": dict(HUMAN)}}
    middleware.get_session = sessions.get
    return middleware


def install_real_resolution(real_auth_middleware, monkeypatch) -> SimpleNamespace:
    """Route every credential through production resolution for the rest of a test.

    Returns ``configure(kind)``, which sets the one deployment switch a kind
    needs (auth disabled, debug on, a platform-key fallback secret), and
    ``middleware()``, the middleware currently in force.
    """
    state = SimpleNamespace(middleware=None, run_secret=RUN_SECRET, device_secret=DEVICE_SECRET)

    def configure(kind: str) -> None:
        state.middleware = real_middleware(real_auth_middleware, enable_auth=kind != "auth_disabled")
        on_platform_key = kind.endswith("_on_platform_key")
        state.run_secret = PLATFORM_SECRET if on_platform_key else RUN_SECRET
        state.device_secret = PLATFORM_SECRET if on_platform_key else DEVICE_SECRET
        debug = kind == "dev_header"

        def _config_get(key, default=None):
            return True if debug and key == "development.debug" else default

        monkeypatch.setattr(real_auth_middleware, "config", SimpleNamespace(get=_config_get))

    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: state.middleware)
    monkeypatch.setattr(user_deps, "get_auth_middleware", lambda: state.middleware)
    monkeypatch.setattr(real_auth_middleware, "verify_internal_api_key", lambda provided: provided == INTERNAL_KEY)
    monkeypatch.setattr(real_auth_middleware, "reject_if_revoked_by_password_change", AsyncMock())
    run_jwt = SimpleNamespace(validate_run_jwt=token_validator(lambda: state.run_secret, RUN_AUD))
    device_jwt = SimpleNamespace(validate_device_jwt=token_validator(lambda: state.device_secret, DEVICE_AUD))
    monkeypatch.setitem(sys.modules, "services.run_jwt", run_jwt)
    monkeypatch.setitem(sys.modules, "services.device_jwt", device_jwt)
    configure("login_jwt")
    return SimpleNamespace(configure=configure, middleware=lambda: state.middleware)
