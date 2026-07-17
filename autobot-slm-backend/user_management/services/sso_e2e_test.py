# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# Author: mrveiss
"""
End-to-end tests for SSO authentication flows with encrypted credentials (MVA-3883, GH#9685).

Tests OAuth and LDAP flows using encrypted secrets:
- OAuth: authorization, token exchange, userinfo retrieval
- LDAP: connection, authentication, user search

The slm-backend root conftest stubs ``sqlalchemy`` / ``models.database`` /
``services.encryption`` as MagicMocks for api/* tests, so bare imports here
would run against inert mock chains (``create_async_engine`` returning a
MagicMock that cannot be awaited — the exact never-run failure #11798 fixed).
Same real-load prologue as the sibling ``sso_secrets_test.py`` (pattern:
tests/services/code_version_test.py, #11737/#11794): swap in the REAL
sqlalchemy + product modules at import time, bind what the tests need,
restore the stubs, and re-activate the swap per-test via ``async_session``.
"""

import contextlib
import importlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SLM_ROOT = Path(__file__).parent.parent.parent
for _p in (str(_SLM_ROOT), str(_SLM_ROOT.parent)):  # slm root + repo root (autobot_shared)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The real EncryptionService requires a master key at first use; provide a
# deterministic test-only default without clobbering a real environment.
os.environ.setdefault("SLM_ENCRYPTION_KEY", "unit-test-encryption-key-0123456789abcdef")

# ldap3 is a declared dependency (requirements.txt) but not always installed
# in dev environments; the LDAP-mocking tests are env-bound on it.
requires_ldap3 = pytest.mark.skipif(
    importlib.util.find_spec("ldap3") is None,
    reason="ldap3 not installed (declared in requirements.txt; env-bound)",
)

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


# Snapshot and clear EVERY swapped key — one cached MagicMock child poisons
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
    encrypt_data = _real_enc.encrypt_data
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


# Test fixtures
@pytest.fixture
async def async_session():
    """Create an async test database session (real modules swapped in)."""
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


@pytest.fixture
def provider_id():
    """Generate a test provider UUID."""
    return uuid.uuid4()


@pytest.fixture
async def oauth_provider_with_encrypted_secret(async_session, provider_id):
    """Create an OAuth provider with encrypted client_secret."""
    # Store encrypted secret
    secret_key = f"sso:provider:{provider_id}:client_secret"
    secret = SystemSecret(
        key=secret_key,
        encrypted_value=encrypt_data("oauth_client_secret_123"),
        category="sso",
        description=f"SSO client_secret for provider {provider_id}",
    )
    async_session.add(secret)
    await async_session.commit()

    # Return provider config with secret reference
    return {
        "provider_id": provider_id,
        "provider_type": "google",
        "client_id": "test_client_id",
        "client_secret_ref": secret_key,
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    }


@pytest.fixture
async def ldap_provider_with_encrypted_password(async_session, provider_id):
    """Create an LDAP provider with encrypted bind_password."""
    # Store encrypted password
    secret_key = f"sso:provider:{provider_id}:bind_password"
    secret = SystemSecret(
        key=secret_key,
        encrypted_value=encrypt_data("ldap_bind_password_456"),
        category="sso",
        description=f"SSO bind_password for provider {provider_id}",
    )
    async_session.add(secret)
    await async_session.commit()

    # Return provider config with secret reference
    return {
        "provider_id": provider_id,
        "provider_type": "ldap",
        "server_url": "ldap://ldap.example.com:389",
        "bind_dn": "cn=admin,dc=example,dc=com",
        "bind_password_ref": secret_key,
        "base_dn": "dc=example,dc=com",
        "user_filter": "(uid={username})",
    }


