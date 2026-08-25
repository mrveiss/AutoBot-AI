# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vault lookup and region validation for the Bedrock provider (#15023).

Split out of ``bedrock.py`` because that module reached its 600-line ceiling,
and this is the one cohesive piece in it that owes nothing to provider state:
the credential retrieval touches no ``self``, and the region pattern is data.

These names live here and only here. ``bedrock.py`` imports the two it uses
and deliberately re-exports nothing: an ``__all__`` whose only purpose is to
satisfy F401 would be indirection existing to quiet a linter. Import the
constants from this module, not through ``bedrock`` -- ``llm_shared.providers.
bedrock.BEDROCK_VAULT_ENTRY_NAME`` raises ``AttributeError`` (#15081).

The test patches ``get_secrets_service`` through
``BedrockProvider._load_credentials_from_vault.__globals__``, which resolves to
*this* module's globals -- where the call actually is -- so the patch target
follows the function rather than a re-export.
"""

from __future__ import annotations

import json
import re

from autobot_shared.logging_manager import get_logger
from services.secrets_service import get_secrets_service

logger = get_logger(__name__)

#: Lookup key (the vault entry's ``name`` column, not a secret value) and
#: type of the Bedrock AWS credential pair in SecretsService -- matches the
#: sole writer, migrate_bedrock_credentials.py.
BEDROCK_VAULT_ENTRY_NAME = "bedrock_aws_credentials"
BEDROCK_VAULT_ENTRY_TYPE = "aws_bedrock_credentials"

#: AWS region shape, e.g. "us-east-1", "eu-west-1", "us-gov-west-1". Used to
#: validate a region resolved from SecretsService before it is used to build
#: a boto3 endpoint -- a vault entry is a trust boundary, not a guarantee of
#: well-formed content.
#:
#: Deliberately matches the general partition grammar rather than an enumerated
#: list of partitions: AWS adds regions continuously, and a pattern that admits
#: only ``-gov-`` rejects the ISO partitions (``us-iso-east-1``,
#: ``us-isob-east-1``) outright. Rejecting a real region here would turn a
#: working deployment into a hard failure, which is a worse outcome than the
#: injection this guard exists to stop -- so the pattern is shaped to exclude
#: hostnames, paths and availability zones ("us-east-1a"), not to enumerate
#: partitions.
_AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d{1,2}$")

#: AWS access-key shape: AKIA (long-lived IAM user) or ASIA (temporary STS) followed
#: by 16 uppercase-alphanumeric characters -- 20 characters total. Restores the check
#: dropped alongside the vault lookup in d470c47c09 (#15080); see validate_credential_pair.
_AWS_ACCESS_KEY_PATTERN = re.compile(r"^(AKIA|ASIA)[0-9A-Z]{16}$")

#: AWS secret-access-key shape: exactly 40 base64 characters (A-Za-z0-9+/).
_AWS_SECRET_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/]{40}$")


def validate_credential_pair(access_key: object, secret_key: object) -> None:
    """Validate the shape of a resolved AWS access-key/secret-key pair.

    Applies regardless of source (SecretsService vault, settings, or environment) --
    a vault entry is a trust boundary, not a format guarantee, the same reasoning
    already applied to the region via ``_AWS_REGION_PATTERN``. Restores the check
    dropped alongside the vault lookup in the formatting auto-fix ``d470c47c09``,
    which #15062 never re-added (#15080).

    An empty string is treated the same as ``None`` (no explicit credentials,
    IAM role authentication applies). A non-string value -- reachable now that
    a vault entry travels through ``json.loads`` rather than only ``os.getenv``
    -- is rejected the same as a malformed string, never inspected further.

    Raises:
        ValueError: Naming the malformed field only -- never any part of its
            value or its length, which is itself derived from the value.
            Deliberately louder than a silent pass-through: a malformed vault
            row means active misconfiguration, and falling through to the
            boto3 default (IAM role) chain would substitute an unintended
            identity rather than surface the bad entry.
    """
    if not access_key:
        access_key = None
    if not secret_key:
        secret_key = None

    if access_key is None and secret_key is None:
        logger.info("Using IAM role authentication (no explicit Bedrock credentials)")
        return

    if (access_key is None) != (secret_key is None):
        raise ValueError(
            "Bedrock: resolved AWS credentials are incomplete -- both the access key and "
            "the secret key must be present, or both absent for IAM role authentication"
        )

    if not isinstance(access_key, str) or not _AWS_ACCESS_KEY_PATTERN.match(access_key):
        raise ValueError("Bedrock: resolved AWS access key has an unexpected format, refusing to initialize client")
    if access_key.startswith("AKIA"):
        logger.warning(
            "Bedrock: using long-lived IAM user credentials (AKIA prefix); consider STS "
            "temporary credentials (ASIA prefix) or IAM role authentication instead"
        )
    else:
        logger.info("Bedrock: using STS temporary credentials (ASIA prefix)")

    if not isinstance(secret_key, str) or not _AWS_SECRET_KEY_PATTERN.match(secret_key):
        raise ValueError("Bedrock: resolved AWS secret key has an unexpected format, refusing to initialize client")


def load_credentials_from_vault() -> tuple[str | None, str | None, str | None]:
    """Look up the Bedrock AWS credential pair in SecretsService.

    Returns (access_key, secret_key, region), each None if not configured or
    unusable -- never raises; any failure is logged (never the credential
    value). A successful lookup is audited to ``secrets_audit`` by ``get_secret()``.
    """
    try:
        secret = get_secrets_service().get_secret(
            name=BEDROCK_VAULT_ENTRY_NAME,
            scope="general",
            include_value=True,
            accessed_by="bedrock_provider",
        )
    except Exception as exc:  # noqa: BLE001 - vault lookup is best-effort, fallback follows
        logger.warning("Bedrock SecretsService lookup failed, falling back: %s", type(exc).__name__)
        return None, None, None
    if not secret or "value" not in secret:
        return None, None, None
    if secret.get("secret_type") != BEDROCK_VAULT_ENTRY_TYPE:
        logger.warning("Bedrock secret '%s' has an unexpected secret_type, ignoring", BEDROCK_VAULT_ENTRY_NAME)
        return None, None, None
    try:
        creds = json.loads(secret["value"])
    except (TypeError, ValueError) as exc:
        logger.warning("Bedrock secret from SecretsService is not valid JSON: %s", type(exc).__name__)
        return None, None, None
    logger.info("Loaded Bedrock credentials from SecretsService (encrypted, access audited)")
    return creds.get("aws_access_key_id"), creds.get("aws_secret_access_key"), creds.get("region")
