# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21559: no envelope secret route puts an exception message in a 403 or 404 body.

``envelope_secrets._mapped`` answers a ``SecretAccessError`` / ``SecretNotFoundError`` with the fixed text of
``secrets_delete_outcome`` (the table every secret delete route uses). The exception message carries the
caller-supplied secret id or the owner reference of the refused vault; it is logged, never returned. Every
route that goes through the helper is driven with both exceptions.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import base64
import logging

import pytest

from api.envelope_secrets_delete_20640_test import _SECRET, _client, store  # noqa: F401 -- fixture
from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError

_MARKER = "LEAK-21559-marker"
_OWNER = "user:owner-ref-21559"
_MESSAGE = f"{_MARKER} secret {_SECRET} owner {_OWNER}"
_ROOT_KEY = base64.urlsafe_b64encode(bytes(32)).decode("ascii").rstrip("=")
_U = f"/api/v2/secrets/{_SECRET}"
_S = f"/api/v2/secrets/system/{_SECRET}"
_CREATE = {"owner_vault": "system", "name": "n", "secret_type": "api_key", "value": "v"}  # pragma: allowlist secret
_DEPENDENT = {"dependent_kind": "service", "dependent_id": "scheduler"}

#: (id, method, url, json body) for every envelope route that maps a coordinator exception with ``_mapped``.
_OPERATIONS = [
    ("create", "POST", "/api/v2/secrets", _CREATE),
    ("service-create", "POST", "/api/v2/secrets/system", _CREATE),
    ("service-read", "GET", _S, None),
    ("service-rotate", "PUT", _S, {"value": "v"}),
    ("service-delete", "DELETE", _S, None),
    ("service-rewrap", "POST", _S + "/rewrap", {"new_root_key": _ROOT_KEY}),
    ("read", "GET", _U, None),
    ("access", "GET", _U + "/access", None),
    ("dependencies", "GET", _U + "/dependencies", None),
    ("register-dependency", "POST", _U + "/dependencies", _DEPENDENT),
    ("unregister-dependency", "DELETE", _U + "/dependencies/service/scheduler", None),
    ("rotate", "PUT", _U, {"value": "v"}),
    ("delete", "DELETE", _U, None),
    ("share", "POST", _U + "/share", {"grantee": "user:grantee"}),
    ("revoke-share", "DELETE", _U + "/share/user:grantee", None),
    ("rewrap", "POST", _U + "/rewrap", {"new_root_key": _ROOT_KEY}),
]
_IDS = [op[0] for op in _OPERATIONS]
_FIXED = {
    SecretAccessError: (403, "Not permitted to access this secret"),
    SecretNotFoundError: (404, "Secret not found"),
}


class _Raises:
    """A coordinator whose every operation raises *error* (the helper under test sees only the exception)."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __getattr__(self, name: str):
        async def call(*_args, **_kwargs):
            raise self.error

        return call


def _send(error: Exception, method: str, url: str, body):
    gen = _client(_Raises(error))
    client = next(gen)
    try:
        return client.request(method, url, json=body)
    finally:
        gen.close()


@pytest.mark.parametrize("kind", [SecretAccessError, SecretNotFoundError], ids=["access-error", "not-found-error"])
@pytest.mark.parametrize("op", _OPERATIONS, ids=_IDS)
def test_a_refused_or_missing_secret_gets_the_fixed_body(op, kind, store, caplog) -> None:
    _, method, url, body = op
    expected_status, expected_text = _FIXED[kind]

    with caplog.at_level(logging.WARNING, logger="api.secrets_delete_outcome"):
        response = _send(kind(_MESSAGE), method, url, body)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_text}
    for leaked in (_MARKER, _SECRET, _OWNER):
        assert leaked not in response.text


_REASON = {SecretAccessError: "permission_denied", SecretNotFoundError: "not_found"}  # pragma: allowlist secret
_FORGED = f"{_MARKER}\r\n2026-01-01 00:00:00 CRITICAL forged line {_SECRET} {_OWNER}"


def _refusal_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "api.secrets_delete_outcome"]


@pytest.mark.parametrize("message", [_MESSAGE, _FORGED], ids=["plain-message", "crlf-forged-line"])
@pytest.mark.parametrize("kind", [SecretAccessError, SecretNotFoundError], ids=["access-error", "not-found-error"])
@pytest.mark.parametrize("op", _OPERATIONS, ids=_IDS)
def test_the_refusal_is_logged_by_class_and_reason_without_the_message(op, kind, message, store, caplog) -> None:
    _, method, url, body = op

    with caplog.at_level(logging.WARNING, logger="api.secrets_delete_outcome"):
        _send(kind(message), method, url, body)

    logged = _refusal_lines(caplog)
    assert any(kind.__name__ in line and _REASON[kind] in line for line in logged)
    for line in logged:
        assert "\r" not in line and "\n" not in line
        for leaked in (_MARKER, _SECRET, _OWNER, "forged"):
            assert leaked not in line


@pytest.mark.parametrize("op", _OPERATIONS, ids=_IDS)
def test_a_validation_failure_gets_the_fixed_400_body_without_its_message(op, store, caplog) -> None:
    _, method, url, body = op

    with caplog.at_level(logging.WARNING, logger="api.secrets_delete_outcome"):
        response = _send(ValueError(f"{_MARKER} {_SECRET} {_OWNER}"), method, url, body)

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid secret request"}
    assert _MARKER not in "".join(r.getMessage() for r in caplog.records)
