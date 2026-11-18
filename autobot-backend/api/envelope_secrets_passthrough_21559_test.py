# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21559: the routes' own 404 / 409 / 503 answers stay outside the refusal table and carry fixed details.

``envelope_secrets._mapped`` turns a coordinator exception into the fixed 403 / 404 / 400 of
``autobot_shared.http_refusal``. The HTTP errors the routes raise themselves pass through it untouched, so
each is asserted here to carry a fixed string (or a fixed code and message), never the text of the error that
caused it, a secret id or an owner reference.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import envelope_secrets
from api.envelope_secrets_delete_20640_test import _DEPENDENTS, _SECRET, _client, store  # noqa: F401 -- fixture
from api.secrets_guarded_delete import _lock_timeout_refusal

_MARKER = "LEAK-21559-passthrough"
_ROUTES = [f"/api/v2/secrets/{_SECRET}", f"/api/v2/secrets/system/{_SECRET}"]


class _Coordinator:
    """Lists dependents for the 409 case; every delete would succeed."""

    async def describe_dependencies_for_delete(self, session, **_kw):
        return _DEPENDENTS

    service_describe_dependencies = describe_dependencies_for_delete

    async def delete(self, session, **_kw):
        return None

    service_delete = delete


@pytest.mark.parametrize("url", _ROUTES, ids=["user-delete", "service-delete"])
def test_the_dependents_409_carries_a_fixed_code_and_message(url, store) -> None:
    gen = _client(_Coordinator())
    client = next(gen)
    try:
        response = client.delete(url)
    finally:
        gen.close()

    detail = response.json()["detail"]
    assert response.status_code == 409
    assert (detail["code"], detail["message"]) == ("secret_has_dependents", "Dependents use this secret")
    assert set(detail) == {"code", "message", "dependents", "dependents_digest"}


@pytest.mark.parametrize("url", _ROUTES, ids=["user-delete", "service-delete"])
def test_the_unrecorded_delete_503_carries_a_fixed_string(url, store) -> None:
    gen = _client(_Coordinator())
    client = next(gen)
    try:
        with patch("api.secrets_audit.audit_log", AsyncMock(return_value=False)):
            response = client.delete(url)
    finally:
        gen.close()

    assert response.status_code == 503
    assert response.json() == {"detail": "Audit trail unavailable; nothing was changed"}


def test_the_lock_timeout_503_carries_a_fixed_code_and_message() -> None:
    refusal = _lock_timeout_refusal()

    assert refusal.status_code == 503
    assert refusal.detail == {"code": "secret_lock_timeout", "message": "The secret is busy; retry the delete shortly"}


def test_the_unconfigured_store_503_does_not_echo_the_cause(monkeypatch) -> None:
    monkeypatch.setattr(envelope_secrets, "_coordinator", None)
    with patch.object(envelope_secrets, "SecretsCoordinator", side_effect=RuntimeError(f"{_MARKER} root key")):
        with pytest.raises(HTTPException) as refused:
            envelope_secrets.get_coordinator()

    assert refused.value.status_code == 503
    assert refused.value.detail == "envelope secrets store not configured"
    assert _MARKER not in str(refused.value.detail)
