#!/usr/bin/env python3
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "autobot-backend"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.secrets_service import SecretsService

# Create temp database
with tempfile.TemporaryDirectory() as temp_dir:
    db_path = str(Path(temp_dir) / "test_secrets.db")
    secrets_service = SecretsService(db_path=db_path)

    # Store credentials
    test_creds = {
        "aws_access_key_id": "AKIATEST12345",
        "aws_secret_access_key": "test_secret_key",
        "region": "us-west-2",
    }

    secrets_service.create_secret(
        name="bedrock_aws_credentials",
        secret_type="aws_bedrock_credentials",
        value=json.dumps(test_creds),
        scope="general",
        created_by="test",
    )

    # Import bedrock module
    from llm_shared.providers.bedrock import BedrockProvider
    import llm_shared.providers.bedrock as bedrock_module

    print("Before monkeypatch:")
    print(f"  bedrock_module.secrets_service_module = {bedrock_module.secrets_service_module}")
    print(f"  bedrock_module.secrets_service_module.get_secrets_service = {bedrock_module.secrets_service_module.get_secrets_service}")

    # Monkeypatch
    original = bedrock_module.secrets_service_module.get_secrets_service
    bedrock_module.secrets_service_module.get_secrets_service = lambda: secrets_service

    print("\nAfter monkeypatch:")
    print(f"  bedrock_module.secrets_service_module.get_secrets_service = {bedrock_module.secrets_service_module.get_secrets_service}")

    # Test
    provider = BedrockProvider()
    print("\nCalling _resolve_credentials...")
    access_key, secret_key, region = provider._resolve_credentials()

    print(f"\nResults:")
    print(f"  access_key: {access_key}")
    print(f"  secret_key: {secret_key}")
    print(f"  region: {region}")

    # Restore
    bedrock_module.secrets_service_module.get_secrets_service = original
