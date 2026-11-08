# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A secret created in-process must list in-process (#19476).

``SecretsManager.create_secret`` cached ``secret.dict()`` -- datetimes and enum
members -- while the on-disk shape (and a fresh process) is JSON-native. The
list handler serialises with ``JSONResponse``, so the very first list after a
create raised ``TypeError`` (500) until the process restarted.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.responses import JSONResponse

import api.secrets as secrets_module
from api.schemas_system import ChatSecretScope, SecretCreateRequest
from api.secrets import SecretsManager

_SECRET_VALUE = "super-secret-value-19476"  # pragma: allowlist secret


def _manager(tmp_path) -> SecretsManager:
    manager = SecretsManager()
    manager.secrets_file = str(tmp_path / "secrets.json")
    manager.key_file = str(tmp_path / "secrets.key")
    manager.cipher = Fernet(Fernet.generate_key())
    manager._initialized = True
    return manager


def _request(**overrides) -> SecretCreateRequest:
    fields = dict(
        name="my-host",
        type="infrastructure_host",
        scope=ChatSecretScope.GENERAL,
        value=_SECRET_VALUE,
        metadata={"host": "h", "username": "root"},
    )
    fields.update(overrides)
    return SecretCreateRequest(**fields)


def test_a_created_secret_lists_and_serialises_in_the_same_process(tmp_path) -> None:
    manager = _manager(tmp_path)
    manager.create_secret(_request(expires_at="2030-01-01T00:00:00"))

    listed = manager.list_secrets()

    assert len(listed) == 1
    JSONResponse(content={"secrets": listed})  # reproduced: TypeError (datetime)
    json.dumps(listed)


def test_cached_and_on_disk_shapes_are_identical(tmp_path) -> None:
    manager = _manager(tmp_path)
    manager.create_secret(_request())

    cached = manager._load_secrets()
    with open(manager.secrets_file, encoding="utf-8") as fh:
        on_disk = json.load(fh)

    assert cached == on_disk


def test_the_chosen_type_is_the_stored_type(tmp_path) -> None:
    """Both GUI choices round-trip: 'Server Host' stays infrastructure_host
    (the type api/infrastructure.py reads for SSH hosts) and the 'SSH Key'
    template stays ssh_key."""
    manager = _manager(tmp_path)
    manager.create_secret(_request(name="a", type="infrastructure_host"))
    manager.create_secret(_request(name="b", type="ssh_key"))

    types = {s["name"]: s["type"] for s in manager.list_secrets()}

    assert types == {"a": "infrastructure_host", "b": "ssh_key"}


def test_create_records_the_authenticated_owner_and_lists_it(tmp_path, monkeypatch) -> None:
    from api.secrets_ownership import stamp_owner

    stamped = stamp_owner(_request(), {"user_id": "u-1", "org_id": "o-1"})
    manager = _manager(tmp_path)
    manager.create_secret(stamped)

    entry = manager.list_secrets()[0]
    assert (entry["owner_id"], entry["org_id"]) == ("u-1", "o-1")


def test_a_body_asserted_owner_cannot_override_the_authenticated_one() -> None:
    from api.secrets_ownership import stamp_owner

    stamped = stamp_owner(_request(owner_id="someone-else"), {"user_id": "u-1"})

    assert stamped.owner_id == "u-1"


def test_no_user_clears_body_asserted_ownership() -> None:
    from api.secrets_ownership import stamp_owner

    stamped = stamp_owner(_request(owner_id="x", org_id="o-x"), None)
    assert (stamped.owner_id, stamped.org_id) == (None, None), "ownership is never taken from the body"


@pytest.mark.asyncio
async def test_list_failure_logs_message_and_never_the_value(tmp_path, monkeypatch, caplog) -> None:
    manager = _manager(tmp_path)
    manager.create_secret(_request())

    def boom(*_a, **_k):
        raise TypeError("Object of type datetime is not JSON serializable")

    monkeypatch.setattr(manager, "list_secrets", boom)
    monkeypatch.setattr(secrets_module, "secrets_manager", manager)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(secrets_module, "check_rate_limit", _noop)
    with caplog.at_level(logging.ERROR), pytest.raises(HTTPException):
        await secrets_module.list_secrets(SimpleNamespace(), None, None, True)

    assert "not JSON serializable" in caplog.text
    assert _SECRET_VALUE not in caplog.text


def test_describe_failure_names_the_cause_but_not_a_value() -> None:
    from api.secrets_failure_log import describe_failure

    def raise_it(exc):
        raise exc

    for exc, expect_message in (
        (TypeError("Object of type datetime is not JSON serializable"), True),
        (RuntimeError(f"echo {_SECRET_VALUE}"), False),
        (KeyError(_SECRET_VALUE), False),
    ):
        try:
            raise_it(exc)
        except Exception as caught:
            text = describe_failure(caught)
        assert type(exc).__name__ in text and "raise_it" in text
        assert (str(exc) in text) is expect_message
        assert (_SECRET_VALUE in text) is False


def test_post_then_get_over_http_lists_the_owned_secret(tmp_path) -> None:
    """The handler wiring: POST records the authenticated owner, GET lists it."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(secrets_module.router, prefix="/api/secrets")
    app.dependency_overrides[check_admin_permission] = lambda: True
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"user_id": "user-42", "org_id": "org-7"}
    with (
        patch("api.secrets.check_rate_limit", AsyncMock(return_value=None)),
        patch("api.secrets_audit.get_auth_middleware", return_value=auth),
        patch("api.secrets.get_auth_middleware", return_value=auth),
        patch("api.secrets._mirror_llm_provider_key", AsyncMock(return_value=None)),
        patch("api.secrets.audit_record", MagicMock()),
        patch("api.secrets.audit_secret_op", AsyncMock(return_value=None)),
        patch("api.secrets.secrets_manager", _manager(tmp_path)),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        body = {"name": "h", "type": "infrastructure_host", "scope": "general", "value": _SECRET_VALUE}
        assert client.post("/api/secrets/", json={**body, "owner_id": "spoofed"}).status_code == 201
        listed = client.get("/api/secrets/")

    assert listed.status_code == 200
    (entry,) = listed.json()["secrets"]
    assert (entry["owner_id"], entry["org_id"], entry["type"]) == ("user-42", "org-7", "infrastructure_host")
    assert _SECRET_VALUE not in listed.text
