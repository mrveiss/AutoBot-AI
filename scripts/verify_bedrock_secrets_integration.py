#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Standalone verification script for Bedrock SecretsService integration.

Tests that the Bedrock provider correctly integrates with SecretsService
for encrypted credential storage and retrieval.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "autobot-backend"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_shared.providers.bedrock import BedrockProvider
from services.secrets_service import SecretsService


def test_credentials_from_secrets_service():
    """Test that credentials are loaded from SecretsService."""
    print("Test 1: Loading credentials from SecretsService...")

    # Create temporary database
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "test_secrets.db")
        secrets_service = SecretsService(db_path=db_path)

        # Store test credentials
        test_creds = {
            "aws_access_key_id": "AKIATEST12345",
            "aws_secret_access_key": "test_secret_key_12345",
            "region": "us-west-2",
        }

        secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test",
        )

        # Mock get_secrets_service to return our test instance
        # We need to mock the module as imported by bedrock.py
        import llm_shared.providers.bedrock as bedrock_module
        original_get_secrets_service = bedrock_module.secrets_service_module.get_secrets_service
        bedrock_module.secrets_service_module.get_secrets_service = lambda: secrets_service

        try:
            provider = BedrockProvider()
            access_key, secret_key, region = provider._resolve_credentials()

            assert access_key == "AKIATEST12345", f"Expected AKIATEST12345, got {access_key}"
            assert secret_key == "test_secret_key_12345", f"Expected test_secret_key_12345, got {secret_key}"
            assert region == "us-west-2", f"Expected us-west-2, got {region}"

            print("✓ Credentials loaded correctly from SecretsService")
        finally:
            bedrock_module.secrets_service_module.get_secrets_service = original_get_secrets_service


def test_credentials_encrypted_in_storage():
    """Test that credentials are stored encrypted, not plain text."""
    print("\nTest 2: Verifying credentials are encrypted in storage...")

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "test_secrets.db")
        secrets_service = SecretsService(db_path=db_path)

        # Store credentials
        test_creds = {
            "aws_access_key_id": "AKIATEST12345",
            "aws_secret_access_key": "test_secret_key_12345",
            "region": "us-west-2",
        }

        secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test",
        )

        # Read directly from database to verify encryption
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT encrypted_value FROM secrets WHERE name = 'bedrock_aws_credentials'"
        )
        row = cursor.fetchone()
        conn.close()

        encrypted_value = row[0]

        # Verify the encrypted value does NOT contain plain text
        assert "AKIATEST12345" not in encrypted_value, "Plain text access key found in encrypted storage!"
        assert "test_secret_key_12345" not in encrypted_value, "Plain text secret key found in encrypted storage!"

        # Verify can be decrypted
        decrypted = secrets_service._decrypt_value(encrypted_value)
        decrypted_creds = json.loads(decrypted)
        assert decrypted_creds == test_creds, "Decrypted credentials don't match original!"

        print("✓ Credentials are properly encrypted in storage")


def test_fallback_to_environment_variables():
    """Test fallback to environment variables when SecretsService is empty."""
    print("\nTest 3: Testing fallback to environment variables...")

    # Save original env vars
    original_env = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION"),
    }

    try:
        # Set test environment variables
        os.environ["AWS_ACCESS_KEY_ID"] = "AKIAENV12345"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "env_secret_key"
        os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "test_secrets.db")
            secrets_service = SecretsService(db_path=db_path)

            # Mock get_secrets_service
            import llm_shared.providers.bedrock as bedrock_module
            original_get_secrets_service = bedrock_module.secrets_service_module.get_secrets_service
            bedrock_module.secrets_service_module.get_secrets_service = lambda: secrets_service

            try:
                provider = BedrockProvider()
                access_key, secret_key, region = provider._resolve_credentials()

                assert access_key == "AKIAENV12345", f"Expected AKIAENV12345, got {access_key}"
                assert secret_key == "env_secret_key", f"Expected env_secret_key, got {secret_key}"
                assert region == "eu-west-1", f"Expected eu-west-1, got {region}"

                print("✓ Fallback to environment variables works correctly")
            finally:
                bedrock_module.secrets_service_module.get_secrets_service = original_get_secrets_service
    finally:
        # Restore original env vars
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]


