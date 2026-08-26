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

from llm_shared.providers.bedrock import BedrockProvider
from llm_shared.providers.bedrock_credentials import (
    _AWS_REGION_PATTERN,
    BEDROCK_ACCESSED_BY,
    BEDROCK_VAULT_ENTRY_NAME,
    BEDROCK_VAULT_ENTRY_TYPE,
    validate_credential_pair,
)
from services.secrets_audit_store import (
    REASON_LOOKUP_ERROR,
    REASON_MALFORMED_VALUE,
    REASON_TYPE_MISMATCH,
)

#: Credential resolution spans two modules since #15023: the vault lookup lives in
#: ``bedrock_credentials`` and the settings/env fallback in ``bedrock``. Reaching them
#: through the bound functions keeps the patch targets correct if either moves again.
_VAULT_GLOBALS = BedrockProvider._load_credentials_from_vault.__globals__
_PROVIDER_GLOBALS = BedrockProvider._resolve_credentials.__globals__

#: Format-valid stand-ins for the vault/env credential pairs below -- shaped to pass
#: validate_credential_pair() (AKIA/ASIA + 16 alnum access key, 40-char base64 secret)
#: so these fixtures exercise credential *resolution* without tripping the *format*
#: validation restored by #15080. Distinct per source so priority-order assertions
#: still tell vault and env values apart.
_WELL_FORMED_VAULT_ACCESS_KEY_ID = "AKIA" + "V" * 16
_WELL_FORMED_VAULT_SECRET_ACCESS_KEY = "V" * 40
_WELL_FORMED_ENV_ACCESS_KEY_ID = "ASIA" + "E" * 16  # STS prefix avoids the AKIA warning below
_WELL_FORMED_ENV_SECRET_ACCESS_KEY = "E" * 40


def _vault_returning(value_json: str | None, secret_type: str = BEDROCK_VAULT_ENTRY_TYPE) -> MagicMock:
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
    monkeypatch.setitem(_VAULT_GLOBALS, "get_secrets_service", lambda: vault)


def _patch_warning(monkeypatch) -> MagicMock:
    """One mock collecting warnings from BOTH credential modules.

    A single resolve can warn twice from two different modules -- the vault
    lookup failing and the plain-text fallback being used. Patching only one
    would silently halve every call_count assertion below.
    """
    warning_mock = MagicMock()
    for module_globals in (_VAULT_GLOBALS, _PROVIDER_GLOBALS):
        monkeypatch.setitem(module_globals, "logger", MagicMock(warning=warning_mock, info=MagicMock()))
    return warning_mock


def test_resolve_credentials_consults_secrets_service_first(monkeypatch):
    """SecretsService is consulted, with the exact call the vault reader must make."""
    vault = _vault_returning(
        '{"aws_access_key_id": "%s", '
        '"aws_secret_access_key": "%s", "region": "eu-west-1"}'
        % (_WELL_FORMED_VAULT_ACCESS_KEY_ID, _WELL_FORMED_VAULT_SECRET_ACCESS_KEY)
    )
    _patch_vault(monkeypatch, vault)
    # Set env vars too, to prove the vault wins priority rather than merely
    # being the only source available.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _WELL_FORMED_ENV_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _WELL_FORMED_ENV_SECRET_ACCESS_KEY)

    provider = BedrockProvider(settings={})
    access_key, secret_key, region = provider._resolve_credentials()

    assert (access_key, secret_key, region) == (
        _WELL_FORMED_VAULT_ACCESS_KEY_ID,
        _WELL_FORMED_VAULT_SECRET_ACCESS_KEY,
        "eu-west-1",
    )
    vault.get_secret.assert_called_once_with(
        name=BEDROCK_VAULT_ENTRY_NAME,
        scope="general",
        include_value=True,
        accessed_by=BEDROCK_ACCESSED_BY,
    )


