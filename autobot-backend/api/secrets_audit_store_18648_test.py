# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Secret operations land in the canonical audit store, never with a value (#18648).

``api/secrets.py`` used to carry a log-only ``audit_log``, so no secret operation
reached the audit trail. The store seam here is ``services.audit.audit.emit`` as
the canonical ``services.audit_logger`` calls it, so the real adapter, field
mapping and sanitiser run; only the final write is faked.
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.schemas_system import ChatSecretScope
from autobot_shared.status_enums import SecretType

KNOWN_VALUE = "hunter2-KNOWN-SECRET-VALUE-18648"  # pragma: allowlist secret
SECRET_ID = "sid-18648-abcdef"


class FakeStore:
    """Collects every event the canonical audit logger records."""

    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)

    def dump(self):
        return json.dumps([e.__dict__ for e in self.events], default=str)

    def actions(self):
        return [(e.action, e.outcome) for e in self.events]


@pytest.fixture
def store():
    fake = FakeStore()
    with patch("services.audit_logger.canonical.emit", fake.emit):
        yield fake


@pytest.fixture
def client():
    from fastapi import FastAPI

    from api.secrets import router
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(router, prefix="/api/secrets")
    app.dependency_overrides[check_admin_permission] = lambda: True
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"user_id": "user-42"}
    with (
        patch("api.secrets.check_rate_limit", AsyncMock(return_value=None)),
        patch("api.secrets_audit.get_auth_middleware", return_value=auth),
        patch("api.secrets.get_auth_middleware", return_value=auth),
        patch("api.secrets._mirror_llm_provider_key", AsyncMock(return_value=None)),
        patch("api.secrets.audit_record", MagicMock()),
        patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=None)),
        patch("api.secrets.secrets_manager") as manager,
    ):
        manager.mock_attrs = manager
        with TestClient(app, raise_server_exceptions=False) as test_client:
            test_client.manager = manager
            yield test_client


def _stored(request):
    return request.to_secret_model()


def _create(client):
    client.manager.create_secret = MagicMock(side_effect=_stored)
    return client.post(
        "/api/secrets/",
        json={
            "name": "db-pass",
            "type": SecretType.API_KEY.value,
            "scope": ChatSecretScope.GENERAL.value,
            "value": KNOWN_VALUE,
        },
    )


def _list(client):
    client.manager.list_secrets = MagicMock(return_value=[{"id": SECRET_ID, "name": "db-pass"}])
    return client.get("/api/secrets/")


def _access(client):
    client.manager.get_secret = MagicMock(return_value={"id": SECRET_ID, "name": "db-pass", "value": KNOWN_VALUE})
    return client.get(f"/api/secrets/{SECRET_ID}")


def _rotate(client):
    client.manager.update_secret = MagicMock(return_value=None)
    bridged = {"id": SECRET_ID, "name": "db-pass", "metadata": {}}
    store = MagicMock(rotate=AsyncMock(return_value=None))
    with (
        patch("api.secrets.get_credential_store", return_value=store),
        patch("api.secrets._get_connector_bridged_secret", AsyncMock(return_value=bridged)),
    ):
        return client.put(f"/api/secrets/{SECRET_ID}", json={"credentials": {"token": KNOWN_VALUE}})


def _delete(client):
    client.manager.delete_secret = MagicMock(return_value=True)
    return client.delete(f"/api/secrets/{SECRET_ID}")


def _transfer(client):
    client.manager.transfer_secrets = MagicMock(return_value={"transferred": [SECRET_ID], "total_requested": 1})
    body = {"secret_ids": [SECRET_ID], "target_scope": ChatSecretScope.GENERAL.value}
    return client.post("/api/secrets/transfer", json=body)


def _bulk_delete(client):
    deleted = {"deleted_secrets": [{"id": SECRET_ID}], "total_deleted": 1}
    client.manager.delete_chat_secrets = MagicMock(return_value=deleted)
    return client.delete("/api/secrets/chat/chat-1")


FAMILIES = {
    "secret.create": _create,
    "secret.list": _list,
    "secret.access": _access,
    "secret.update": _rotate,
    "secret.delete": _delete,
    "secret.transfer": _transfer,
    "secret.bulk_delete": _bulk_delete,
}


class TestRecordLandsInTheAuditStore:
    """(a) every operation family writes one record to the store."""

    @pytest.mark.parametrize("operation", sorted(FAMILIES))
    def test_success_record_is_stored(self, client, store, operation):
        response = FAMILIES[operation](client)
        assert response.status_code in (200, 201), response.text
        assert store.actions() == [(operation, "success")]
        event = store.events[0]
        assert event.actor_id == "user-42"
        assert event.category.name == "SECURITY"

    def test_failures_map_onto_audit_result_values(self, client, store):
        client.manager.get_secret = MagicMock(return_value=None)
        with patch("api.secrets._get_connector_bridged_secret", AsyncMock(return_value=None)):
            assert client.get(f"/api/secrets/{SECRET_ID}").status_code == 404
        client.manager.delete_secret = MagicMock(side_effect=PermissionError("nope"))
        assert client.delete(f"/api/secrets/{SECRET_ID}").status_code == 403
        client.manager.list_secrets = MagicMock(side_effect=RuntimeError("boom"))
        assert client.get("/api/secrets/").status_code == 500
        assert store.actions() == [
            ("secret.access", "failed"),
            ("secret.delete", "denied"),
        ]

    def test_resource_is_a_hash_never_the_raw_id(self, client, store):
        _access(client)
        assert store.events[0].resource_id not in (None, SECRET_ID)
        assert SECRET_ID not in store.dump()


