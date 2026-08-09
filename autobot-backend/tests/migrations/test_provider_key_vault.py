# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the LLM-provider-key vault capture + runtime resolution (#10088 / Task 7).

Runs against a real, disposable Postgres (migration-gate) so the envelope
crypto path (System-vault create/read/rotate) is exercised for real, not
mocked. Verifies: a captured key lands in the System vault; a second capture
of the same name is idempotent (rotates, not duplicates); the runtime
resolver (:func:`resolve_provider_key`) actually returns the vault-hydrated
value when the env var is unset; env vars always win over the vault; and no
plaintext value is ever logged.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.envelope_secrets_service import EnvelopeSecretsService
from services.provider_key_vault import (
    _hydrated_keys,
    capture_provider_key,
    hydrate_provider_keys_from_vault,
    resolve_provider_key,
)
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = bytes(range(32))
_SYSTEM_VAULT = VaultRef(VaultKind.SYSTEM)
_SENTINEL_USER = uuid.UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clear_hydration_cache():
    """The process-lifetime hydration cache must not leak between tests."""
    _hydrated_keys.clear()
    yield
    _hydrated_keys.clear()


async def test_capture_lands_in_system_vault(session):
    wrote = await capture_provider_key(
        session, name="OPENAI_API_KEY", plaintext="sk-test-key-1", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()
    assert wrote is True

    svc = EnvelopeSecretsService(root_key=_ROOT)
    secrets = await svc.list_for_vaults(session, accessible_vaults={_SYSTEM_VAULT})
    assert len(secrets) == 1
    assert secrets[0].name == "OPENAI_API_KEY"
    value = await svc.read(session, secret_id=secrets[0].id, accessible_vaults={_SYSTEM_VAULT})
    assert value == b"sk-test-key-1"


async def test_second_capture_rotates_not_duplicates(session):
    await capture_provider_key(
        session, name="OPENAI_API_KEY", plaintext="sk-first", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()
    await capture_provider_key(
        session, name="OPENAI_API_KEY", plaintext="sk-second", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()

    svc = EnvelopeSecretsService(root_key=_ROOT)
    secrets = await svc.list_for_vaults(session, accessible_vaults={_SYSTEM_VAULT})
    assert len(secrets) == 1  # no duplicate row
    value = await svc.read(session, secret_id=secrets[0].id, accessible_vaults={_SYSTEM_VAULT})
    assert value == b"sk-second"  # updated, not stale


async def test_non_provider_name_is_a_noop(session):
    wrote = await capture_provider_key(
        session, name="SOME_UNRELATED_SECRET", plaintext="whatever", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()
    assert wrote is False

    svc = EnvelopeSecretsService(root_key=_ROOT)
    secrets = await svc.list_for_vaults(session, accessible_vaults={_SYSTEM_VAULT})
    assert secrets == []


async def test_hydrate_finds_vault_only_key(session, monkeypatch):
    """A key with no env var set is discoverable via the System vault (dual-read)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    await capture_provider_key(
        session, name="ANTHROPIC_API_KEY", plaintext="claude-key-value", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()

    hydrated = await hydrate_provider_keys_from_vault(session, root_key=_ROOT)
    assert "ANTHROPIC_API_KEY" in hydrated
    # The runtime reader actually resolves through the new path (guards
    # against a write-only vault, #10088's Task 5 defect class).
    assert resolve_provider_key("ANTHROPIC_API_KEY", "") == "claude-key-value"


async def test_hydrate_skips_when_env_var_already_set(session, monkeypatch):
    """Env wins -- an Ansible-provisioned deployment is unaffected by the vault."""
    monkeypatch.setenv("GROQ_API_KEY", "env-value")
    await capture_provider_key(
        session, name="GROQ_API_KEY", plaintext="vault-value", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()

    hydrated = await hydrate_provider_keys_from_vault(session, root_key=_ROOT)
    assert "GROQ_API_KEY" not in hydrated  # env already set -- vault never even queried
    # resolve_provider_key: env value always wins over anything in the cache.
    assert resolve_provider_key("GROQ_API_KEY", "env-value") == "env-value"


async def test_hydrate_is_idempotent_second_run_noop(session, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    await capture_provider_key(
        session, name="MISTRAL_API_KEY", plaintext="mistral-value", created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()

    first = await hydrate_provider_keys_from_vault(session, root_key=_ROOT)
    second = await hydrate_provider_keys_from_vault(session, root_key=_ROOT)
    assert first == second == ["MISTRAL_API_KEY"]
    assert resolve_provider_key("MISTRAL_API_KEY", "") == "mistral-value"


async def test_resolve_without_env_or_vault_returns_empty(session):
    assert resolve_provider_key("OPENROUTER_API_KEY", "") == ""


async def test_capture_never_logs_secret_value(session, caplog):
    plaintext = "super-secret-plaintext-marker-xyz"
    with caplog.at_level("DEBUG"):
        await capture_provider_key(
            session, name="OPENAI_API_KEY", plaintext=plaintext, created_by=_SENTINEL_USER, root_key=_ROOT
        )
        await session.commit()
    assert plaintext not in caplog.text


async def test_hydrate_never_logs_secret_value(session, caplog, monkeypatch):
    monkeypatch.delenv("NOUS_API_KEY", raising=False)
    plaintext = "another-secret-plaintext-marker-abc"
    await capture_provider_key(
        session, name="NOUS_API_KEY", plaintext=plaintext, created_by=_SENTINEL_USER, root_key=_ROOT
    )
    await session.commit()

    with caplog.at_level("DEBUG"):
        await hydrate_provider_keys_from_vault(session, root_key=_ROOT)
    assert plaintext not in caplog.text


# #13311: the "every declared name has a real runtime reader" check used to
# live here as an ``inspect.getsource`` grep over
# ``provider_registry._populate_default_providers``.  It is now a behavioural
# test that records which names the registry actually resolves, and it moved to
# ``llm_shared/tests/test_provider_registry_key_coverage.py`` because this
# module is gated behind ``requires_postgres`` -- a coverage assertion that
# needs no database must not be skipped along with the migration tests.
