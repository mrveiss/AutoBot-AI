# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration tests for SSO encrypted credential storage (MVA-3883, GH#9685).

Tests SSOSecretsManager for:
- Creating and encrypting SSO provider secrets
- Updating encrypted secrets
- Deleting provider secrets
- Migrating plaintext to encrypted storage
- Handling decryption failures gracefully

The slm-backend root conftest stubs ``sqlalchemy`` / ``models.database`` /
``services.encryption`` as MagicMocks for api/* tests, so bare imports here
would run against inert mock chains (``create_async_engine`` returning a
MagicMock that cannot be awaited — the exact never-run failure #11798 fixed).
Following the established real-load pattern (tests/services/code_version_test.py,
#11737/#11794), this module swaps in the REAL sqlalchemy + product modules at
import time, binds what it needs, then restores the stubs so sibling test
files are unaffected.  The swap is re-activated for each test via the
``async_session`` fixture (``_real_modules_swapped()``) because
SSOSecretsManager resolves ``models.database`` / ``services.encryption`` /
``user_management.services.vault_client`` through sys.modules at call time.
"""

import contextlib
import importlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SLM_ROOT = Path(__file__).parent.parent.parent
for _p in (str(_SLM_ROOT), str(_SLM_ROOT.parent)):  # slm root + repo root (autobot_shared)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The real EncryptionService requires a master key at first use; provide a
# deterministic test-only default without clobbering a real environment.
os.environ.setdefault("SLM_ENCRYPTION_KEY", "unit-test-encryption-key-0123456789abcdef")

_SWAP_PREFIXES = ("sqlalchemy", "aiosqlite")
_SWAP_KEYS = (
    "models.database",
    "services.encryption",
    "user_management.services.vault_client",
    "user_management.services.sso_secrets",
)


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or any(name == p or name.startswith(p + ".") for p in _SWAP_PREFIXES)


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so runtime imports resolve)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# Snapshot and clear EVERY swapped key (not just the ones the root conftest
# stubs): earlier-collected files leave extra child stubs such as
# ``sqlalchemy.exc`` in sys.modules, and one cached MagicMock child poisons
# the real package import (see code_version_test.py, #11737).
_orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
for _name in list(_orig_modules):
    del sys.modules[_name]
try:
    for _name in (
        "sqlalchemy",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.orm",
        # The aiosqlite dialect is resolved lazily at create_async_engine()
        # time; import it now while the real package tree is intact.
        "sqlalchemy.dialects.sqlite.aiosqlite",
    ):
        importlib.import_module(_name)

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    _real_md = _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
    _real_enc = _load_real_module("services.encryption", _SLM_ROOT / "services" / "encryption.py")
    _real_vc = _load_real_module(
        "user_management.services.vault_client",
        _SLM_ROOT / "user_management" / "services" / "vault_client.py",
    )
    # Force the legacy SystemSecret code path deterministically: an env with
    # AUTOBOT_INTERNAL_API_KEY / SLM_SERVICE_KEY set would flip is_configured()
    # and route store/retrieve to live HTTP vault calls.  This mutates only our
    # private real-loaded instance, never the conftest stub other files see.
    _real_vc._INTERNAL_API_KEY = ""
    _real_vc._SERVICE_KEY = ""
    _real_sso = _load_real_module(
        "user_management.services.sso_secrets",
        _SLM_ROOT / "user_management" / "services" / "sso_secrets.py",
    )

    Base = _real_md.Base
    SystemSecret = _real_md.SystemSecret
    decrypt_data = _real_enc.decrypt_data
    SSOSecretsManager = _real_sso.SSOSecretsManager

    _REAL_MODULES = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
finally:
    for _name in [name for name in sys.modules if _is_swap_key(name)]:
        del sys.modules[_name]
    for _name, _mod in _orig_modules.items():
        sys.modules[_name] = _mod


@contextlib.contextmanager
def _real_modules_swapped():
    """Temporarily put the real sqlalchemy/product modules back into sys.modules."""
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


# Test fixtures setup
@pytest.fixture
async def async_session():
    """Create an async test database session (real modules swapped in)."""
    with _real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)  # canonical: ignore py-adhoc-db-engine

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create session factory
        async_session_maker = sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_maker() as session:
            yield session

        await engine.dispose()


@pytest.fixture
def provider_id():
    """Generate a test provider UUID."""
    return uuid.uuid4()


@pytest.fixture
def oauth_config():
    """Sample OAuth provider config with plaintext secrets."""
    return {
        "client_id": "test_client_123",
        "client_secret": "secret_abc_oauth",
        "authorize_url": "https://provider.com/oauth/authorize",
        "token_url": "https://provider.com/oauth/token",
        "userinfo_url": "https://provider.com/oauth/userinfo",
        "scope": "openid email profile",
    }


@pytest.fixture
def ldap_config():
    """Sample LDAP provider config with plaintext bind password."""
    return {
        "server_url": "ldap://ldap.example.com:389",
        "bind_dn": "cn=admin,dc=example,dc=com",
        "bind_password": "ldap_secret_password_123",
        "base_dn": "dc=example,dc=com",
        "user_filter": "(uid={username})",
    }


class TestSSOSecretsManagerIntegration:
    """Integration tests for SSOSecretsManager with real async database."""

    @pytest.mark.asyncio
    async def test_store_secrets_creates_encrypted_secrets(self, async_session, provider_id, oauth_config):
        """Test that store_secrets extracts and encrypts sensitive fields."""
        manager = SSOSecretsManager(async_session)

        # Store secrets
        sanitized = await manager.store_secrets(provider_id, oauth_config)
        await async_session.commit()

        # Verify sanitized config has reference, not plaintext
        assert "client_secret" not in sanitized
        assert "client_secret_ref" in sanitized
        assert sanitized["client_secret_ref"] == f"sso:provider:{provider_id}:client_secret"

        # Verify other fields preserved
        assert sanitized["client_id"] == "test_client_123"
        assert sanitized["authorize_url"] == "https://provider.com/oauth/authorize"

        # Verify secret stored encrypted in database
        result = await async_session.execute(
            select(SystemSecret).where(SystemSecret.key == f"sso:provider:{provider_id}:client_secret")
        )
        secret = result.scalar_one()

        assert secret is not None
        assert secret.category == "sso"
        assert secret.encrypted_value != "secret_abc_oauth"

        # Verify decryption works
        decrypted = decrypt_data(secret.encrypted_value)
        assert decrypted == "secret_abc_oauth"

    @pytest.mark.asyncio
    async def test_store_secrets_handles_multiple_sensitive_fields(self, async_session, provider_id, ldap_config):
        """Test storing config with bind_password field."""
        manager = SSOSecretsManager(async_session)

        # Store LDAP config with bind_password
        sanitized = await manager.store_secrets(provider_id, ldap_config)
        await async_session.commit()

        # Verify bind_password was extracted
        assert "bind_password" not in sanitized
        assert "bind_password_ref" in sanitized
        assert sanitized["bind_dn"] == "cn=admin,dc=example,dc=com"

        # Verify secret stored in database
        result = await async_session.execute(
            select(SystemSecret).where(SystemSecret.key == f"sso:provider:{provider_id}:bind_password")
        )
        secret = result.scalar_one()

        decrypted = decrypt_data(secret.encrypted_value)
        assert decrypted == "ldap_secret_password_123"

    @pytest.mark.asyncio
    async def test_store_secrets_updates_existing_secret(self, async_session, provider_id, oauth_config):
        """Test that updating provider updates the encrypted secret."""
        manager = SSOSecretsManager(async_session)

        # Store initial secret
        await manager.store_secrets(provider_id, oauth_config)
        await async_session.commit()

        # Update with new secret
        new_config = oauth_config.copy()
        new_config["client_secret"] = "new_secret_xyz"

        await manager.store_secrets(provider_id, new_config)
        await async_session.commit()

        # Verify updated secret in database
        result = await async_session.execute(
            select(SystemSecret).where(SystemSecret.key == f"sso:provider:{provider_id}:client_secret")
        )
        secret = result.scalar_one()

        decrypted = decrypt_data(secret.encrypted_value)
        assert decrypted == "new_secret_xyz"

    @pytest.mark.asyncio
    async def test_retrieve_secret_decrypts_successfully(self, async_session, provider_id, oauth_config):
        """Test retrieving and decrypting a stored secret."""
        manager = SSOSecretsManager(async_session)

        # Store secret first
        await manager.store_secrets(provider_id, oauth_config)
        await async_session.commit()

        # Retrieve and verify
        decrypted = await manager.retrieve_secret(provider_id, "client_secret")
        assert decrypted == "secret_abc_oauth"

    @pytest.mark.asyncio
    async def test_retrieve_secret_returns_none_for_missing(self, async_session, provider_id):
        """Test that retrieve_secret returns None for non-existent secret."""
        manager = SSOSecretsManager(async_session)

        # Try to retrieve non-existent secret
        result = await manager.retrieve_secret(provider_id, "client_secret")
        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_secret_handles_decryption_failure(self, async_session, provider_id):
        """Test graceful handling of decryption failures."""
        manager = SSOSecretsManager(async_session)

        # Store a secret with corrupted encryption
        secret = SystemSecret(
            key=f"sso:provider:{provider_id}:client_secret",
            encrypted_value="corrupted_data_that_cant_decrypt",
            category="sso",
            description=f"SSO client_secret for provider {provider_id}",
        )
        async_session.add(secret)
        await async_session.commit()

        # Attempt to retrieve should raise ValueError with clear message
        with pytest.raises(ValueError, match="Failed to decrypt secret client_secret"):
            await manager.retrieve_secret(provider_id, "client_secret")

    @pytest.mark.asyncio
    async def test_delete_secrets_removes_all_provider_secrets(self, async_session, provider_id, oauth_config):
        """Test that delete_secrets removes all associated secrets."""
        manager = SSOSecretsManager(async_session)

        # Store secrets
        await manager.store_secrets(provider_id, oauth_config)
        await async_session.commit()

        # Verify secret exists
        result = await async_session.execute(
            select(SystemSecret).where(SystemSecret.key == f"sso:provider:{provider_id}:client_secret")
        )
        assert result.scalar_one_or_none() is not None

        # Delete all secrets for provider
        await manager.delete_secrets(provider_id)
        await async_session.commit()

        # Verify secret deleted
        result = await async_session.execute(
            select(SystemSecret).where(SystemSecret.key == f"sso:provider:{provider_id}:client_secret")
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_has_plaintext_secrets_detects_plaintext(self, oauth_config):
        """Test detection of plaintext secrets in config."""
        manager = SSOSecretsManager(AsyncMock())

        # Config with plaintext secret
        assert await manager.has_plaintext_secrets(oauth_config) is True

        # Config without sensitive fields
        safe_config = {"client_id": "test_123", "authorize_url": "https://example.com"}
        assert await manager.has_plaintext_secrets(safe_config) is False

    @pytest.mark.asyncio
    async def test_migrate_plaintext_to_secrets_converts_successfully(self, async_session, provider_id, oauth_config):
        """Test migration from plaintext to encrypted storage."""
        manager = SSOSecretsManager(async_session)

        # Migrate plaintext config
        sanitized = await manager.migrate_plaintext_to_secrets(provider_id, oauth_config)
        await async_session.commit()

        # Verify migration created encrypted secrets
        assert "client_secret" not in sanitized
        assert "client_secret_ref" in sanitized

        # Verify secret can be retrieved
        decrypted = await manager.retrieve_secret(provider_id, "client_secret")
        assert decrypted == "secret_abc_oauth"

    @pytest.mark.asyncio
    async def test_migrate_plaintext_skips_already_migrated(self, async_session, provider_id):
        """Test that migration skips configs without plaintext secrets."""
        manager = SSOSecretsManager(async_session)

        # Config already migrated (has references)
        migrated_config = {
            "client_id": "test_123",
            "client_secret_ref": f"sso:provider:{provider_id}:client_secret",
        }

        # Should return unchanged
        result = await manager.migrate_plaintext_to_secrets(provider_id, migrated_config)
        assert result == migrated_config

    @pytest.mark.asyncio
    async def test_store_secrets_handles_empty_secret_values(self, async_session, provider_id):
        """Test that empty/null secret values are not stored."""
        manager = SSOSecretsManager(async_session)

        # Config with empty client_secret
        config = {
            "client_id": "test_123",
            "client_secret": "",
            "authorize_url": "https://example.com",
        }

        sanitized = await manager.store_secrets(provider_id, config)
        await async_session.commit()

        # Empty values should not create secrets
        result = await async_session.execute(
            select(SystemSecret).where(SystemSecret.key == f"sso:provider:{provider_id}:client_secret")
        )
        assert result.scalar_one_or_none() is None

        # Sanitized config should not have reference either
        assert "client_secret_ref" not in sanitized


class TestSSOSecretsManagerEdgeCases:
    """Edge case tests for SSOSecretsManager."""

    @pytest.mark.asyncio
    async def test_concurrent_updates_to_same_secret(self, async_session, provider_id, oauth_config):
        """Test that concurrent updates don't corrupt secrets."""
        manager = SSOSecretsManager(async_session)

        # Store initial secret
        await manager.store_secrets(provider_id, oauth_config)
        await async_session.commit()

        # Simulate concurrent updates (in practice would be different sessions)
        config1 = oauth_config.copy()
        config1["client_secret"] = "concurrent_secret_1"

        config2 = oauth_config.copy()
        config2["client_secret"] = "concurrent_secret_2"

        await manager.store_secrets(provider_id, config1)
        await async_session.commit()

        await manager.store_secrets(provider_id, config2)
        await async_session.commit()

        # Last write should win
        decrypted = await manager.retrieve_secret(provider_id, "client_secret")
        assert decrypted == "concurrent_secret_2"

    @pytest.mark.asyncio
    async def test_unicode_secrets_handled_correctly(self, async_session, provider_id):
        """Test that Unicode characters in secrets are preserved."""
        manager = SSOSecretsManager(async_session)

        # Config with Unicode secret
        config = {
            "client_id": "test_123",
            "client_secret": "密碼secret🔐test",
            "authorize_url": "https://example.com",
        }

        await manager.store_secrets(provider_id, config)
        await async_session.commit()

        # Verify Unicode preserved after encryption/decryption
        decrypted = await manager.retrieve_secret(provider_id, "client_secret")
        assert decrypted == "密碼secret🔐test"

    @pytest.mark.asyncio
    async def test_very_long_secret_values(self, async_session, provider_id):
        """Test handling of very long secret values (e.g., long API keys)."""
        manager = SSOSecretsManager(async_session)

        # Generate a 2KB secret
        long_secret = "x" * 2048
        config = {
            "client_id": "test_123",
            "client_secret": long_secret,
            "authorize_url": "https://example.com",
        }

        await manager.store_secrets(provider_id, config)
        await async_session.commit()

        # Verify long secret preserved
        decrypted = await manager.retrieve_secret(provider_id, "client_secret")
        assert decrypted == long_secret
        assert len(decrypted) == 2048