class TestNoValueEverReachesTheRecordOrTheLogs:
    """(b) a known value fed through each operation appears nowhere."""

    @pytest.mark.parametrize("operation", sorted(FAMILIES))
    def test_value_absent_from_record_and_logs(self, client, store, caplog, operation):
        with caplog.at_level(logging.DEBUG):
            FAMILIES[operation](client)
        assert store.events, "the operation recorded nothing"
        assert KNOWN_VALUE not in store.dump()
        assert KNOWN_VALUE not in caplog.text

    def test_an_error_message_echoing_the_value_is_not_recorded(self, client, store, caplog):
        client.manager.create_secret = MagicMock(side_effect=ValueError(f"bad value {KNOWN_VALUE}"))
        with caplog.at_level(logging.DEBUG):
            response = client.post(
                "/api/secrets/",
                json={
                    "name": "x",
                    "type": SecretType.API_KEY.value,
                    "scope": ChatSecretScope.GENERAL.value,
                    "value": KNOWN_VALUE,
                },
            )
        assert response.status_code == 400
        assert store.actions() == [("secret.create", "failed")]
        assert store.events[0].metadata["details"] == {"reason": "ValueError"}
        assert KNOWN_VALUE not in store.dump()
        assert KNOWN_VALUE not in caplog.text


class TestAnUnreachableStoreNeverFailsTheOperation:
    """(c) the secret operation completes; the miss is logged by class name only."""

    def test_emit_failure_inside_the_canonical_logger(self, client, caplog):
        class StoreDown(Exception):
            pass

        def boom(event):
            raise StoreDown(f"cannot write {KNOWN_VALUE}")

        with patch("services.audit_logger.canonical.emit", boom), caplog.at_level(logging.DEBUG):
            response = _create(client)
        assert response.status_code == 201
        assert "StoreDown" in caplog.text
        assert KNOWN_VALUE not in caplog.text

    def test_audit_call_itself_failing(self, client, caplog):
        class LoggerDown(Exception):
            pass

        failing = AsyncMock(side_effect=LoggerDown(f"cannot reach {KNOWN_VALUE}"))
        with patch("api.secrets_audit.audit_log", failing), caplog.at_level(logging.DEBUG):
            response = _delete(client)
        assert response.status_code == 200
        assert "LoggerDown" in caplog.text
        assert KNOWN_VALUE not in caplog.text


class TestHandlerErrorLogsCarryTheClassNameOnly:
    """A handler's own error log must not echo an exception text that holds a value."""

    @staticmethod
    def _raising(client, attr):
        setattr(client.manager, attr, MagicMock(side_effect=RuntimeError(f"echo {KNOWN_VALUE}")))

    def _update(self, client):
        client.manager.update_secret = MagicMock(return_value=None)
        store = MagicMock(rotate=AsyncMock(side_effect=RuntimeError(f"echo {KNOWN_VALUE}")))
        with patch("api.secrets.get_credential_store", return_value=store):
            return client.put(f"/api/secrets/{SECRET_ID}", json={"credentials": {"token": KNOWN_VALUE}})

    @pytest.mark.parametrize(
        "attr, call",
        [
            ("create_secret", lambda c: _create_raw(c)),
            ("list_secrets", lambda c: c.get("/api/secrets/")),
            ("get_secret", lambda c: c.get(f"/api/secrets/{SECRET_ID}")),
            ("delete_secret", lambda c: c.delete(f"/api/secrets/{SECRET_ID}")),
            ("transfer_secrets", lambda c: c.post("/api/secrets/transfer", json=_transfer_body())),
            ("delete_chat_secrets", lambda c: c.delete("/api/secrets/chat/chat-1")),
        ],
    )
    def test_generic_failure_logs_no_value(self, client, store, caplog, attr, call):
        self._raising(client, attr)
        with caplog.at_level(logging.DEBUG):
            response = call(client)
        assert response.status_code == 500
        assert "RuntimeError" in caplog.text
        assert KNOWN_VALUE not in caplog.text
        assert KNOWN_VALUE not in store.dump()

    def test_update_failure_logs_no_value(self, client, store, caplog):
        with caplog.at_level(logging.DEBUG):
            response = self._update(client)
        assert response.status_code == 500
        assert "RuntimeError" in caplog.text
        assert KNOWN_VALUE not in caplog.text


class TestAnUnrecordedWriteIsReported:
    """AuditLogger.log reports a failed write by returning False, not by raising."""

    def test_a_false_return_is_logged_and_the_operation_completes(self, client, caplog):
        with patch("api.secrets_audit.audit_log", AsyncMock(return_value=False)), caplog.at_level(logging.DEBUG):
            response = _delete(client)
        assert response.status_code == 200
        assert "did not record DELETE" in caplog.text


def _create_raw(client):
    body = {"name": "x", "type": SecretType.API_KEY.value, "scope": ChatSecretScope.GENERAL.value, "value": KNOWN_VALUE}
    return client.post("/api/secrets/", json=body)


def _transfer_body():
    return {"secret_ids": [SECRET_ID], "target_scope": ChatSecretScope.GENERAL.value}


class TestTheOldLocalFunctionRecordedNothing:
    """(d) contrast: the log-only function never reached the store; the route now does."""

    def test_the_local_audit_log_is_gone(self):
        import api.secrets as module

        assert not hasattr(module, "audit_log")

    def test_the_old_log_only_shape_leaves_the_store_empty(self, store, caplog):
        """The removed body (a ``logger.info`` and nothing else) vs the routed call."""
        old_logger = logging.getLogger("old-local-audit")
        with caplog.at_level(logging.INFO):
            old_logger.info("[Secrets Audit] %s | Operation: %s", "SUCCESS", "CREATE")
        assert store.events == []

    def test_the_route_now_reaches_the_store(self, client, store):
        _delete(client)
        assert len(store.events) == 1
