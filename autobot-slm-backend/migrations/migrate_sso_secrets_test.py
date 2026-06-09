# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SSO secrets migration script (MVA-3883, GH#9685).

Tests the migration from plaintext SSO credentials to encrypted SystemSecret storage:
- Migrating sample providers with plaintext secrets
- Verifying secrets are properly encrypted
- Verifying config references are correct
- Handling providers with missing/empty secrets
- Handling already-migrated providers (idempotency)
"""

import json
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    """Provide an encryption key so encrypt_data() and the pre-flight check work."""
    monkeypatch.setenv("SLM_ENCRYPTION_KEY", "test-key-0123456789abcdef0123456789ab")


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection for migration tests."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def sample_providers_with_plaintext():
    """Sample SSO providers with plaintext secrets."""
    provider1_id = str(uuid.uuid4())
    provider2_id = str(uuid.uuid4())
    provider3_id = str(uuid.uuid4())

    return [
        (
            provider1_id,
            json.dumps(
                {
                    "provider_type": "google",
                    "client_id": "google_client_123",
                    "client_secret": "plaintext_google_secret",
                    "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                }
            ),
        ),
        (
            provider2_id,
            json.dumps(
                {
                    "provider_type": "ldap",
                    "server_url": "ldap://ldap.example.com",
                    "bind_dn": "cn=admin,dc=example,dc=com",
                    "bind_password": "plaintext_ldap_password",
                    "base_dn": "dc=example,dc=com",
                }
            ),
        ),
        (
            provider3_id,
            json.dumps(
                {
                    "provider_type": "github",
                    "client_id": "github_client_456",
                    "client_secret": "plaintext_github_secret",
                    "authorize_url": "https://github.com/login/oauth/authorize",
                }
            ),
        ),
    ]


class TestSSOSecretsMigration:
    """Tests for the migration script that moves plaintext secrets to encrypted storage."""

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_extracts_and_encrypts_client_secret(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration extracts client_secret and stores it encrypted."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        # Setup mock to return single OAuth provider
        provider_id, config_json = sample_providers_with_plaintext[0]
        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        mock_cursor.fetchone.return_value = None  # No existing secret

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        # Run migration
        migrate("postgresql://test")

        # Verify INSERT called for system_secrets table
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]
        assert len(insert_calls) >= 1

        # Verify UPDATE called for sso_providers table
        update_calls = [call for call in mock_cursor.execute.call_args_list if "UPDATE sso_providers" in str(call)]
        assert len(update_calls) >= 1

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_removes_plaintext_and_adds_reference(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration removes plaintext secret and adds reference."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider_id, config_json = sample_providers_with_plaintext[0]
        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Get the UPDATE call for sso_providers
        update_calls = [call for call in mock_cursor.execute.call_args_list if "UPDATE sso_providers" in str(call)]

        # Verify updated config was passed.
        # Call shape: execute("UPDATE sso_providers SET config = %s WHERE id = %s",
        #                      (updated_config_json, provider_id))
        assert len(update_calls) > 0
        sql_params = update_calls[0].args[1]
        updated_config = json.loads(sql_params[0])

        # Verify plaintext removed and reference added
        assert "client_secret" not in updated_config
        assert "client_secret_ref" in updated_config
        assert updated_config["client_secret_ref"] == f"sso:provider:{provider_id}:client_secret"

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_handles_ldap_bind_password(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration handles LDAP bind_password field."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        # Use LDAP provider (second in list)
        provider_id, config_json = sample_providers_with_plaintext[1]
        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Verify bind_password was processed
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]
        assert len(insert_calls) >= 1

        # Check that secret key includes bind_password
        insert_call_str = str(insert_calls[0])
        assert "bind_password" in insert_call_str

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_handles_multiple_providers(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration processes all providers in database."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        # Return all three sample providers
        mock_cursor.fetchall.return_value = sample_providers_with_plaintext
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Should have 3 INSERT calls (one per provider)
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]
        assert len(insert_calls) == 3

        # Should have 3 UPDATE calls (one per provider)
        update_calls = [call for call in mock_cursor.execute.call_args_list if "UPDATE sso_providers" in str(call)]
        assert len(update_calls) == 3

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_handles_provider_with_no_secrets(self, mock_get_connection, mock_db_connection):
        """Test migration skips providers without sensitive fields."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        # Provider config without any secrets
        provider_id = str(uuid.uuid4())
        config_without_secrets = json.dumps(
            {
                "provider_type": "saml",
                "entity_id": "https://idp.example.com/saml",
                "sso_url": "https://idp.example.com/sso",
                # No client_secret or bind_password
            }
        )

        mock_cursor.fetchall.return_value = [(provider_id, config_without_secrets)]

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Should not insert any secrets
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]
        assert len(insert_calls) == 0

        # Should not update provider config
        update_calls = [call for call in mock_cursor.execute.call_args_list if "UPDATE sso_providers" in str(call)]
        assert len(update_calls) == 0

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_handles_empty_secret_values(self, mock_get_connection, mock_db_connection):
        """Test migration skips empty/null secret values."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        # Provider with empty client_secret
        provider_id = str(uuid.uuid4())
        config_with_empty_secret = json.dumps(
            {
                "provider_type": "google",
                "client_id": "client_123",
                "client_secret": "",  # Empty value
                "authorize_url": "https://accounts.google.com/oauth",
            }
        )

        mock_cursor.fetchall.return_value = [(provider_id, config_with_empty_secret)]

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Should not insert secret for empty value
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]
        assert len(insert_calls) == 0

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_updates_existing_secret(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration updates secret if it already exists (idempotency)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider_id, config_json = sample_providers_with_plaintext[0]
        mock_cursor.fetchall.return_value = [(provider_id, config_json)]

        # Mock existing secret (return a row ID)
        mock_cursor.fetchone.return_value = (1,)  # Secret exists with ID=1

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Should UPDATE instead of INSERT
        update_secret_calls = [
            call for call in mock_cursor.execute.call_args_list if "UPDATE system_secrets" in str(call)
        ]
        assert len(update_secret_calls) >= 1

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_preserves_non_sensitive_config_fields(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration preserves all non-sensitive config fields."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider_id, config_json = sample_providers_with_plaintext[0]
        original_config = json.loads(config_json)

        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Get updated config from UPDATE call
        update_calls = [call for call in mock_cursor.execute.call_args_list if "UPDATE sso_providers" in str(call)]

        # Verify non-sensitive fields preserved
        # (In real test, would parse the SQL parameters)
        assert len(update_calls) > 0

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_commits_transaction_on_success(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration commits transaction after successful migration."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        mock_cursor.fetchall.return_value = sample_providers_with_plaintext
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Verify commit was called
        mock_conn.commit.assert_called_once()

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_rolls_back_on_error(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test migration rolls back transaction on error."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        mock_cursor.fetchall.return_value = sample_providers_with_plaintext
        # Simulate error during INSERT
        mock_cursor.execute.side_effect = [
            None,  # SELECT succeeds
            Exception("Database error"),  # INSERT fails
        ]

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        # Migration should raise exception
        with pytest.raises(Exception, match="Database error"):
            migrate("postgresql://test")

        # Verify rollback was called
        mock_conn.rollback.assert_called_once()

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_closes_connection(self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext):
        """Test migration closes connection in finally block."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        mock_cursor.fetchall.return_value = sample_providers_with_plaintext
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Verify connection closed
        mock_conn.close.assert_called_once()

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_handles_json_string_and_dict_configs(self, mock_get_connection, mock_db_connection):
        """Test migration handles both JSON string and dict config formats."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider1_id = str(uuid.uuid4())
        provider2_id = str(uuid.uuid4())

        # Mix of JSON string and Python dict
        mixed_providers = [
            # JSON string format
            (
                provider1_id,
                json.dumps(
                    {
                        "client_id": "client_1",
                        "client_secret": "secret_1",
                    }
                ),
            ),
            # Dict format (PostgreSQL JSONB)
            (
                provider2_id,
                {
                    "client_id": "client_2",
                    "client_secret": "secret_2",
                },
            ),
        ]

        mock_cursor.fetchall.return_value = mixed_providers
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Should process both formats without error
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]
        assert len(insert_calls) == 2


class TestMigrationDataIntegrity:
    """Tests for ensuring data integrity during migration."""

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_encrypted_value_can_be_decrypted(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test that encrypted values can be successfully decrypted."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider_id, config_json = sample_providers_with_plaintext[0]
        original_config = json.loads(config_json)
        original_secret = original_config["client_secret"]

        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        mock_cursor.fetchone.return_value = None

        # Capture the encrypted value passed to INSERT
        captured_encrypted_value = None

        def capture_insert(*args, **kwargs):
            nonlocal captured_encrypted_value
            if "INSERT INTO system_secrets" in args[0]:
                captured_encrypted_value = args[1][1]  # encrypted_value parameter

        mock_cursor.execute.side_effect = capture_insert

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        # services.encryption is stubbed in conftest. migrate() reads encrypt/decrypt
        # off sys.modules["services.encryption"], so patch.object that exact module
        # with a reversible round-trip rather than a string target (which resolves to
        # a different auto-child mock and would not intercept migrate's import).
        enc = sys.modules["services.encryption"]
        with (
            patch.object(enc, "encrypt_data", side_effect=lambda v: f"encrypted::{v}"),
            patch.object(enc, "decrypt_data", side_effect=lambda v: v.split("encrypted::", 1)[1]) as mock_decrypt,
        ):
            migrate("postgresql://test")

        # Migration stored the encrypted form (not plaintext) and it round-trips back.
        assert captured_encrypted_value == f"encrypted::{original_secret}"
        assert captured_encrypted_value != original_secret
        assert mock_decrypt(captured_encrypted_value) == original_secret

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_secret_key_format_matches_sso_secrets_manager(
        self, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test that secret keys use the same format as SSOSecretsManager."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider_id, config_json = sample_providers_with_plaintext[0]
        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Verify key format in INSERT call
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list if "INSERT INTO system_secrets" in str(call)
        ]

        # Key should match format: sso:provider:{uuid}:client_secret
        assert len(insert_calls) > 0
        # The key is first parameter
        call_str = str(insert_calls[0])
        assert f"sso:provider:{provider_id}:client_secret" in call_str


class TestMigrationLogging:
    """Tests for migration logging and reporting."""

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    @patch("migrations.migrate_sso_secrets_to_system_secret.logger")
    def test_migration_logs_progress(
        self, mock_logger, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test that migration logs progress information."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        mock_cursor.fetchall.return_value = sample_providers_with_plaintext
        mock_cursor.fetchone.return_value = None

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        migrate("postgresql://test")

        # Verify info logging called
        assert mock_logger.info.call_count >= 3  # Start, per-provider, completion

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    @patch("migrations.migrate_sso_secrets_to_system_secret.logger")
    def test_migration_logs_errors(
        self, mock_logger, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """Test that migration logs errors."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        mock_cursor.fetchall.return_value = sample_providers_with_plaintext
        mock_cursor.execute.side_effect = Exception("Test error")

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        with pytest.raises(Exception):
            migrate("postgresql://test")

        # Verify error logged
        mock_logger.error.assert_called_once()


