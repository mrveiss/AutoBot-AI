# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the infrastructure host DELETE route (#12723).

Issue #1310 made infra hosts user Secrets entries (host id == secret id).
The FE (useSecretsInfraApi.deleteInfraHost) DELETEs
``/api/infrastructure/hosts/{id}``; this restores the missing backend half.
"""

import pytest

import api.infrastructure as infra


@pytest.fixture
def _hosts(monkeypatch):
    """Stub the secrets-host read-shim with a single known host."""
    monkeypatch.setattr(
        infra, "_load_secrets_hosts", lambda: [{"id": "h9", "name": "box"}]
    )


async def test_delete_infrastructure_host_removes_matching_secret(_hosts, monkeypatch):
    import api.secrets as secrets_mod

    calls = []
    monkeypatch.setattr(
        secrets_mod.secrets_manager,
        "delete_secret",
        lambda sid, *a, **k: calls.append(sid) or True,
    )

    result = await infra.delete_infrastructure_host(host_id="h9", _user={"sub": "u"})

    assert result == {"status": "success", "id": "h9"}
    assert calls == ["h9"]


async def test_delete_unknown_host_returns_404(_hosts):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await infra.delete_infrastructure_host(host_id="missing", _user={"sub": "u"})

    assert exc.value.status_code == 404


async def test_delete_404_when_secret_delete_reports_missing(_hosts, monkeypatch):
    import api.secrets as secrets_mod
    from fastapi import HTTPException

    monkeypatch.setattr(
        secrets_mod.secrets_manager, "delete_secret", lambda sid, *a, **k: False
    )

    with pytest.raises(HTTPException) as exc:
        await infra.delete_infrastructure_host(host_id="h9", _user={"sub": "u"})

    assert exc.value.status_code == 404