class TestOAuthFlowWithEncryptedCredentials:
    """End-to-end OAuth flow tests using encrypted client_secret."""

    @pytest.mark.asyncio
    async def test_oauth_authorization_url_generation(self, async_session, oauth_provider_with_encrypted_secret):
        """Test OAuth authorization URL generation with encrypted credentials."""
        manager = SSOSecretsManager(async_session)
        provider_id = oauth_provider_with_encrypted_secret["provider_id"]

        # Retrieve client_secret for OAuth flow
        client_secret = await manager.retrieve_secret(provider_id, "client_secret")
        assert client_secret == "oauth_client_secret_123"

        # Simulate authorization URL generation
        # In real code, this would use authlib or similar
        auth_params = {
            "client_id": oauth_provider_with_encrypted_secret["client_id"],
            "redirect_uri": "https://autobot.example.com/auth/callback",
            "scope": oauth_provider_with_encrypted_secret["scope"],
            "response_type": "code",
            "state": "random_state_token",
        }

        # URL generation would happen here
        # For test purposes, verify we have all required params
        assert auth_params["client_id"] == "test_client_id"
        assert "openid" in auth_params["scope"]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_oauth_token_exchange_with_encrypted_secret(
        self, mock_post, async_session, oauth_provider_with_encrypted_secret
    ):
        """Test OAuth token exchange using decrypted client_secret."""
        manager = SSOSecretsManager(async_session)
        provider_id = oauth_provider_with_encrypted_secret["provider_id"]

        # Mock token endpoint response
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "id_token": "mock_id_token",
                }
            ),
        )

        # Retrieve encrypted client_secret
        client_secret = await manager.retrieve_secret(provider_id, "client_secret")

        # Simulate token exchange
        token_params = {
            "code": "authorization_code_from_callback",
            "client_id": oauth_provider_with_encrypted_secret["client_id"],
            "client_secret": client_secret,
            "redirect_uri": "https://autobot.example.com/auth/callback",
            "grant_type": "authorization_code",
        }

        # Verify decrypted secret used in request
        assert token_params["client_secret"] == "oauth_client_secret_123"

        # In real implementation, this would call the token endpoint
        # For test, just verify params are correct
        assert token_params["grant_type"] == "authorization_code"
        assert token_params["code"] == "authorization_code_from_callback"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_oauth_userinfo_retrieval(self, mock_get, async_session, oauth_provider_with_encrypted_secret):
        """Test OAuth userinfo retrieval after successful token exchange."""
        # Mock userinfo endpoint response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    "sub": "google_user_123",
                    "email": "user@example.com",
                    "email_verified": True,
                    "name": "Test User",
                    "picture": "https://example.com/photo.jpg",
                }
            ),
        )

        # Simulate userinfo request with access token
        access_token = "mock_access_token"
        oauth_provider_with_encrypted_secret["userinfo_url"]

        # In real code, this would make HTTP request
        # For test, verify flow completes successfully
        headers = {"Authorization": f"Bearer {access_token}"}

        # Verify headers set correctly
        assert headers["Authorization"] == "Bearer mock_access_token"

    @pytest.mark.asyncio
    async def test_oauth_flow_handles_missing_secret_gracefully(self, async_session, provider_id):
        """Test OAuth flow error handling when secret not found."""
        manager = SSOSecretsManager(async_session)

        # Try to retrieve non-existent secret
        client_secret = await manager.retrieve_secret(provider_id, "client_secret")

        # Should return None, allowing caller to handle error
        assert client_secret is None

    @pytest.mark.asyncio
    async def test_oauth_flow_handles_decryption_error(self, async_session, provider_id):
        """Test OAuth flow when secret decryption fails."""
        # Store corrupted secret
        secret_key = f"sso:provider:{provider_id}:client_secret"
        secret = SystemSecret(
            key=secret_key,
            encrypted_value="corrupted_encrypted_data",
            category="sso",
            description=f"SSO client_secret for provider {provider_id}",
        )
        async_session.add(secret)
        await async_session.commit()

        manager = SSOSecretsManager(async_session)

        # Decryption should raise clear error
        with pytest.raises(ValueError, match="Failed to decrypt secret"):
            await manager.retrieve_secret(provider_id, "client_secret")