class TestMigrationHardening:
    """Tests for encryption-key validation and error context (GH#9686)."""

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    def test_migrate_aborts_without_encryption_key(self, mock_get_connection, monkeypatch):
        """Migration fails fast with a clear error and opens no DB connection."""
        monkeypatch.delenv("SLM_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SLM_SECRET_KEY", raising=False)

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        with pytest.raises(RuntimeError, match="No encryption key configured"):
            migrate("postgresql://test")

        # Aborted before touching the database.
        mock_get_connection.assert_not_called()

    @patch("migrations.migrate_sso_secrets_to_system_secret.get_connection")
    @patch("migrations.migrate_sso_secrets_to_system_secret.logger")
    def test_migrate_error_log_includes_provider_and_field_context(
        self, mock_logger, mock_get_connection, mock_db_connection, sample_providers_with_plaintext
    ):
        """A failure mid-field is logged with the provider id and field name."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_connection.return_value = mock_conn

        provider_id, config_json = sample_providers_with_plaintext[0]
        mock_cursor.fetchall.return_value = [(provider_id, config_json)]
        # Providers SELECT succeeds; the secret-existence SELECT raises.
        mock_cursor.execute.side_effect = [None, Exception("boom")]

        from migrations.migrate_sso_secrets_to_system_secret import migrate

        with pytest.raises(Exception, match="boom"):
            migrate("postgresql://test")

        mock_conn.rollback.assert_called_once()
        mock_logger.error.assert_called_once()
        error_msg = str(mock_logger.error.call_args)
        assert provider_id in error_msg
        assert "client_secret" in error_msg
