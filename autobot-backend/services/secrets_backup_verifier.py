# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one verifier for "a backup of the secrets store exists" (#18281).

A destructive secrets proposal carries a ``backup_reference``. Text is not a backup, so the
reference is checked against the SLM, which owns the backup record and the artifact
(``GET /api/stateful/secrets-backups/{id}``, authenticated with ``X-Internal-API-Key`` like
every other service-to-service call; see ``autobot_shared.node_proxy``).

:func:`verify_backup` is True ONLY when the record exists, is ``completed``, is a ``secrets``
backup, completed within ``SECRETS_BACKUP_MAX_AGE_S``, and the SLM re-checksummed the stored
file and it matched. Anything else -- including a timeout, a transport error, a non-200 or an
unparsable answer -- is False and logged: the caller refuses, it never proceeds on doubt.
There is deliberately no flag that skips this check.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.node_proxy import INTERNAL_KEY_HEADER, internal_api_key, node_client
from autobot_shared.slm_rest_url import rest_url
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

#: Oldest accepted backup. Default one day: it spans human-approval latency, yet few secrets can
#: have changed since. Env-backed and registered (AUTOBOT_SECRETS_BACKUP_MAX_AGE_S).
SECRETS_BACKUP_MAX_AGE_S = env_int_clamped("AUTOBOT_SECRETS_BACKUP_MAX_AGE_S", 86400, 60, 2592000)
#: Tolerated SLM-vs-backend clock skew before a "future" completion time is distrusted.
CLOCK_SKEW_S = 120
STATUS_PATH = "/api/stateful/secrets-backups/{backup_id}"
_COMPLETED = "completed"
_SECRETS = "secrets"  # pragma: allowlist secret


def _fresh(completed_at: object) -> bool:
    """Whether *completed_at* (ISO text; naive means UTC) is within the accepted age."""
    if not isinstance(completed_at, str):
        return False
    stamp = datetime.fromisoformat(completed_at)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    return -CLOCK_SKEW_S <= age <= SECRETS_BACKUP_MAX_AGE_S


def _acceptable(record: object) -> bool:
    """The record-level conditions (b)-(e)."""
    return (
        isinstance(record, dict)
        and record.get("status") == _COMPLETED
        and record.get("service_type") == _SECRETS
        and _fresh(record.get("completed_at"))
        and record.get("integrity_ok") is True
    )


async def _fetch(reference: str) -> object:
    url = rest_url(config.slm_url.rstrip("/"), STATUS_PATH.format(backup_id=quote(reference, safe="")))
    async with node_client() as client:
        response = await client.get(url, headers={INTERNAL_KEY_HEADER: internal_api_key()})
    if response.status_code != 200:
        logger.warning("Secrets backup %r not verified: SLM answered %s", reference, response.status_code)
        return None
    return response.json()


async def verify_backup(reference: str) -> bool:
    """Whether *reference* names a real, complete, recent, intact backup of the secrets store."""
    if not reference or not internal_api_key():
        logger.warning("Secrets backup not verified: no reference or no internal API key configured")
        return False
    try:
        verified = _acceptable(await _fetch(reference))
    except Exception as exc:
        logger.warning("Secrets backup %r not verified: %s: %s", reference, type(exc).__name__, exc)
        return False
    if not verified:
        logger.warning(
            "Secrets backup %r refused: not completed, not a secrets backup, too old, or failed integrity", reference
        )
    return verified
