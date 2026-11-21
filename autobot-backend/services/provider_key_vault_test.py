# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The mirror's failure log names a registry label, never a credential (#16444).

`mirror_provider_key_best_effort(name, value, ...)` logs `name` when the vault
write fails. CodeQL flagged that as `py/clear-text-logging-sensitive-data`:
`api/secrets.py` unpacks `name` and `value` from one request model, and the
taint analysis treats every attribute of it alike, so the key's *name* inherited
the sensitivity of the key's *value*.

It is a false positive -- `name` passes a `VAULT_RESOLVED_CREDENTIAL_NAMES`
membership guard before it can reach the log -- but "it is fine, here is why" in
a comment does not break a taint path and does not survive a refactor. The log
now re-reads the label out of the frozenset, so the property holds by
construction. These tests pin the property, not the mechanism: they would fail
if someone restored the parameter, and they do not care how the re-read is spelt.
"""

from __future__ import annotations

import pytest

from services.provider_key_vault import VAULT_RESOLVED_CREDENTIAL_NAMES, mirror_provider_key_best_effort
from testkit.fake_async_session import FakeAsyncSession

_SECRET = "sk-not-a-real-key-0123456789"  # pragma: allowlist secret


def test_the_registry_is_not_empty() -> None:
    """Negative control: every test below passes vacuously on an empty registry."""
    assert VAULT_RESOLVED_CREDENTIAL_NAMES, "no registry members -- the guard has no subject"


@pytest.mark.asyncio
async def test_a_failed_mirror_logs_the_key_name_and_never_the_value(monkeypatch, caplog) -> None:
    """The diagnostic must survive: an operator still needs to know which key."""
    name = sorted(VAULT_RESOLVED_CREDENTIAL_NAMES)[0]

    def _boom() -> None:
        raise RuntimeError("no root key configured")

    monkeypatch.setattr("user_management.database.get_async_session_factory", _boom, raising=False)

    with caplog.at_level("WARNING"):
        wrote = await mirror_provider_key_best_effort(name, _SECRET, created_by=None)

    assert wrote is False
    logged = caplog.text
    assert name in logged, "the key name was dropped; the failure is no longer diagnosable"
    assert _SECRET not in logged, "the credential reached the log"


@pytest.mark.asyncio
async def test_an_unrecognised_name_never_reaches_the_mirror_at_all(caplog) -> None:
    """The guard returns before any vault work, so nothing is logged for it."""
    with caplog.at_level("WARNING"):
        wrote = await mirror_provider_key_best_effort("NOT_A_REGISTRY_NAME", _SECRET, created_by=None)

    assert wrote is False
    assert "NOT_A_REGISTRY_NAME" not in caplog.text


class _SessionOpenFails:
    async def __aenter__(self):
        raise ConnectionRefusedError("down")

    async def __aexit__(self, *exc) -> None:
        return None


def _factory(session_cls):
    return lambda: session_cls


async def _unreachable_log(monkeypatch, caplog, session_cls, **patched) -> str:
    from services import provider_key_vault as vault

    for attr, fn in patched.items():
        monkeypatch.setattr(vault, attr, fn)
    with caplog.at_level("ERROR"):
        assert await vault.hydrate_at_startup(_factory(session_cls)) == []
    return caplog.text


@pytest.mark.asyncio
async def test_an_unreachable_vault_log_names_the_stage_that_failed_and_the_exception_class(
    monkeypatch, caplog
) -> None:
    async def _list_fails(_session, _name):
        raise TimeoutError("slow")

    async def _found(_session, _name):
        return "id-1"

    async def _register_fails(_session, **_kw):
        raise PermissionError("denied")

    opened = await _unreachable_log(monkeypatch, caplog, _SessionOpenFails)
    assert "stage: open session" in opened and "ConnectionRefusedError" in opened
    caplog.clear()
    listed = await _unreachable_log(monkeypatch, caplog, FakeAsyncSession, _find_system_secret_id=_list_fails)
    assert "stage: list" in listed and "TimeoutError" in listed
    caplog.clear()
    registered = await _unreachable_log(
        monkeypatch,
        caplog,
        FakeAsyncSession,
        _find_system_secret_id=_found,
        _register_credential_dependency=_register_fails,
    )
    assert "stage: register dependency" in registered and "PermissionError" in registered


@pytest.mark.asyncio
async def test_the_failed_hydration_still_refuses_every_vault_resolved_name(monkeypatch, caplog) -> None:
    from services import provider_key_vault as vault

    await _unreachable_log(monkeypatch, caplog, _SessionOpenFails)
    assert vault._vault_state == vault.VAULT_UNREACHABLE


@pytest.mark.asyncio
async def test_a_transient_vault_failure_then_success_ends_with_the_key_loaded(monkeypatch) -> None:
    """#21089 AC5: the first hydration hits a transient DB error, the second succeeds; the key resolves."""
    from services import provider_key_vault as vault

    name = "GROQ_API_KEY"  # pragma: allowlist secret
    attempts: list[int] = []

    async def _found(_session, _name):
        return "id-1" if _name == name else None

    async def _registered(_session, **_kw) -> None:
        return None

    async def _read(_session, _service, *, name, secret_id):  # noqa: ARG001 - external boundary stub
        return "vaulted-value-1"  # pragma: allowlist secret

    def _flaky_factory():
        attempts.append(1)
        return _SessionOpenFails() if len(attempts) == 1 else FakeAsyncSession()

    monkeypatch.setattr(vault, "_find_system_secret_id", _found)
    monkeypatch.setattr(vault, "_register_credential_dependency", _registered)
    monkeypatch.setattr(vault, "_read_one_key", _read)
    monkeypatch.setattr(vault, "_hydrated_keys", {})
    monkeypatch.setattr(vault, "_unreadable_keys", set())
    monkeypatch.setattr(vault, "_vault_state", vault.VAULT_NOT_HYDRATED)
    # resolve_provider_key retries an unreachable vault through the process-init hook; this test drives
    # the retry itself, so the hook must not hydrate behind it.
    monkeypatch.setattr("services.provider_key_process_init.hydrate_this_process", lambda: [])

    assert await vault.hydrate_at_startup(lambda: _flaky_factory) == []
    assert vault._vault_state == vault.VAULT_UNREACHABLE and len(attempts) == 1
    with pytest.raises(vault.VaultKeyUnavailableError):
        vault.resolve_provider_key(name, "env-value")  # pragma: allowlist secret

    assert await vault.hydrate_at_startup(lambda: _flaky_factory) == [name]
    assert len(attempts) == 2
    assert vault._vault_state == vault.VAULT_REACHABLE
    assert vault.resolve_provider_key(name, "env-value") == "vaulted-value-1"  # pragma: allowlist secret