def test_resolve_credentials_falls_back_to_env_and_logs_warning(monkeypatch):
    """Vault not configured -> env fallback is used AND a warning names the source."""
    _patch_vault(monkeypatch, _vault_returning(None))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _WELL_FORMED_ENV_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _WELL_FORMED_ENV_SECRET_ACCESS_KEY)
    warning_mock = _patch_warning(monkeypatch)

    provider = BedrockProvider(settings={})
    access_key, secret_key, _region = provider._resolve_credentials()

    assert (access_key, secret_key) == (_WELL_FORMED_ENV_ACCESS_KEY_ID, _WELL_FORMED_ENV_SECRET_ACCESS_KEY)
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
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _WELL_FORMED_ENV_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _WELL_FORMED_ENV_SECRET_ACCESS_KEY)
    warning_mock = _patch_warning(monkeypatch)

    provider = BedrockProvider(settings={})
    access_key, secret_key, _region = provider._resolve_credentials()

    assert (access_key, secret_key) == (_WELL_FORMED_ENV_ACCESS_KEY_ID, _WELL_FORMED_ENV_SECRET_ACCESS_KEY)
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


# The region reaches `boto3.client(region_name=...)` from a SecretsService entry,
# so it is validated before it can shape an endpoint host. Both directions are
# pinned by name: a pattern that rejects a real region turns a working
# deployment into a hard failure, which is worse than the injection the guard
# exists to stop -- so the accepted set is enumerated explicitly rather than
# trusted to a regex nobody re-reads.
@pytest.mark.parametrize(
    "region",
    [
        "us-east-1",
        "eu-west-1",
        "ap-southeast-4",
        "il-central-1",
        "me-central-1",
        "us-gov-west-1",
        "cn-northwest-1",
        "us-iso-east-1",
        "us-isob-east-1",
    ],
)
def test_every_real_aws_partition_is_accepted(region):
    assert _AWS_REGION_PATTERN.match(region), f"{region} is a real AWS region and must not be rejected"


@pytest.mark.parametrize(
    "value",
    [
        "us-east-1a",
        "evil.example.invalid",
        "us-east-1;curl http://x",
        "../../etc/passwd",
        "http://internal/",
        "US-EAST-1",
        "us-east",
        "",
    ],
)
def test_non_region_values_are_refused(value):
    assert not _AWS_REGION_PATTERN.match(value), f"{value!r} is not a region and must not reach boto3"


# --- validate_credential_pair() (#15080) --------------------------------------------
#
# The AWS key pair reaches boto3 through the same vault-is-a-trust-boundary path as
# the region above, but travelled unvalidated after the formatting auto-fix d470c47c09
# dropped `_validate_credentials()` and #15062 restored only the vault lookup, not the
# validator. These tests exercise `validate_credential_pair()` directly (the well-formed
# and malformed shapes) and `_resolve_credentials()` end-to-end (a malformed vault entry
# is refused before it can reach `client_kwargs`).


@pytest.mark.parametrize(
    "access_key, secret_key",
    [
        ("AKIA" + "A" * 16, "A" * 40),  # long-lived IAM user credentials
        ("ASIA" + "0" * 16, "B" * 40),  # temporary STS credentials
        (None, None),  # IAM role authentication -- both absent is well-formed too
    ],
)
def test_well_formed_credential_pair_is_accepted(access_key, secret_key):
    """Counterweight: a validator that rejected everything would fail this too."""
    validate_credential_pair(access_key, secret_key)  # must not raise


@pytest.mark.parametrize(
    "access_key, secret_key",
    [
        ("AKIA" + "A" * 16, None),  # secret key missing
        (None, "A" * 40),  # access key missing
        ("not-shaped-like-an-access-key", "A" * 40),  # wrong prefix/length
        ("AKIA" + "a" * 16, "A" * 40),  # lowercase suffix, not the AWS charset
        ("AKIA" + "A" * 15, "A" * 40),  # one character short
        ("AKIA" + "A" * 16, "A" * 39),  # secret key one character short
        ("AKIA" + "A" * 16, "A" * 41),  # secret key one character long
        ("AKIA" + "A" * 16, "not base64 at all!!"),  # secret key outside the charset
        ("AKIA" + "A" * 16, 12345),  # non-string secret key (malformed vault JSON)
        (["AKIA" + "A" * 16], "A" * 40),  # non-string access key (malformed vault JSON)
    ],
)
def test_malformed_credential_pair_is_rejected(access_key, secret_key):
    with pytest.raises(ValueError):
        validate_credential_pair(access_key, secret_key)


def test_rejection_never_echoes_the_credential_value():
    """The whole point of #15080: a malformed value must never reach the exception text."""
    telltale = "TELLTALE-MARKER-VALUE-THAT-MUST-NEVER-APPEAR"
    with pytest.raises(ValueError) as excinfo:
        validate_credential_pair("AKIA" + telltale[:16], "A" * 40)
    assert telltale not in str(excinfo.value)
    assert "TELLTALE" not in str(excinfo.value)