def test_secrets_service_priority_over_env():
    """Test that SecretsService credentials take priority over environment."""
    print("\nTest 4: Testing SecretsService priority over environment variables...")

    original_env = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    }

    try:
        # Set environment variables
        os.environ["AWS_ACCESS_KEY_ID"] = "AKIAENV12345"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "env_secret_key"

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "test_secrets.db")
            secrets_service = SecretsService(db_path=db_path)

            # Store different credentials in SecretsService
            test_creds = {
                "aws_access_key_id": "AKIASECURE99999",
                "aws_secret_access_key": "secure_secret_key",
                "region": "ap-southeast-1",
            }

            secrets_service.create_secret(
                name="bedrock_aws_credentials",
                secret_type="aws_bedrock_credentials",
                value=json.dumps(test_creds),
                scope="general",
                created_by="test",
            )

            # Mock get_secrets_service
            import llm_shared.providers.bedrock as bedrock_module
            original_get_secrets_service = bedrock_module.secrets_service_module.get_secrets_service
            bedrock_module.secrets_service_module.get_secrets_service = lambda: secrets_service

            try:
                provider = BedrockProvider()
                access_key, secret_key, region = provider._resolve_credentials()

                # Should use SecretsService credentials, not env vars
                assert access_key == "AKIASECURE99999", f"Expected AKIASECURE99999, got {access_key}"
                assert secret_key == "secure_secret_key", f"Expected secure_secret_key, got {secret_key}"
                assert region == "ap-southeast-1", f"Expected ap-southeast-1, got {region}"

                print("✓ SecretsService takes priority over environment variables")
            finally:
                bedrock_module.secrets_service_module.get_secrets_service = original_get_secrets_service
    finally:
        # Restore original env vars
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]


def test_audit_trail():
    """Test that credential access is logged in audit trail."""
    print("\nTest 5: Testing audit trail for credential access...")

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = str(Path(temp_dir) / "test_secrets.db")
        secrets_service = SecretsService(db_path=db_path)

        # Store credentials
        test_creds = {
            "aws_access_key_id": "AKIATEST12345",
            "aws_secret_access_key": "test_secret_key",
            "region": "us-east-1",
        }

        secret = secrets_service.create_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            value=json.dumps(test_creds),
            scope="general",
            created_by="test_user",
        )

        # Mock get_secrets_service
        import llm_shared.providers.bedrock as bedrock_module
        original_get_secrets_service = bedrock_module.secrets_service_module.get_secrets_service
        bedrock_module.secrets_service_module.get_secrets_service = lambda: secrets_service

        try:
            # Access credentials (should create audit entry)
            provider = BedrockProvider()
            provider._resolve_credentials()

            # Check audit log
            audit_log = secrets_service.get_audit_log(secret_id=secret["id"])

            # Should have at least 2 entries: created + accessed
            assert len(audit_log) >= 2, f"Expected at least 2 audit entries, got {len(audit_log)}"

            # Find the "accessed" entry
            accessed_entries = [e for e in audit_log if e["action"] == "accessed"]
            assert len(accessed_entries) > 0, "No 'accessed' audit entry found"

            # Verify the accessed entry has correct metadata
            accessed_entry = accessed_entries[0]
            assert accessed_entry["performed_by"] == "bedrock_provider", \
                f"Expected performed_by='bedrock_provider', got {accessed_entry['performed_by']}"

            print("✓ Audit trail correctly records credential access")
        finally:
            bedrock_module.secrets_service_module.get_secrets_service = original_get_secrets_service


def main():
    """Run all verification tests."""
    print("="  * 70)
    print("Bedrock SecretsService Integration Verification")
    print("=" * 70)

    tests = [
        test_credentials_from_secrets_service,
        test_credentials_encrypted_in_storage,
        test_fallback_to_environment_variables,
        test_secrets_service_priority_over_env,
        test_audit_trail,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    if failed == 0:
        print("✓ All tests passed!")
        print("=" * 70)
        return 0
    else:
        print(f"✗ {failed}/{len(tests)} tests failed")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
