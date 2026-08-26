# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vault lookup and credential validation for the Bedrock provider (#15023).

Split out of ``bedrock.py`` because that module reached its 600-line ceiling,
and this is the one cohesive piece in it that owes nothing to provider state:
the credential retrieval touches no ``self``, and the region pattern is data.

These names live here and only here. ``bedrock.py`` imports only what it
calls and deliberately re-exports nothing: an ``__all__`` whose only purpose is to
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
from autobot_shared.security.redaction import redact_text
from services.secrets_audit_store import (
    REASON_LOOKUP_ERROR,
    REASON_MALFORMED_VALUE,
    REASON_TYPE_MISMATCH,
)
from services.secrets_service import get_secrets_service

logger = get_logger(__name__)

#: Lookup key (the vault entry's ``name`` column, not a secret value) and
#: type of the Bedrock AWS credential pair in SecretsService -- matches the
#: sole writer, migrate_bedrock_credentials.py.
BEDROCK_VAULT_ENTRY_NAME = "bedrock_aws_credentials"
BEDROCK_VAULT_ENTRY_TYPE = "aws_bedrock_credentials"

#: Identity stamped on every audit row this provider causes -- the successful
#: access and the failed ones alike, so both limbs of #15023 AC3 attribute to
#: the same principal and a query for one finds the other.
BEDROCK_ACCESSED_BY = "bedrock_provider"

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


#: Replacement for any credential value removed from text on its way to a log.
_CREDENTIAL_MASK = "***"


def scrub_credentials(text: str, credentials: tuple[str | None, str | None, str | None]) -> str:
    """Return *text* with the canonical redactions applied and *credentials* masked out.

    The AWS SDK names the key it rejected in some of its error messages, and an
    availability probe logs whatever it caught. Masking by *value* on top of the
    shared pattern redactor is what makes the result provable rather than
    probable: the resolved values are in hand here, so nothing is left to a
    pattern's coverage (#15071).

    Only the access key and the secret key are masked; the region is not a
    secret and removing it would cost the log line its only useful detail.
    """
    scrubbed = redact_text(text)
    for value in credentials[:2]:
        if isinstance(value, str) and value:
            scrubbed = scrubbed.replace(value, _CREDENTIAL_MASK)
    return scrubbed


def build_boto3_client(service_name: str, credentials: tuple[str | None, str | None, str | None]):
    """Build a boto3 client for *service_name* from one already-resolved credential tuple.

    Takes the resolved tuple rather than resolving its own, so every client built
    during a single operation is provably built from the *same* pair. Two
    resolutions can disagree -- a settings reload, an environment mutation, or a
    vault rotation landing between them -- and a mismatched access-key/secret-key
    pair does not raise: it fails opaquely at call time, which the caller then
    sees only as an unexplained ``is_available() -> False`` (#15071).

    Explicit credentials are added only when both are present, so an unset pair
    falls through to boto3's own chain (IAM role / instance profile) instead of
    being handed ``None`` for each.

    Raises:
        ImportError: If boto3 is not installed.
        ValueError: If the region is absent or not AWS-region-shaped. A region
            can originate from a vault entry, which is a trust boundary and not
            a format guarantee, so it is checked before it is used to build a
            boto3 endpoint host -- and never echoed back, per
            validate_credential_pair.
    """
    try:
        import boto3
    except ImportError as exc:
        raise ImportError("boto3 not installed. Run: pip install boto3") from exc

    access_key, secret_key, region = credentials
    if not region or not _AWS_REGION_PATTERN.match(region):
        raise ValueError("Bedrock: resolved AWS region has an unexpected format, refusing to initialize client")

    client_kwargs: dict[str, object] = {"region_name": region, "service_name": service_name}
    if access_key and secret_key:
        client_kwargs["aws_access_key_id"] = access_key
        client_kwargs["aws_secret_access_key"] = secret_key
    return boto3.client(**client_kwargs)


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


def _audit_vault_rejection(reason: str, secret_id: str | None = None) -> None:
    """Record a vault row *this module* rejected, after ``get_secret()`` returned it.

    ``get_secret()`` audits the failures it can see itself -- no such entry, and
    an expired one. The three below are only visible here, so without this they
    would be a log line and nothing else, which is exactly the hole #15023's AC3
    failure limb names. Auditing is best-effort by construction: a credential
    path must not start failing because its audit sink did.
    """
    try:
        get_secrets_service().record_access_failure(
            reason,
            name=BEDROCK_VAULT_ENTRY_NAME,
            accessed_by=BEDROCK_ACCESSED_BY,
            secret_id=secret_id,
        )
    except Exception as exc:  # noqa: BLE001 - audit write must never break credential resolution
        logger.warning("Bedrock: could not record the failed credential access: %s", type(exc).__name__)


def load_credentials_from_vault() -> tuple[str | None, str | None, str | None]:
    """Look up the Bedrock AWS credential pair in SecretsService.

    Returns (access_key, secret_key, region), each None if not configured or
    unusable -- never raises; any failure is logged (never the credential value)
    and recorded in ``secrets_audit``. A successful lookup is audited by
    ``get_secret()``; so are its own two failure modes, so the rejections
    audited here are only the ones it cannot see (#15023 AC3).
    """
    try:
        secret = get_secrets_service().get_secret(
            name=BEDROCK_VAULT_ENTRY_NAME,
            scope="general",
            include_value=True,
            accessed_by=BEDROCK_ACCESSED_BY,
        )
    except Exception as exc:  # noqa: BLE001 - vault lookup is best-effort, fallback follows
        logger.warning("Bedrock SecretsService lookup failed, falling back: %s", type(exc).__name__)
        _audit_vault_rejection(REASON_LOOKUP_ERROR)
        return None, None, None
    # No row, or an expired one: get_secret() has already written the row that
    # distinguishes those two, so auditing again here would double-count them.
    if not secret or "value" not in secret:
        return None, None, None
    if secret.get("secret_type") != BEDROCK_VAULT_ENTRY_TYPE:
        logger.warning("Bedrock secret '%s' has an unexpected secret_type, ignoring", BEDROCK_VAULT_ENTRY_NAME)
        _audit_vault_rejection(REASON_TYPE_MISMATCH, secret.get("id"))
        return None, None, None
    try:
        creds = json.loads(secret["value"])
    except (TypeError, ValueError) as exc:
        logger.warning("Bedrock secret from SecretsService is not valid JSON: %s", type(exc).__name__)
        _audit_vault_rejection(REASON_MALFORMED_VALUE, secret.get("id"))
        return None, None, None
    logger.info("Loaded Bedrock credentials from SecretsService (encrypted, access audited)")
    return creds.get("aws_access_key_id"), creds.get("aws_secret_access_key"), creds.get("region")
