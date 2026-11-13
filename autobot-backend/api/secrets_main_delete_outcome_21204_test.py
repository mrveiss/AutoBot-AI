# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21204: ``DELETE /api/secrets/{id}`` leaves an outcome record after its ``attempted`` intent for EVERY failure.

A lock-timeout 503 and the vault-not-configured 503 used to leave the intent as the last record. The mapping
is the one ``envelope_secrets_delete.audited_delete`` applies: ``denied`` for a refusal (``http_<status>``),
``failed`` for a missing secret or an unexpected error; records carry identifiers and class names only.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

from unittest.mock import AsyncMock

from api import secrets as secrets_module
from api import secrets_audit, secrets_guarded_delete, secrets_system_vault
from api.secrets_defects_20557_test import _outcome, _trail, _with_dependents
from api.secrets_system_vault_17731_test import _SECRET_ID, client_and_vault  # noqa: F401 -- fixture


def _results(ops: AsyncMock) -> list:
    """Every record of the request as (result, details), the intent first."""
    return [
        (call.args[3] if len(call.args) > 3 else "success", {k: v for k, v in call.kwargs.items() if k != "actor"})
        for call in ops.await_args_list
    ]


def test_a_lock_timeout_503_records_a_denied_outcome_after_the_intent(client_and_vault, monkeypatch) -> None:
    client, vault = _with_dependents(client_and_vault, monkeypatch, [])
    ops = _trail(monkeypatch)

    async def busy(session, secret_id) -> None:
        raise secrets_guarded_delete._lock_timeout_refusal()

    monkeypatch.setattr(secrets_guarded_delete, "lock_secret_row", busy)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 503
    assert response.headers["Retry-After"]
    assert _results(ops) == [
        ("attempted", {"required": True, "phase": "before_write"}),
        ("denied", {"reason": "http_503"}),
    ]
    assert len(vault.store) == 1, "the secret must still be stored"


def test_the_vault_not_configured_503_records_a_denied_outcome_after_the_intent(client_and_vault, monkeypatch) -> None:
    client, _vault = client_and_vault()
    monkeypatch.setattr(secrets_system_vault, "_coordinator_or_none", lambda: None)
    ops = _trail(monkeypatch)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 503
    assert _results(ops)[0][0] == "attempted"
    assert _outcome(ops) == ("denied", {"reason": "http_503"})
    assert len(ops.await_args_list) == 2


def test_an_unknown_secret_records_exactly_one_not_found_outcome(client_and_vault, monkeypatch) -> None:
    client, vault = client_and_vault()
    vault.store.clear()
    monkeypatch.setattr(secrets_module, "_get_connector_bridged_secret", AsyncMock(return_value=None))
    ops = _trail(monkeypatch)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 404
    assert [r[0] for r in _results(ops)] == ["attempted", "failed"]
    assert _outcome(ops) == ("failed", {"reason": "not_found"})


def test_a_refusal_for_dependents_still_records_has_dependents(client_and_vault, monkeypatch) -> None:
    client, _vault = _with_dependents(client_and_vault, monkeypatch, [("service", "scheduler")])
    ops = _trail(monkeypatch)

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 409

    assert [r[0] for r in _results(ops)] == ["attempted", "denied"]
    assert _outcome(ops) == ("denied", {"reason": "has_dependents"})


def test_a_permission_error_still_records_denied_and_answers_403(client_and_vault, monkeypatch) -> None:
    client, _vault = client_and_vault()
    secrets_module.secrets_manager.delete_secret.side_effect = PermissionError("no")
    ops = _trail(monkeypatch)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 403
    assert [r[0] for r in _results(ops)] == ["attempted", "denied"]
    assert _outcome(ops) == ("denied", {"reason": "permission_denied"})


def test_an_unexpected_error_still_records_failed_with_the_class_name_only(client_and_vault, monkeypatch) -> None:
    client, _vault = client_and_vault()
    secrets_module.secrets_manager.delete_secret.side_effect = RuntimeError("disk said SECRET-VALUE")
    ops = _trail(monkeypatch)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 500
    assert _outcome(ops) == ("failed", {"reason": "RuntimeError"})
    assert "SECRET-VALUE" not in repr(ops.await_args_list)


def test_an_unwritable_intent_gets_no_second_record(client_and_vault, monkeypatch) -> None:
    """The 'audit trail unavailable' 503 IS the intent failing: no outcome is attempted after it."""
    client, vault = client_and_vault()
    monkeypatch.setattr(secrets_module, "audit_secret_op", secrets_audit.audit_secret_op)
    monkeypatch.setattr(secrets_audit, "_actor", lambda _r: "admin")
    record = AsyncMock(return_value=False)
    monkeypatch.setattr(secrets_audit, "audit_log", record)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 503
    assert record.await_count == 1
    assert len(vault.store) == 1