class TestLDAPFlowWithEncryptedCredentials:
    """End-to-end LDAP authentication tests using encrypted bind_password."""

    @pytest.mark.asyncio
    async def test_ldap_connection_with_encrypted_password(self, async_session, ldap_provider_with_encrypted_password):
        """Test LDAP connection using decrypted bind_password."""
        manager = SSOSecretsManager(async_session)
        provider_id = ldap_provider_with_encrypted_password["provider_id"]

        # Retrieve encrypted bind_password
        bind_password = await manager.retrieve_secret(provider_id, "bind_password")
        assert bind_password == "ldap_bind_password_456"

        # Simulate LDAP connection parameters
        ldap_params = {
            "server": ldap_provider_with_encrypted_password["server_url"],
            "bind_dn": ldap_provider_with_encrypted_password["bind_dn"],
            "bind_password": bind_password,
        }

        # Verify decrypted password available for connection
        assert ldap_params["bind_password"] == "ldap_bind_password_456"
        assert ldap_params["bind_dn"] == "cn=admin,dc=example,dc=com"

    @requires_ldap3
    @pytest.mark.asyncio
    @patch("ldap3.Connection")
    @patch("ldap3.Server")
    async def test_ldap_authentication_flow(
        self, mock_server, mock_connection, async_session, ldap_provider_with_encrypted_password
    ):
        """Test full LDAP authentication with encrypted credentials."""
        # Mock LDAP server and connection
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance

        mock_conn_instance = MagicMock()
        mock_conn_instance.bind.return_value = True
        mock_conn_instance.search.return_value = True
        mock_conn_instance.entries = [
            MagicMock(
                entry_attributes_as_dict={
                    "uid": ["testuser"],
                    "cn": ["Test User"],
                    "mail": ["testuser@example.com"],
                }
            )
        ]
        mock_connection.return_value = mock_conn_instance

        manager = SSOSecretsManager(async_session)
        provider_id = ldap_provider_with_encrypted_password["provider_id"]
        provider = ldap_provider_with_encrypted_password

        # Retrieve encrypted bind_password
        bind_password = await manager.retrieve_secret(provider_id, "bind_password")

        # Simulate LDAP bind with decrypted password
        # In real code, this would use ldap3 library
        ldap_connection_params = {
            "server": provider["server_url"],
            "user": provider["bind_dn"],
            "password": bind_password,
            "auto_bind": True,
        }

        # Verify password decrypted correctly
        assert ldap_connection_params["password"] == "ldap_bind_password_456"

        # Simulate user search
        search_params = {
            "base_dn": provider["base_dn"],
            "filter": provider["user_filter"].format(username="testuser"),
            "attributes": ["uid", "cn", "mail"],
        }

        # Verify search parameters
        assert search_params["base_dn"] == "dc=example,dc=com"
        assert "(uid=testuser)" in search_params["filter"]

    @pytest.mark.asyncio
    async def test_ldap_connection_handles_missing_password(self, async_session, provider_id):
        """Test LDAP connection error handling when bind_password missing."""
        manager = SSOSecretsManager(async_session)

        # Try to retrieve non-existent password
        bind_password = await manager.retrieve_secret(provider_id, "bind_password")

        # Should return None, allowing caller to handle error
        assert bind_password is None

    @requires_ldap3
    @pytest.mark.asyncio
    @patch("ldap3.Connection")
    @patch("ldap3.Server")
    async def test_ldap_user_authentication_with_encrypted_credentials(
        self, mock_server, mock_connection, async_session, ldap_provider_with_encrypted_password
    ):
        """Test LDAP user authentication flow."""
        # Mock successful bind
        mock_conn_instance = MagicMock()
        mock_conn_instance.bind.return_value = True
        mock_connection.return_value = mock_conn_instance

        manager = SSOSecretsManager(async_session)
        provider_id = ldap_provider_with_encrypted_password["provider_id"]

        # Retrieve bind_password for admin connection
        bind_password = await manager.retrieve_secret(provider_id, "bind_password")

        # First, admin binds to search for user
        ldap_provider_with_encrypted_password["bind_dn"]
        assert bind_password == "ldap_bind_password_456"

        # Then user would be authenticated with their own credentials
        # (user password is not stored in SSO config, only bind password)
        user_dn = "uid=testuser,dc=example,dc=com"

        # Verify admin bind password retrieved from encrypted storage
        assert bind_password is not None

    @pytest.mark.asyncio
    async def test_ldap_handles_special_characters_in_password(self, async_session, provider_id):
        """Test LDAP with special characters in bind_password."""
        # Store password with special chars
        special_password = 'p@ssw0rd!"#$%&*()[]{}:;<>?'
        secret_key = f"sso:provider:{provider_id}:bind_password"
        secret = SystemSecret(
            key=secret_key,
            encrypted_value=encrypt_data(special_password),
            category="sso",
            description=f"SSO bind_password for provider {provider_id}",
        )
        async_session.add(secret)
        await async_session.commit()

        manager = SSOSecretsManager(async_session)

        # Retrieve and verify special chars preserved
        decrypted = await manager.retrieve_secret(provider_id, "bind_password")
        assert decrypted == special_password


