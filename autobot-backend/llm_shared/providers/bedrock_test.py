# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for AWS credential resolution in the Bedrock provider (#15023).

The prior fix removed the ``SecretsService`` lookup entirely in a formatting
auto-fix commit (``d470c47c09``) with nothing exercising that path, so it went
unnoticed. These tests drive the real ``_resolve_credentials()`` path -- only
``get_secrets_service`` (and ``logger``, to assert on warnings) is replaced,
never ``_resolve_credentials`` itself -- and assert on the *specific* call the
vault must receive and the *specific* values it must win over the environment.
A permissive mock that accepts any call would not have caught the regression.

Credentials are patched directly into ``BedrockProvider``'s own module
globals (rather than a separately re-imported module reference), since this
tree's test collection can bind two distinct module objects for the same
dotted path -- patching the wrong one would silently no-op.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_shared.providers.bedrock import BEDROCK_SECRET_NAME, BEDROCK_SECRET_TYPE, BedrockProvider

_MODULE_GLOBALS = BedrockProvider._load_credentials_from_vault.__globals__


def _vault_returning(value_json: str | None, secret_type: str = BEDROCK_SECRET_TYPE) -> MagicMock:
    """A ``get_secrets_service()`` stand-in whose ``get_secret`` returns *value_json*."""
    service = MagicMock()
    if value_json is None:
        service.get_secret.return_value = None
    else:
        service.get_secret.return_value = {"id": "sec-1", "secret_type": secret_type, "value": value_json}
    return service


@pytest.fixture(autouse=True)
def _clear_aws_env(monkeypatch):
    """Every test starts with a clean AWS credential environment."""
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(var, raising=False)


def _patch_vault(monkeypatch, vault) -> None:
    monkeypatch.setitem(_MODULE_GLOBALS, "get_secrets_service", lambda: vault)


def _patch_warning(monkeypatch) -> MagicMock:
    warning_mock = MagicMock()
    monkeypatch.setitem(_MODULE_GLOBALS, "logger", MagicMock(warning=warning_mock, info=MagicMock()))
    return warning_mock


def test_resolve_credentials_consults_secrets_service_first(monkeypatch):
    """SecretsService is consulted, with the exact call the vault reader must make."""
    vault = _vault_returning(
        '{"aws_access_key_id": "AKIAVAULTVAULTVAULT", '
        '"aws_secret_access_key": "vault-secret", "region": "eu-west-1"}'
    )
    _patch_vault(monkeypatch, vault)
    # Set env vars too, to prove the vault wins priority rather than merely
    # being the only source available.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAENVENVENVENVENV")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")

    provider = BedrockProvider(settings={})
    access_key, secret_key, region = provider._resolve_credentials()

    assert (access_key, secret_key, region) == ("AKIAVAULTVAULTVAULT", "vault-secret", "eu-west-1")
    vault.get_secret.assert_called_once_with(
        name=BEDROCK_SECRET_NAME,
        scope="general",
        include_value=True,
        accessed_by="bedrock_provider",
    )


def test_resolve_credentials_falls_back_to_env_and_logs_warning(monkeypatch):
    """Vault not configured -> env fallback is used AND a warning names the source."""
    _patch_vault(monkeypatch, _vault_returning(None))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAENVENVENVENVENV")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
    warning_mock = _patch_warning(monkeypatch)

    provider = BedrockProvider(settings={})
    access_key, secret_key, _region = provider._resolve_credentials()

    assert (access_key, secret_key) == ("AKIAENVENVENVENVENV", "env-secret")
    assert warning_mock.call_count == 1
    logged_message = warning_mock.call_args[0][0]
    assert "SecretsService" in logged_message
    assert "environment" in logged_message


def test_resolve_credentials_no_vault_no_env_falls_through_to_iam_role(monkeypatch):
    """Neither source configured -> both creds are None (boto3 default/IAM role chain)."""
    _patch_vault(monkeypatch, _vault_returning(None))

    provider = BedrockProvider(settings={})
    access_key, secret_key, region = provider._resolve_credentials()

    assert access_key is None
    assert secret_key is None
    assert region == "us-east-1"


def test_vault_lookup_failure_is_logged_and_falls_back(monkeypatch):
    """A raising SecretsService lookup never propagates -- it logs and falls back."""
    vault = MagicMock()
    vault.get_secret.side_effect = RuntimeError("db locked")
    _patch_vault(monkeypatch, vault)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAENVENVENVENVENV")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
    warning_mock = _patch_warning(monkeypatch)

    provider = BedrockProvider(settings={})
    access_key, secret_key, _region = provider._resolve_credentials()

    assert (access_key, secret_key) == ("AKIAENVENVENVENVENV", "env-secret")
    # Two warnings: the vault-lookup failure, then the plain-text-fallback notice.
    assert warning_mock.call_count == 2
    assert "SecretsService lookup failed" in warning_mock.call_args_list[0][0][0]


def test_vault_secret_type_mismatch_is_rejected(monkeypatch):
    """A same-named secret of the wrong type is never trusted as Bedrock's credentials."""
    vault = _vault_returning(
        '{"aws_access_key_id": "AKIAWRONGTYPEWRONGT", "aws_secret_access_key": "x"}',
        secret_type="some_other_secret_type",
    )
    _patch_vault(monkeypatch, vault)
    warning_mock = _patch_warning(monkeypatch)

    provider = BedrockProvider(settings={})
    access_key, secret_key, _region = provider._resolve_credentials()

    assert access_key is None
    assert secret_key is None
    assert any("unexpected secret_type" in call.args[0] for call in warning_mock.call_args_list)
