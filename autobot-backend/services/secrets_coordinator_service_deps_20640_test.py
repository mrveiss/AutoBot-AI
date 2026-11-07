# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20640: the REAL coordinator's service-identity dependents listing is system-vault only.

``service_describe_dependencies`` feeds the envelope service delete. The route tests use a fake
coordinator, so the authorization here is exercised against the real class: a secret owned by
a company or user vault is refused before any dependents are read; a system-owned one is listed.
"""

import uuid
from types import SimpleNamespace

import pytest

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError
from services.secrets_coordinator import SecretsCoordinator
from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_result import FakeResult

_SECRET = uuid.UUID("22222222-2222-4222-8222-222222222222")
_SYSTEM = VaultRef(VaultKind.SYSTEM)
_DEP = SimpleNamespace(dependent_kind="service", dependent_id="scheduler")


def _session(owner: str | None, dependents=()):
    """Answers the owner lookup first, then the dependents query; the statements are recorded."""
    return FakeAsyncSession(results=[FakeResult([] if owner is None else [owner]), FakeResult(list(dependents))])


def _coordinator() -> SecretsCoordinator:
    return SecretsCoordinator(SimpleNamespace())


async def test_a_system_owned_secret_lists_its_dependents() -> None:
    session = _session(_SYSTEM.to_str(), [_DEP])

    deps = await _coordinator().service_describe_dependencies(session, secret_id=_SECRET, vault=_SYSTEM)

    assert deps == [_DEP]
    assert _SECRET in set(session.statements[0].compile().params.values()), "the owner lookup is keyed to the secret"


@pytest.mark.parametrize("owner", [f"company:{_SECRET}", f"user:{_SECRET}"])
async def test_a_non_system_owned_secret_is_refused_before_dependents_are_read(owner) -> None:
    session = _session(owner, [_DEP])

    with pytest.raises(SecretAccessError):
        await _coordinator().service_describe_dependencies(session, secret_id=_SECRET, vault=_SYSTEM)

    assert len(session.statements) == 1, "the dependents query must not run for a refused caller"


async def test_a_missing_secret_is_not_found() -> None:
    with pytest.raises(SecretNotFoundError):
        await _coordinator().service_describe_dependencies(_session(None), secret_id=_SECRET, vault=_SYSTEM)


async def test_a_service_cannot_name_another_vault() -> None:
    with pytest.raises(SecretAccessError):
        await _coordinator().service_describe_dependencies(
            _session(_SYSTEM.to_str()), secret_id=_SECRET, vault=VaultRef(VaultKind.USER, str(_SECRET))
        )


async def test_service_delete_shares_the_same_owner_check() -> None:
    session = FakeAsyncSession(results=[FakeResult([f"company:{_SECRET}"])])

    with pytest.raises(SecretAccessError):
        await _coordinator().service_delete(session, secret_id=_SECRET, vault=_SYSTEM)
