# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The coordinator's admin-maintenance path (#17850, #17773): admin only, attributable, audited before it runs."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.secrets_vault import VaultRef
from services import secrets_coordinator as coordinator_module
from services import secrets_maintenance as maintenance
from services.secrets_coordinator import SecretsCoordinator
from services.secrets_maintenance import MaintenanceActor, MaintenanceAuditError

_ADMIN = uuid.UUID(int=7)
_SECRET = uuid.UUID(int=1)
_ACTOR = MaintenanceActor(_ADMIN, "approval-42")
_OWNER = VaultRef.parse("user:" + str(uuid.UUID(int=5)))


def _coordinator(monkeypatch, *, audit_written=True):
    """A coordinator whose ADMIN CHECK is stubbed: this file pins ordering and audit; the check itself is exercised
    against a real database in ``tests/migrations/test_secrets_maintenance_admin_17850.py``."""
    service = MagicMock(read=AsyncMock(return_value=b"value"), delete=AsyncMock())
    coordinator = SecretsCoordinator(service)
    monkeypatch.setattr(coordinator, "_owner_vault", AsyncMock(return_value=_OWNER))
    monkeypatch.setattr(coordinator_module, "require_maintenance_admin", AsyncMock())
    audit = AsyncMock(return_value=audit_written)
    monkeypatch.setattr(maintenance, "audit_log", audit)
    return coordinator, service, audit


@pytest.mark.asyncio
async def test_a_maintenance_read_writes_its_audit_row_first_and_opens_through_the_owner_vault(monkeypatch):
    coordinator, service, audit = _coordinator(monkeypatch)
    value = await coordinator.maintenance_read(MagicMock(), actor=_ACTOR, secret_id=_SECRET)
    assert value == b"value"
    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["user_id"] == str(_ADMIN) and kwargs["resource"] == f"secret:{_SECRET}" and kwargs["durable"] is True
    assert kwargs["details"] == {"operation": "maintenance_read", "reference": "approval-42"}
    assert service.read.await_args.kwargs["accessible_vaults"] == [_OWNER]


@pytest.mark.asyncio
async def test_a_maintenance_delete_is_audited_before_the_delete_runs(monkeypatch):
    coordinator, service, audit = _coordinator(monkeypatch)
    order: list[str] = []
    audit.side_effect = lambda *a, **k: order.append("audit") or True
    service.delete.side_effect = lambda *a, **k: order.append("delete")
    await coordinator.maintenance_delete(MagicMock(), actor=_ACTOR, secret_id=_SECRET)
    assert order == ["audit", "delete"]
    assert audit.await_args.kwargs["details"]["operation"] == "maintenance_delete"


@pytest.mark.asyncio
async def test_no_read_or_delete_runs_when_the_audit_row_cannot_be_written(monkeypatch):
    coordinator, service, _ = _coordinator(monkeypatch, audit_written=False)
    with pytest.raises(MaintenanceAuditError):
        await coordinator.maintenance_read(MagicMock(), actor=_ACTOR, secret_id=_SECRET)
    with pytest.raises(MaintenanceAuditError):
        await coordinator.maintenance_delete(MagicMock(), actor=_ACTOR, secret_id=_SECRET)
    service.read.assert_not_called()
    service.delete.assert_not_called()


@pytest.mark.asyncio
async def test_the_audit_row_carries_ids_and_a_reference_never_a_value_or_name(monkeypatch):
    coordinator, _, audit = _coordinator(monkeypatch)
    await coordinator.maintenance_read(MagicMock(), actor=_ACTOR, secret_id=_SECRET)
    assert "value" not in repr(audit.await_args)
