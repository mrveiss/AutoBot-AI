#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Bedrock provider SecretsService integration.

Tests credential resolution, encryption, and audit trail for AWS Bedrock credentials.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from llm_shared.providers.bedrock import BedrockProvider
from services.secrets_service import SecretsService


class BedrockSecretsIntegrationTest(unittest.TestCase):
    """Test Bedrock provider integration with SecretsService."""

    def setUp(self):
        """Set up test fixtures with temporary database."""
        # Create temporary database for SecretsService
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_secrets.db")

        # Initialize SecretsService with test database
        self.secrets_service = SecretsService(db_path=self.db_path)

        # Clear environment variables for clean test state
        self.original_env = {}
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"]:
            self.original_env[key] = os.environ.pop(key, None)

    def tearDown(self):
        """Clean up test fixtures."""
        # Restore original environment
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]

        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_credentials_from_secrets_service(self):
        """Test that credentials are loaded from SecretsService when available."""
        # Store test credentials in SecretsService
        test_creds = {
            "aws_access_key_id": "AKIATEST12345",
            "aws_secret_access_key": "test_secret_key_12345",
            "region": "us-west-2",
        }

        self.secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test",
        )

        # Mock get_secrets_service to return our test instance
        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            access_key, secret_key, region = provider._resolve_credentials()

            self.assertEqual(access_key, "AKIATEST12345")
            self.assertEqual(secret_key, "test_secret_key_12345")
            self.assertEqual(region, "us-west-2")

    def test_credentials_encrypted_in_storage(self):
        """Test that credentials are stored encrypted, not plain text."""
        # Store credentials
        test_creds = {
            "aws_access_key_id": "AKIATEST12345",
            "aws_secret_access_key": "test_secret_key_12345",
            "region": "us-west-2",
        }

        self.secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test",
        )

        # Read directly from database to verify encryption
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT encrypted_value FROM secrets WHERE name = 'bedrock_aws_credentials'")
        row = cursor.fetchone()
        conn.close()

        encrypted_value = row[0]

        # Verify the encrypted value does NOT contain plain text credentials
        self.assertNotIn("AKIATEST12345", encrypted_value)
        self.assertNotIn("test_secret_key_12345", encrypted_value)

        # Verify the encrypted value can be decrypted back to original
        decrypted = self.secrets_service._decrypt_value(encrypted_value)
        decrypted_creds = json.loads(decrypted)
        self.assertEqual(decrypted_creds, test_creds)

    def test_fallback_to_environment_variables(self):
        """Test fallback to environment variables when SecretsService has no credentials."""
        # Set environment variables
        os.environ["AWS_ACCESS_KEY_ID"] = "AKIAENV12345"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "env_secret_key"
        os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"

        # Mock get_secrets_service to return our test instance (empty)
        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            access_key, secret_key, region = provider._resolve_credentials()

            self.assertEqual(access_key, "AKIAENV12345")
            self.assertEqual(secret_key, "env_secret_key")
            self.assertEqual(region, "eu-west-1")

    def test_secrets_service_priority_over_env(self):
        """Test that SecretsService credentials take priority over environment variables."""
        # Set environment variables
        os.environ["AWS_ACCESS_KEY_ID"] = "AKIAENV12345"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "env_secret_key"

        # Store different credentials in SecretsService
        test_creds = {
            "aws_access_key_id": "AKIASECURE99999",
            "aws_secret_access_key": "secure_secret_key",
            "region": "ap-southeast-1",
        }

        self.secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test",
        )

        # Mock get_secrets_service
        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            access_key, secret_key, region = provider._resolve_credentials()

            # Should use SecretsService credentials, not env vars
            self.assertEqual(access_key, "AKIASECURE99999")
            self.assertEqual(secret_key, "secure_secret_key")
            self.assertEqual(region, "ap-southeast-1")

    def test_audit_trail_on_credential_access(self):
        """Test that credential access is logged in audit trail."""
        # Store credentials
        test_creds = {
            "aws_access_key_id": "AKIATEST12345",
            "aws_secret_access_key": "test_secret_key",
            "region": "us-east-1",
        }

        secret = self.secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test_user",
        )

        # Access credentials (should create audit entry)
        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            provider._resolve_credentials()

        # Check audit log
        audit_log = self.secrets_service.get_audit_log(secret_id=secret["id"])

        # Should have at least 2 entries: created + accessed
        self.assertGreaterEqual(len(audit_log), 2)

        # Find the "accessed" entry
        accessed_entries = [e for e in audit_log if e["action"] == "accessed"]
        self.assertGreater(len(accessed_entries), 0)

        # Verify the accessed entry has correct metadata
        accessed_entry = accessed_entries[0]
        self.assertEqual(accessed_entry["performed_by"], "bedrock_provider")

    def test_no_plain_text_credentials_in_settings(self):
        """Test that credentials cannot be passed via settings dict (security requirement)."""
        # This test verifies that the old insecure path is removed
        # Settings dict should not be used for credentials

        # Create provider with settings containing credentials (should be ignored)
        provider = BedrockProvider(
            settings={
                "aws_access_key_id": "SHOULD_BE_IGNORED",
                "aws_secret_access_key": "SHOULD_BE_IGNORED",
            }
        )

        # Set env vars to a different value
        os.environ["AWS_ACCESS_KEY_ID"] = "AKIAENV12345"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "env_secret"

        # Mock get_secrets_service to return empty secrets
        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            access_key, secret_key, region = provider._resolve_credentials()

            # Should use env vars, NOT settings (since settings path is removed)
            self.assertEqual(access_key, "AKIAENV12345")
            self.assertEqual(secret_key, "env_secret")

    def test_region_fallback_chain(self):
        """Test region resolution fallback chain."""
        # Test 1: Region from SecretsService
        test_creds_with_region = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "test_secret",
            "region": "ap-northeast-1",
        }

        self.secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds_with_region),
            scope="general",
        )

        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            _, _, region = provider._resolve_credentials()
            self.assertEqual(region, "ap-northeast-1")

        # Clean up for next test
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_secrets.db")
        self.secrets_service = SecretsService(db_path=self.db_path)

        # Test 2: Region from environment when not in SecretsService
        os.environ["AWS_DEFAULT_REGION"] = "eu-central-1"

        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            _, _, region = provider._resolve_credentials()
            self.assertEqual(region, "eu-central-1")

        # Test 3: Default region when nothing is set
        del os.environ["AWS_DEFAULT_REGION"]

        with patch("llm_shared.providers.bedrock.get_secrets_service", return_value=self.secrets_service):
            provider = BedrockProvider()
            _, _, region = provider._resolve_credentials()
            self.assertEqual(region, "us-east-1")  # Default


if __name__ == "__main__":
    unittest.main()
