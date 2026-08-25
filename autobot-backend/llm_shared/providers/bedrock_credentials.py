# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vault lookup and region validation for the Bedrock provider (#15023).

Split out of ``bedrock.py`` because that module reached its 600-line ceiling,
and this is the one cohesive piece in it that owes nothing to provider state:
the credential retrieval touches no ``self``, and the region pattern is data.

``bedrock.py`` re-exports every name defined here, so
``llm_shared.providers.bedrock.BEDROCK_VAULT_ENTRY_NAME`` and its siblings
still resolve for existing importers and patch targets.
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
