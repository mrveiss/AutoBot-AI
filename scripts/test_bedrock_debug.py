#!/usr/bin/env python3
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

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

    print("Creating secret...")
    secret = secrets_service.create_secret(
        name="bedrock_aws_credentials",
        secret_type="aws_bedrock_credentials",
        value=json.dumps(test_creds),
        scope="general",
        created_by="test",
    )
    print(f"Secret created: {secret['id']}")

    # Verify we can retrieve it
    print("\nVerifying secret retrieval...")
    retrieved = secrets_service.get_secret(
        name="bedrock_aws_credentials",
        scope="general",
        include_value=True,
        accessed_by="test",
    )
    print(f"Retrieved secret: {retrieved is not None}")
    if retrieved:
        print(f"  Has value: {'value' in retrieved}")
        if 'value' in retrieved:
            print(f"  Value: {retrieved['value'][:50]}...")

    # Import bedrock module
    from llm_shared.providers.bedrock import BedrockProvider
    import llm_shared.providers.bedrock as bedrock_module

    # Monkeypatch
    print("\nMonkeypatching...")
    original = bedrock_module.secrets_service_module.get_secrets_service
    bedrock_module.secrets_service_module.get_secrets_service = lambda: secrets_service

    # Test what get_secrets_service returns
    print("Testing monkeypatched function...")
    test_service = bedrock_module.secrets_service_module.get_secrets_service()
    print(f"  Returned service: {test_service}")
    print(f"  Same as our secrets_service: {test_service is secrets_service}")

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