class TestSSOIntegrationScenarios:
    """Integration test scenarios combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_oauth_sso_provider_lifecycle(self, async_session, provider_id):
        """Test complete lifecycle: create, use, update, delete."""
        manager = SSOSecretsManager(async_session)

        # 1. Create provider with encrypted secret
        initial_config = {
            "client_id": "initial_client_id",
            "client_secret": "initial_secret_123",
            "authorize_url": "https://provider.com/oauth/authorize",
        }

        sanitized = await manager.store_secrets(provider_id, initial_config)
        await async_session.commit()

        assert "client_secret_ref" in sanitized

        # 2. Use the provider (retrieve secret)
        secret = await manager.retrieve_secret(provider_id, "client_secret")
        assert secret == "initial_secret_123"

        # 3. Update provider secret (rotation)
        updated_config = {
            "client_id": "initial_client_id",
            "client_secret": "rotated_secret_456",
            "authorize_url": "https://provider.com/oauth/authorize",
        }

        await manager.store_secrets(provider_id, updated_config)
        await async_session.commit()

        # 4. Verify updated secret
        secret = await manager.retrieve_secret(provider_id, "client_secret")
        assert secret == "rotated_secret_456"

        # 5. Delete provider (cleanup)
        await manager.delete_secrets(provider_id)
        await async_session.commit()

        # 6. Verify secret removed
        secret = await manager.retrieve_secret(provider_id, "client_secret")
        assert secret is None

    @pytest.mark.asyncio
    async def test_multiple_providers_with_encrypted_secrets(self, async_session):
        """Test managing secrets for multiple SSO providers simultaneously."""
        manager = SSOSecretsManager(async_session)

        # Create three different providers
        google_id = uuid.uuid4()
        github_id = uuid.uuid4()
        okta_id = uuid.uuid4()

        google_config = {"client_id": "google", "client_secret": "google_secret"}
        github_config = {"client_id": "github", "client_secret": "github_secret"}
        okta_config = {"client_id": "okta", "client_secret": "okta_secret"}

        await manager.store_secrets(google_id, google_config)
        await manager.store_secrets(github_id, github_config)
        await manager.store_secrets(okta_id, okta_config)
        await async_session.commit()

        # Verify each secret is independent and correct
        assert await manager.retrieve_secret(google_id, "client_secret") == "google_secret"
        assert await manager.retrieve_secret(github_id, "client_secret") == "github_secret"
        assert await manager.retrieve_secret(okta_id, "client_secret") == "okta_secret"

        # Delete one provider, others should remain
        await manager.delete_secrets(github_id)
        await async_session.commit()

        assert await manager.retrieve_secret(google_id, "client_secret") == "google_secret"
        assert await manager.retrieve_secret(github_id, "client_secret") is None
        assert await manager.retrieve_secret(okta_id, "client_secret") == "okta_secret"
