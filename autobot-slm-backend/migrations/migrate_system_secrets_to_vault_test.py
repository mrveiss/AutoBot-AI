# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the system_secrets -> System vault import script (#10088 Task 6a).

Real-load pattern (same technique as
``user_management/services/sso_secrets_test.py`` /
``services/system_secrets_vault_test.py``): swaps in the real sqlalchemy +
product modules over an in-memory SQLite DB, with the System vault faked by
an in-memory double patched onto the real, loaded ``vault_client`` module.

Also manually verified end-to-end against a disposable local Postgres 16
instance (private ``initdb``, not the shared host cluster) — see PR
description for the run transcript: migrated hf_token + scim_bearer_token,
skipped autobot_internal_api_key (irreducible), second run made zero
additional vault writes, and the legacy ``system_secrets`` rows were
untouched throughout.
"""

import importlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

_SLM_ROOT = Path(__file__).parent.parent
for _p in (str(_SLM_ROOT), str(_SLM_ROOT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("SLM_ENCRYPTION_KEY", "unit-test-encryption-key-0123456789abcdef")
os.environ.setdefault("AUTOBOT_INTERNAL_API_KEY", "unit-test-internal-api-key")

_SWAP_KEYS = (
    "models.database",
    "services.encryption",
    "services.system_secrets_vault",
    "migrations.migrate_system_secrets_to_vault",
    "user_management.services.vault_client",
)


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or any(name == p or name.startswith(p + ".") for p in ("sqlalchemy", "aiosqlite"))


def _load_real_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class _FakeVault:
    """In-memory double for the System vault's HTTP surface (name -> plaintext)."""

    def __init__(self) -> None:
        self.entries: dict[uuid.UUID, dict] = {}

    def is_configured(self) -> bool:
        return True

    async def vault_create(self, name: str, secret_type: str, value: str) -> dict:
        secret_id = uuid.uuid4()
        self.entries[secret_id] = {"id": str(secret_id), "name": name, "value": value, "type": secret_type}
        return self.entries[secret_id]

    async def vault_list(self) -> list:
        return list(self.entries.values())


@pytest.fixture
def migration_env(monkeypatch, tmp_path):
    """Real-loaded modules + an in-memory SQLite DB seeded with system_secrets rows."""
    orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
    for name in list(orig_modules):
        del sys.modules[name]
    try:
        for name in ("sqlalchemy", "sqlalchemy.ext.asyncio", "sqlalchemy.orm", "sqlalchemy.dialects.sqlite.aiosqlite"):
            importlib.import_module(name)

        md = _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
        enc = _load_real_module("services.encryption", _SLM_ROOT / "services" / "encryption.py")
        vc = _load_real_module(
            "user_management.services.vault_client", _SLM_ROOT / "user_management" / "services" / "vault_client.py"
        )
        _load_real_module("services.system_secrets_vault", _SLM_ROOT / "services" / "system_secrets_vault.py")
        mig = _load_real_module(
            "migrations.migrate_system_secrets_to_vault",
            _SLM_ROOT / "migrations" / "migrate_system_secrets_to_vault.py",
        )

        fv = _FakeVault()
        monkeypatch.setattr(vc, "is_configured", fv.is_configured)
        monkeypatch.setattr(vc, "vault_create", fv.vault_create)
        monkeypatch.setattr(vc, "vault_list", fv.vault_list)

        db_path = tmp_path / "system_secrets_migration_test.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"

        import asyncio

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        async def _seed():
            engine = create_async_engine(db_url, echo=False)  # canonical: ignore py-adhoc-db-engine
            async with engine.begin() as conn:
                await conn.run_sync(md.Base.metadata.create_all)
            session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with session_maker() as session:
                session.add(md.SystemSecret(key="hf_token", encrypted_value=enc.encrypt_data("real-hf-token")))
                session.add(
                    md.SystemSecret(
                        key="autobot_internal_api_key", encrypted_value=enc.encrypt_data("irreducible-value")
                    )
                )
                session.add(
                    md.SystemSecret(key="scim_bearer_token", encrypted_value=enc.encrypt_data("scim-token-value"))
                )
                await session.commit()
            await engine.dispose()

        asyncio.run(_seed())

        yield mig, fv, db_url
    finally:
        for name in [name for name in sys.modules if _is_swap_key(name)]:
            del sys.modules[name]
        for name, mod in orig_modules.items():
            sys.modules[name] = mod


class TestMigrateSystemSecretsToVault:
    def test_migrates_eligible_keys_only(self, migration_env):
        mig, fv, db_url = migration_env
        mig.migrate(db_url)

        names = {e["name"] for e in fv.entries.values()}
        assert names == {"hf_token", "scim_bearer_token"}
        assert "autobot_internal_api_key" not in names

    def test_second_run_is_a_noop(self, migration_env):
        mig, fv, db_url = migration_env
        mig.migrate(db_url)
        count_after_first = len(fv.entries)

        mig.migrate(db_url)
        count_after_second = len(fv.entries)

        assert count_after_first == count_after_second == 2

    def test_migrated_values_match_source(self, migration_env):
        mig, fv, db_url = migration_env
        mig.migrate(db_url)

        by_name = {e["name"]: e["value"] for e in fv.entries.values()}
        assert by_name["hf_token"] == "real-hf-token"
        assert by_name["scim_bearer_token"] == "scim-token-value"

    def test_require_env_aborts_without_encryption_key(self, monkeypatch, migration_env):
        mig, _fv, db_url = migration_env
        monkeypatch.delenv("SLM_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SLM_SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="SLM_ENCRYPTION_KEY or SLM_SECRET_KEY"):
            mig.migrate(db_url)

    def test_require_env_aborts_without_vault_auth(self, monkeypatch, migration_env):
        mig, _fv, db_url = migration_env
        monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY", raising=False)
        monkeypatch.delenv("SLM_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SLM_SERVICE_ID", raising=False)

        with pytest.raises(RuntimeError, match="vault auth"):
            mig.migrate(db_url)
