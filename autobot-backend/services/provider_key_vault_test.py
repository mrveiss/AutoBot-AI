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
