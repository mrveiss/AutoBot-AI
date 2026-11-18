# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20557: a value update is never dropped, a delete never ignores dependents, and the
audit record of a credential delete/rotate is written BEFORE the write or the write stops.

Every assertion is on the STORE (legacy file, vault dict), not the status code: the
defects all answered 200 while the store did something other than what was reported.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from api import secrets as secrets_module
from api import secrets_audit, secrets_system_vault
from api.schemas_system import ChatSecretScope, SecretCreateRequest, SecretUpdateRequest
from api.secrets_system_vault_17731_test import _SECRET_ID, _FakeVault, client_and_vault  # noqa: F401 -- fixture

_OLD = "old-value-20557"  # pragma: allowlist secret
_NEW = "new-value-20557"  # pragma: allowlist secret
_VAULT_KEY = uuid.UUID(_SECRET_ID)


def _manager(tmp_path) -> secrets_module.SecretsManager:
    manager = secrets_module.SecretsManager()
    manager.secrets_file = str(tmp_path / "secrets.json")
    manager.key_file = str(tmp_path / "secrets.key")
    manager.cipher = Fernet(Fernet.generate_key())
    manager._initialized = True
    return manager


def test_a_legacy_value_update_is_applied_to_the_store(tmp_path) -> None:
    manager = _manager(tmp_path)
    created = manager.create_secret(
        SecretCreateRequest(name="legacy", type="api_key", scope=ChatSecretScope.GENERAL, value=_OLD)
    )

    updated = manager.update_secret(created.id, SecretUpdateRequest(value=_NEW))

    assert updated is not None
    assert manager._decrypt_value(manager._load_secrets()[created.id]["encrypted_value"]) == _NEW


def test_a_legacy_update_without_a_value_leaves_the_stored_value(tmp_path) -> None:
    manager = _manager(tmp_path)
    created = manager.create_secret(
        SecretCreateRequest(name="legacy", type="api_key", scope=ChatSecretScope.GENERAL, value=_OLD)
    )

    manager.update_secret(created.id, SecretUpdateRequest(description="only metadata"))

    assert manager._decrypt_value(manager._load_secrets()[created.id]["encrypted_value"]) == _OLD


class _VaultWithDependents(_FakeVault):
    def __init__(self, dependents):
        super().__init__()
        self.dependents = dependents

    async def describe_dependencies(self, session, *, user_id, permissions, secret_id):
        return [SimpleNamespace(dependent_kind=k, dependent_id=i) for k, i in self.dependents]


def _digest(dependents) -> str:
    """The digest a human echoes to confirm the listed (kind, id) dependents."""
    from api.secrets_guarded_delete import dependents_digest

    return dependents_digest([SimpleNamespace(dependent_kind=k, dependent_id=i) for k, i in dependents])


def _with_dependents(client_and_vault, monkeypatch, dependents):  # noqa: F811
    client, _ = client_and_vault()
    vault = _VaultWithDependents(dependents)
    monkeypatch.setattr(secrets_system_vault, "_coordinator_or_none", lambda: vault)
    return client, vault


def test_delete_with_dependents_is_refused_and_lists_them(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [("service", "scheduler"), ("agent", "a-1")])

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "secret_has_dependents"
    assert detail["dependents"] == [
        {"dependent_kind": "service", "dependent_id": "scheduler"},
        {"dependent_kind": "agent", "dependent_id": "a-1"},
    ]
    assert _VAULT_KEY in vault.store


def test_a_confirmed_delete_removes_the_secret(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [("service", "scheduler")])

    response = client.delete(f"/api/secrets/{_SECRET_ID}?dependents_digest={_digest([('service', 'scheduler')])}")

    assert response.status_code == 200
    assert _VAULT_KEY not in vault.store


def test_the_internal_key_cannot_confirm_past_dependents(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [("service", "scheduler")])
    monkeypatch.setattr(secrets_system_vault, "verify_internal_api_key", lambda k: k == "svc")

    response = client.delete(
        f"/api/secrets/{_SECRET_ID}?dependents_digest={_digest([('service', 'scheduler')])}",
        headers={"X-Internal-API-Key": "svc"},
    )

    assert response.status_code == 403
    assert _VAULT_KEY in vault.store


def test_a_delete_without_dependents_needs_no_confirmation(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [])

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200
    assert _VAULT_KEY not in vault.store


@pytest.fixture
def real_audit(client_and_vault, monkeypatch):  # noqa: F811
    """The route with the REAL audit adapter; `audit_log` is the injected failure point."""
    client, _ = client_and_vault()
    vault = _VaultWithDependents([])
    monkeypatch.setattr(secrets_system_vault, "_coordinator_or_none", lambda: vault)
    monkeypatch.setattr(secrets_module, "audit_secret_op", secrets_audit.audit_secret_op)
    monkeypatch.setattr(secrets_audit, "_actor", lambda _r: "admin")
    return client, vault


