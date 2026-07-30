# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for the system_secrets -> System vault bridge (#10088 Task 6a).

The slm-backend root conftest stubs ``sqlalchemy`` / ``models.database`` /
``services.encryption`` etc. as MagicMocks for api/* tests. Following the
established real-load pattern
(``user_management/services/sso_secrets_test.py``, #11737/#11794/#10153),
this module swaps in the REAL sqlalchemy + product modules at import time,
binds what it needs, then restores the stubs so sibling test files are
unaffected.

The System vault itself (a separate service, autobot-backend) is faked with
an in-memory ``_FakeVault`` double patched onto the real, loaded
``user_management.services.vault_client`` module — this exercises the
actual name-lookup / create / read / delete logic in
``system_secrets_vault.py`` without any live HTTP dependency.
"""

import contextlib
import importlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

_SLM_ROOT = Path(__file__).parent.parent
for _p in (str(_SLM_ROOT), str(_SLM_ROOT.parent)):  # slm root + repo root (autobot_shared)
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("SLM_ENCRYPTION_KEY", "unit-test-encryption-key-0123456789abcdef")

_SWAP_PREFIXES = ("sqlalchemy", "aiosqlite")
_SWAP_KEYS = (
    "models.database",
    "services.encryption",
    "services.system_secrets_vault",
    "user_management.services.vault_client",
)


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or any(name == p or name.startswith(p + ".") for p in _SWAP_PREFIXES)


def _load_real_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
for _name in list(_orig_modules):
    del sys.modules[_name]
try:
    for _name in (
        "sqlalchemy",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.orm",
        "sqlalchemy.dialects.sqlite.aiosqlite",
    ):
        importlib.import_module(_name)

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    _real_md = _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
    _real_enc = _load_real_module("services.encryption", _SLM_ROOT / "services" / "encryption.py")
    _real_vc = _load_real_module(
        "user_management.services.vault_client",
        _SLM_ROOT / "user_management" / "services" / "vault_client.py",
    )
    _real_ssv = _load_real_module(
        "services.system_secrets_vault",
        _SLM_ROOT / "services" / "system_secrets_vault.py",
    )

    Base = _real_md.Base
    SystemSecret = _real_md.SystemSecret
    encrypt_data = _real_enc.encrypt_data
    ssv = _real_ssv

    _REAL_MODULES = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
finally:
    for _name in [name for name in sys.modules if _is_swap_key(name)]:
        del sys.modules[_name]
    for _name, _mod in _orig_modules.items():
        sys.modules[_name] = _mod


@contextlib.contextmanager
def _real_modules_swapped():
    saved = {name: sys.modules.get(name) for name in _REAL_MODULES}
    sys.modules.update(_REAL_MODULES)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


class _FakeVault:
    """In-memory double for the System vault's HTTP surface (name -> plaintext)."""

    def __init__(self) -> None:
        self.entries: dict[uuid.UUID, dict] = {}
        self.configured = True

    def is_configured(self) -> bool:
        return self.configured

    async def vault_create(self, name: str, secret_type: str, value: str) -> dict:
        secret_id = uuid.uuid4()
        self.entries[secret_id] = {"id": str(secret_id), "name": name, "value": value, "type": secret_type}
        return self.entries[secret_id]

    async def vault_read(self, secret_id: uuid.UUID) -> str:
        entry = self.entries.get(secret_id)
        if entry is None:
            raise _real_vc.VaultSecretNotFound(str(secret_id))
        return entry["value"]

    async def vault_list(self) -> list:
        return list(self.entries.values())

    async def vault_delete(self, secret_id: uuid.UUID) -> None:
        self.entries.pop(secret_id, None)


@pytest.fixture
def fake_vault(monkeypatch):
    """Patch the real, loaded vault_client's module-level functions with a fake."""
    with _real_modules_swapped():
        fv = _FakeVault()
        monkeypatch.setattr(_real_vc, "is_configured", fv.is_configured)
        monkeypatch.setattr(_real_vc, "vault_create", fv.vault_create)
        monkeypatch.setattr(_real_vc, "vault_read", fv.vault_read)
        monkeypatch.setattr(_real_vc, "vault_list", fv.vault_list)
        monkeypatch.setattr(_real_vc, "vault_delete", fv.vault_delete)
        yield fv


@pytest.fixture
async def async_session():
    with _real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async_session_maker = sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session_maker() as session:
            yield session
        await engine.dispose()


async def _add_legacy(session, key: str, value: str) -> None:
    with _real_modules_swapped():
        session.add(SystemSecret(key=key, encrypted_value=encrypt_data(value), category="system"))
        await session.commit()


class TestIsMigratable:
    def test_irreducible_key_rejected(self):
        with _real_modules_swapped():
            assert ssv.is_migratable("autobot_internal_api_key") is False

    def test_sso_prefixed_key_rejected(self):
        with _real_modules_swapped():
            assert ssv.is_migratable(f"sso:provider:{uuid.uuid4()}:client_secret") is False

    def test_ordinary_key_accepted(self):
        with _real_modules_swapped():
            assert ssv.is_migratable("hf_token") is True


class TestRetrieveSecret:
    @pytest.mark.asyncio
    async def test_legacy_first_when_present(self, async_session, fake_vault):
        with _real_modules_swapped():
            await _add_legacy(async_session, "hf_token", "legacy-value")
            # Also seed a DIFFERENT (stale) vault copy to prove legacy wins.
            await fake_vault.vault_create("hf_token", "system-secret", "stale-vault-value")

            value = await ssv.retrieve_secret(async_session, "hf_token")
            assert value == "legacy-value"

    @pytest.mark.asyncio
    async def test_falls_back_to_vault_when_legacy_absent(self, async_session, fake_vault):
        with _real_modules_swapped():
            await fake_vault.vault_create("hf_token", "system-secret", "vault-only-value")
            value = await ssv.retrieve_secret(async_session, "hf_token")
            assert value == "vault-only-value"

    @pytest.mark.asyncio
    async def test_returns_none_when_absent_everywhere(self, async_session, fake_vault):
        with _real_modules_swapped():
            assert await ssv.retrieve_secret(async_session, "nonexistent_key") is None

    @pytest.mark.asyncio
    async def test_irreducible_key_never_reads_vault(self, async_session, fake_vault):
        """Even if a vault entry somehow exists under this name, it must never be read."""
        with _real_modules_swapped():
            await fake_vault.vault_create("autobot_internal_api_key", "system-secret", "should-never-surface")
            assert await ssv.retrieve_secret(async_session, "autobot_internal_api_key") is None

    @pytest.mark.asyncio
    async def test_not_configured_returns_none_without_legacy(self, async_session, fake_vault):
        with _real_modules_swapped():
            fake_vault.configured = False
            assert await ssv.retrieve_secret(async_session, "hf_token") is None


class TestMigrateKeyToVault:
    @pytest.mark.asyncio
    async def test_migrates_eligible_key(self, async_session, fake_vault):
        with _real_modules_swapped():
            await _add_legacy(async_session, "hf_token", "the-hf-token")
            migrated = await ssv.migrate_key_to_vault(async_session, "hf_token")
            assert migrated is True
            entries = await fake_vault.vault_list()
            assert any(e["name"] == "hf_token" and e["value"] == "the-hf-token" for e in entries)

    @pytest.mark.asyncio
    async def test_second_run_is_a_noop(self, async_session, fake_vault):
        with _real_modules_swapped():
            await _add_legacy(async_session, "hf_token", "the-hf-token")
            first = await ssv.migrate_key_to_vault(async_session, "hf_token")
            second = await ssv.migrate_key_to_vault(async_session, "hf_token")
            assert first is True
            assert second is False  # already migrated — no duplicate vault entry
            entries = await fake_vault.vault_list()
            assert len([e for e in entries if e["name"] == "hf_token"]) == 1

    @pytest.mark.asyncio
    async def test_skips_irreducible_key(self, async_session, fake_vault):
        with _real_modules_swapped():
            await _add_legacy(async_session, "autobot_internal_api_key", "the-internal-key")
            migrated = await ssv.migrate_key_to_vault(async_session, "autobot_internal_api_key")
            assert migrated is False
            assert await fake_vault.vault_list() == []

    @pytest.mark.asyncio
    async def test_skips_sso_prefixed_key(self, async_session, fake_vault):
        provider_id = uuid.uuid4()
        key = f"sso:provider:{provider_id}:client_secret"
        with _real_modules_swapped():
            await _add_legacy(async_session, key, "sso-secret-value")
            migrated = await ssv.migrate_key_to_vault(async_session, key)
            assert migrated is False
            assert await fake_vault.vault_list() == []

    @pytest.mark.asyncio
    async def test_absent_legacy_key_not_migrated(self, async_session, fake_vault):
        with _real_modules_swapped():
            migrated = await ssv.migrate_key_to_vault(async_session, "hf_token")
            assert migrated is False

    @pytest.mark.asyncio
    async def test_vault_not_configured_skips(self, async_session, fake_vault):
        with _real_modules_swapped():
            await _add_legacy(async_session, "hf_token", "the-hf-token")
            fake_vault.configured = False
            migrated = await ssv.migrate_key_to_vault(async_session, "hf_token")
            assert migrated is False


class TestDeleteVaultCopy:
    @pytest.mark.asyncio
    async def test_revoked_secret_cannot_resurrect(self, async_session, fake_vault):
        """Delete legacy + vault copy => retrieve_secret finds it nowhere (no resurrection)."""
        with _real_modules_swapped():
            await _add_legacy(async_session, "hf_token", "the-hf-token")
            await ssv.migrate_key_to_vault(async_session, "hf_token")

            # Simulate the legacy DELETE endpoint's row removal.
            from sqlalchemy import delete as sa_delete

            await async_session.execute(sa_delete(SystemSecret).where(SystemSecret.key == "hf_token"))
            await async_session.commit()

            # Without the dual-delete, this would resurrect via the vault fallback.
            await ssv.delete_vault_copy("hf_token")

            assert await ssv.retrieve_secret(async_session, "hf_token") is None

    @pytest.mark.asyncio
    async def test_delete_vault_copy_is_idempotent(self, fake_vault):
        with _real_modules_swapped():
            await ssv.delete_vault_copy("never_existed")  # must not raise
            await ssv.delete_vault_copy("never_existed")

    @pytest.mark.asyncio
    async def test_delete_vault_copy_never_touches_irreducible_key(self, fake_vault):
        with _real_modules_swapped():
            await fake_vault.vault_create("autobot_internal_api_key", "system-secret", "value")
            await ssv.delete_vault_copy("autobot_internal_api_key")
            # Entry untouched (guard returns before ever calling vault_delete).
            entries = await fake_vault.vault_list()
            assert any(e["name"] == "autobot_internal_api_key" for e in entries)


class TestNoSecretValueLogged:
    @pytest.mark.asyncio
    async def test_migrate_logging_never_includes_secret_value(self, async_session, fake_vault, caplog):
        with _real_modules_swapped():
            secret_value = "super-secret-plaintext-marker-xyz"
            await _add_legacy(async_session, "hf_token", secret_value)
            with caplog.at_level("INFO"):
                await ssv.migrate_key_to_vault(async_session, "hf_token")
            for record in caplog.records:
                assert secret_value not in record.getMessage()

    @pytest.mark.asyncio
    async def test_retrieve_logging_never_includes_secret_value(self, async_session, fake_vault, caplog):
        with _real_modules_swapped():
            secret_value = "another-secret-plaintext-marker-abc"
            await fake_vault.vault_create("hf_token", "system-secret", secret_value)
            with caplog.at_level("INFO"):
                value = await ssv.retrieve_secret(async_session, "hf_token")
            assert value == secret_value
            for record in caplog.records:
                assert secret_value not in record.getMessage()
