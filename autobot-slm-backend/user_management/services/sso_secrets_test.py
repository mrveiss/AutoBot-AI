# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Integration tests for SSO encrypted credential storage (MVA-3883, GH#9685).

Tests SSOSecretsManager for:
- Creating and encrypting SSO provider secrets
- Updating encrypted secrets
- Deleting provider secrets
- Migrating plaintext to encrypted storage
- Handling decryption failures gracefully
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, SystemSecret
from services.encryption import decrypt_data


# Test fixtures setup
@pytest.fixture
async def async_session():
    """Create an async test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

        manager = SSOSecretsManager(async_session)

        # Try to retrieve non-existent secret
        result = await manager.retrieve_secret(provider_id, "client_secret")
        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_secret_handles_decryption_failure(self, async_session, provider_id):
        """Test graceful handling of decryption failures."""
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

        manager = SSOSecretsManager(AsyncMock())

        # Config with plaintext secret
        assert await manager.has_plaintext_secrets(oauth_config) is True

        # Config without sensitive fields
        safe_config = {"client_id": "test_123", "authorize_url": "https://example.com"}
        assert await manager.has_plaintext_secrets(safe_config) is False

    @pytest.mark.asyncio
    async def test_migrate_plaintext_to_secrets_converts_successfully(self, async_session, provider_id, oauth_config):
        """Test migration from plaintext to encrypted storage."""
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
        from user_management.services.sso_secrets import SSOSecretsManager

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
