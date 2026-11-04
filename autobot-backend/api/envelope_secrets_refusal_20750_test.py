# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20750: a refused System-vault caller is logged with the credential FORM it presented, never a value."""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api import _service_principal_refusal as refusal
from api import envelope_secrets

_SENT = "sent-key-sample"  # pragma: allowlist secret -- a fixture value
_OWN = "own-key-sample"  # pragma: allowlist secret -- a fixture value


def _request(headers: dict) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request(
        {"type": "http", "method": "GET", "path": "/api/v2/secrets/system", "headers": raw, "query_string": b""}
    )


@pytest.fixture(autouse=True)
def real_key_check(monkeypatch):
    """The conftest stubs auth_middleware's key check to always refuse; these cases need the real one."""
    from autobot_shared.auth.internal_api_key import verify_internal_api_key

    monkeypatch.setattr(envelope_secrets, "verify_internal_api_key", verify_internal_api_key)


@pytest.fixture
def refused_hmac(monkeypatch):
    async def refuse(_request):
        raise HTTPException(status_code=401, detail="Missing authentication headers")

    monkeypatch.setattr(refusal, "validate_service_auth", refuse)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers, backend_key, expected",
    [
        (
            {"X-Internal-API-Key": _SENT},
            _OWN,
            "presented X-Internal-API-Key; it does not match the backend's AUTOBOT_INTERNAL_API_KEY",
        ),
        (
            {"X-Internal-API-Key": _SENT},
            "",
            "presented X-Internal-API-Key; the backend has no AUTOBOT_INTERNAL_API_KEY configured",
        ),
        (
            {"X-Service-ID": "slm-backend", "X-Service-Signature": "sig", "X-Service-Timestamp": "1"},
            _OWN,
            "presented X-Service-* (HMAC); the service signature did not validate",
        ),
        ({}, _OWN, "presented none; no service credential was presented"),
    ],
    ids=["key-mismatch", "backend-has-no-key", "hmac-refused", "no-credential"],
)
async def test_each_refusal_names_the_form_and_why_never_a_value(
    monkeypatch, caplog, refused_hmac, headers, backend_key, expected
) -> None:
    if backend_key:
        monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", backend_key)
    else:
        monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY", raising=False)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as refused:
        await envelope_secrets.service_principal(_request(headers))
    assert refused.value.status_code == 401
    messages = [r.getMessage() for r in caplog.records if "service principal refused" in r.getMessage()]
    assert messages == [f"service principal refused: {expected}"]
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert _SENT not in logged and _OWN not in logged, "no key value reaches the log"


@pytest.mark.asyncio
async def test_an_accepted_key_is_not_logged_as_a_refusal(monkeypatch, caplog, refused_hmac) -> None:
    """Control: the refusal log fires only on a refusal."""
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _OWN)
    with caplog.at_level(logging.WARNING):
        assert await envelope_secrets.service_principal(_request({"X-Internal-API-Key": _OWN})) == "slm-backend"
    assert not [r for r in caplog.records if "service principal refused" in r.getMessage()]