def test_resolve_credentials_rejects_a_malformed_vault_pair(monkeypatch):
    """A malformed vault entry is refused inside `_resolve_credentials()` itself,
    before it can reach `client_kwargs` -- not left for boto3 to fail on later."""
    vault = _vault_returning(
        '{"aws_access_key_id": "not-an-aws-access-key", '
        '"aws_secret_access_key": "%s", "region": "eu-west-1"}' % _WELL_FORMED_VAULT_SECRET_ACCESS_KEY
    )
    _patch_vault(monkeypatch, vault)

    provider = BedrockProvider(settings={})
    with pytest.raises(ValueError) as excinfo:
        provider._resolve_credentials()
    assert "not-an-aws-access-key" not in str(excinfo.value)


# --- failed-access auditing (#15023 AC3, failure limb) --------------------------------
#
# get_secret() audits the two failures it can see itself -- no such entry, and an
# expired one. The three below are verdicts this module reaches *after* get_secret()
# has returned, so nothing but the caller can record them; before #15023 they were a
# logger.warning and a silent (None, None, None). The real row-writing is covered
# against a real database in services/secrets_audit_store_test.py; what is pinned here
# is that the provider reports each rejection, with the right reason, to the right
# principal -- and that it does NOT report the two get_secret() already owns.


def test_vault_lookup_exception_is_audited(monkeypatch):
    vault = MagicMock()
    vault.get_secret.side_effect = RuntimeError("db locked")
    _patch_vault(monkeypatch, vault)
    _patch_warning(monkeypatch)

    BedrockProvider(settings={})._resolve_credentials()

    vault.record_access_failure.assert_called_once_with(
        REASON_LOOKUP_ERROR,
        name=BEDROCK_VAULT_ENTRY_NAME,
        accessed_by=BEDROCK_ACCESSED_BY,
        secret_id=None,
    )


def test_secret_type_mismatch_is_audited_against_the_rejected_row(monkeypatch):
    vault = _vault_returning('{"aws_access_key_id": "x"}', secret_type="some_other_secret_type")
    _patch_vault(monkeypatch, vault)
    _patch_warning(monkeypatch)

    BedrockProvider(settings={})._resolve_credentials()

    vault.record_access_failure.assert_called_once_with(
        REASON_TYPE_MISMATCH,
        name=BEDROCK_VAULT_ENTRY_NAME,
        accessed_by=BEDROCK_ACCESSED_BY,
        secret_id="sec-1",
    )


def test_unparseable_vault_value_is_audited(monkeypatch):
    vault = _vault_returning("{not json at all")
    _patch_vault(monkeypatch, vault)
    _patch_warning(monkeypatch)

    BedrockProvider(settings={})._resolve_credentials()

    reason, kwargs = vault.record_access_failure.call_args[0][0], vault.record_access_failure.call_args[1]
    assert reason == REASON_MALFORMED_VALUE
    assert kwargs["secret_id"] == "sec-1"
    # The malformed value must not travel to the audit sink in any argument.
    assert "not json at all" not in str(vault.record_access_failure.call_args)


def test_absent_vault_entry_is_not_double_audited(monkeypatch):
    """get_secret() already wrote the not-found row; a second one here would double-count."""
    vault = _vault_returning(None)
    _patch_vault(monkeypatch, vault)

    BedrockProvider(settings={})._resolve_credentials()

    vault.record_access_failure.assert_not_called()


def test_a_failing_audit_sink_never_breaks_credential_resolution(monkeypatch):
    """Auditing is best-effort: a broken sink must not take the credential path down."""
    vault = MagicMock()
    vault.get_secret.side_effect = RuntimeError("db locked")
    vault.record_access_failure.side_effect = RuntimeError("audit sink down")
    _patch_vault(monkeypatch, vault)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _WELL_FORMED_ENV_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _WELL_FORMED_ENV_SECRET_ACCESS_KEY)
    _patch_warning(monkeypatch)

    access_key, secret_key, _region = BedrockProvider(settings={})._resolve_credentials()

    assert (access_key, secret_key) == (_WELL_FORMED_ENV_ACCESS_KEY_ID, _WELL_FORMED_ENV_SECRET_ACCESS_KEY)
