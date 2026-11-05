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


def _refuse_with(monkeypatch, status: int, detail: str) -> None:
    async def refuse(_request):
        raise HTTPException(status_code=status, detail=detail)

    monkeypatch.setattr(refusal, "validate_service_auth", refuse)


@pytest.fixture
def refused_hmac(monkeypatch):
    _refuse_with(monkeypatch, 401, "Authentication required: Missing required headers")


def _refusals(caplog) -> list:
    return [r for r in caplog.records if "service principal refused" in r.getMessage()]


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
        ({}, _OWN, "presented none; no service credential was presented"),
    ],
    ids=["key-mismatch", "backend-has-no-key", "no-credential"],
)
async def test_each_key_refusal_names_the_form_and_why_never_a_value(
    monkeypatch, caplog, refused_hmac, headers, backend_key, expected
) -> None:
    if backend_key:
        monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", backend_key)
    else:
        monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY", raising=False)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as refused:
        await envelope_secrets.service_principal(_request(headers))
    assert refused.value.status_code == 401
    assert [r.getMessage() for r in _refusals(caplog)] == [f"service principal refused: {expected}"]
    record = _refusals(caplog)[0]
    assert (record.credential_form, record.path, record.method) == (
        expected.split(";")[0].removeprefix("presented "),
        "/api/v2/secrets/system",
        "GET",
    )
    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert _SENT not in logged and _OWN not in logged, "no key value reaches the message or its extra"


_HMAC = {"X-Service-ID": "evil-svc", "X-Service-Signature": "sig", "X-Service-Timestamp": "1"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail, reason",
    [
        ("Authentication failed: Invalid signature", "the service signature did not validate"),
        ("Authentication failed: Unknown service: evil-svc", "the service is not registered"),
        (
            "Authentication required: Timestamp outside 300s window (diff: 999s)",
            "the request timestamp is outside the allowed window",
        ),
        ("Authentication failed: Invalid timestamp format", "the request timestamp is malformed"),
    ],
    ids=["bad-signature", "unknown-service", "stale-timestamp", "malformed-timestamp"],
)
async def test_an_hmac_refusal_takes_its_reason_from_the_checks_fixed_detail(
    monkeypatch, caplog, detail: str, reason: str
) -> None:
    """The reason is the check's own, not guessed from which headers arrived, and no client value is echoed."""
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _OWN)
    _refuse_with(monkeypatch, 401, detail)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException):
        await envelope_secrets.service_principal(_request(_HMAC))
    assert [r.getMessage() for r in _refusals(caplog)] == [
        f"service principal refused: presented X-Service-* (HMAC); {reason}"
    ]
    assert "evil-svc" not in " ".join(r.getMessage() for r in caplog.records), "the caller's service id isn't echoed"


@pytest.mark.asyncio
async def test_an_auth_service_error_is_not_logged_as_a_refusal(monkeypatch, caplog) -> None:
    """A 5xx (Redis down) is the authentication service failing, its own message, never 'did not validate'."""
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _OWN)
    _refuse_with(monkeypatch, 500, "Internal server error: Authentication service error")
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as failed:
        await envelope_secrets.service_principal(_request(_HMAC))
    assert failed.value.status_code == 500
    assert not _refusals(caplog)
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == [
        "service principal check failed: the authentication service errored (HTTP 500); presented X-Service-* (HMAC)"
    ]


@pytest.mark.asyncio
async def test_an_accepted_key_is_not_logged_as_a_refusal(monkeypatch, caplog, refused_hmac) -> None:
    """Control: the refusal log fires only on a refusal."""
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _OWN)
    with caplog.at_level(logging.WARNING):
        assert await envelope_secrets.service_principal(_request({"X-Internal-API-Key": _OWN})) == "slm-backend"
    assert not _refusals(caplog)
