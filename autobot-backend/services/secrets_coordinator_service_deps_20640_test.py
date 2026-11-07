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
from services.secrets_authz import PrincipalFacts
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


_COMPANY = uuid.UUID("33333333-3333-4333-8333-333333333333")
_USER = uuid.UUID("44444444-4444-4444-8444-444444444444")


def _member(role: str) -> SecretsCoordinator:
    """A coordinator whose principal holds *role* in the company that owns the secret."""
    coordinator = _coordinator()

    async def facts(*_a, **_k) -> PrincipalFacts:
        return PrincipalFacts(user_id=str(_USER), company_roles={str(_COMPANY): role})

    coordinator._facts = facts
    return coordinator


async def test_a_write_only_member_lists_dependents_for_a_delete() -> None:
    """A company member can write but not share: the delete's listing must not need `share`."""
    owner = f"company:{_COMPANY}"
    listing = await _member("member").describe_dependencies_for_delete(
        _session(owner, [_DEP]), user_id=_USER, permissions=set(), secret_id=_SECRET
    )
    assert listing == [_DEP]
    with pytest.raises(SecretAccessError):
        await _member("member").describe_dependencies(
            _session(owner, [_DEP]), user_id=_USER, permissions=set(), secret_id=_SECRET
        )


async def test_a_guest_cannot_list_dependents_for_a_delete_it_may_not_make() -> None:
    session = _session(f"company:{_COMPANY}", [_DEP])

    with pytest.raises(SecretAccessError):
        await _member("guest").describe_dependencies_for_delete(
            session, user_id=_USER, permissions=set(), secret_id=_SECRET
        )

    assert len(session.statements) == 1, "the dependents query must not run for a refused caller"


async def test_registering_a_dependency_on_a_non_envelope_row_is_not_found_and_inserts_nothing() -> None:
    """A legacy row (NULL sealed_value) is not in the owner lookup, so nothing can depend on it."""
    session = _session(None)

    with pytest.raises(SecretNotFoundError):
        await _member("owner").register_dependency(
            session,
            user_id=_USER,
            permissions=set(),
            secret_id=_SECRET,
            dependent_kind="service",
            dependent_id="scheduler",
        )

    assert len(session.statements) == 1, "only the owner lookup ran; no dependency was inserted"
    assert "sealed_value IS NOT NULL" in str(session.statements[0].compile())