@pytest.mark.parametrize("failure", [AsyncMock(return_value=False), AsyncMock(side_effect=RuntimeError("down"))])
def test_a_failed_audit_write_stops_a_credential_delete(real_audit, monkeypatch, failure) -> None:
    client, vault = real_audit
    monkeypatch.setattr(secrets_audit, "audit_log", failure)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 503
    assert vault.store == {_VAULT_KEY: b"old-value"}
    secrets_module.secrets_manager.delete_secret.assert_not_called()


@pytest.mark.parametrize("failure", [AsyncMock(return_value=False), AsyncMock(side_effect=RuntimeError("down"))])
def test_a_failed_audit_write_stops_a_credential_rotate(real_audit, monkeypatch, failure) -> None:
    client, vault = real_audit
    monkeypatch.setattr(secrets_audit, "audit_log", failure)

    response = client.put(f"/api/secrets/{_SECRET_ID}", json={"value": _NEW})

    assert response.status_code == 503
    assert vault.store == {_VAULT_KEY: b"old-value"}


def test_the_record_is_written_before_the_delete(real_audit, monkeypatch) -> None:
    client, vault = real_audit
    order: list[str] = []

    async def record(*args, **kwargs):
        order.append(f"audit:{'present' if _VAULT_KEY in vault.store else 'gone'}")
        return True

    monkeypatch.setattr(secrets_audit, "audit_log", record)

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200
    assert order[0] == "audit:present"
    assert _VAULT_KEY not in vault.store


def _trail(monkeypatch) -> AsyncMock:
    ops = AsyncMock()
    monkeypatch.setattr(secrets_module, "audit_secret_op", ops)
    return ops


def _outcome(ops: AsyncMock) -> tuple:
    """The result and details of the last record: (result, details); the actor is asserted on its own."""
    call = ops.await_args
    return (call.args[3] if len(call.args) > 3 else "success", {k: v for k, v in call.kwargs.items() if k != "actor"})


def test_a_completed_delete_records_its_outcome_after_the_intent(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, _vault = _with_dependents(client_and_vault, monkeypatch, [])
    ops = _trail(monkeypatch)

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200

    assert ops.await_args_list[0].kwargs["phase"] == "before_write"
    assert _outcome(ops) == ("success", {"phase": "completed"})


def test_a_refused_delete_records_the_refusal_not_a_completion(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [("service", "scheduler")])
    ops = _trail(monkeypatch)

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 409

    assert _outcome(ops) == ("denied", {"reason": "has_dependents"})
    assert _VAULT_KEY in vault.store


def test_a_completed_rotate_records_its_outcome_after_the_intent(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, _vault = _with_dependents(client_and_vault, monkeypatch, [])
    ops = _trail(monkeypatch)
    secrets_module.secrets_manager.update_secret.return_value = SimpleNamespace(
        model_dump=lambda mode: {"id": "legacy-1", "name": "same"}
    )

    assert client.put("/api/secrets/legacy-1", json={"value": "new"}).status_code == 200

    assert ops.await_args_list[0].kwargs["phase"] == "before_write"
    assert _outcome(ops) == ("success", {"phase": "completed"})


def test_best_effort_operations_still_survive_a_down_audit_store(real_audit, monkeypatch) -> None:
    """A metadata-only update is not a credential rotation: its record stays best-effort."""
    client, _vault = real_audit
    monkeypatch.setattr(secrets_audit, "audit_log", AsyncMock(return_value=False))
    secrets_module.secrets_manager.update_secret.return_value = SimpleNamespace(
        model_dump=lambda mode: {"id": "legacy-1", "name": "renamed"}
    )

    assert client.put("/api/secrets/legacy-1", json={"description": "d"}).status_code == 200


def test_the_required_record_is_awaited_durably_and_best_effort_ones_are_not(real_audit, monkeypatch) -> None:
    """Train review: `required` must wait for the committed row, not merely schedule the write."""
    client, _ = real_audit
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(secrets_audit, "audit_log", record)

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200

    durable = [call.kwargs["durable"] for call in record.await_args_list]
    assert durable[0] is True  # the "attempted" record written before the delete
    assert durable[1:] == [False] * (len(durable) - 1)  # the outcome record stays best-effort


def test_every_record_of_a_delete_names_the_resolved_actor(real_audit, monkeypatch) -> None:
    """The actor is looked up once; a second lookup that fails must not file the delete as `system`."""
    client, _ = real_audit
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(secrets_audit, "audit_log", record)
    monkeypatch.setattr(secrets_audit, "_actor", lambda _r: None)  # the second lookup comes back empty

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200

    users = {call.kwargs["user_id"] for call in record.await_args_list}
    assert users and None not in users
