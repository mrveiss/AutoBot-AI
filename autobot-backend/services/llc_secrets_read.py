# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dual-read path for LLC company secrets imported into the envelope store (#10088 / Task 4).

Resolves a secret imported by ``llc_secrets_importer`` via its
``imported_from_llc_secrets`` marker and decrypts it through the secret's
Company vault (``company:<company_id>``), so ``SecretService.get()`` can serve
either path with no response-shape drift for its callers. Returns ``None``
(fall back to the legacy ``llc_secrets`` Fernet decrypt) when the secret hasn't
been imported yet, the envelope read fails, or the feature flag is off — the
legacy table remains authoritative until this path is enabled and proven.

Correctness note (revoke safety): callers MUST resolve and revocation-check the
legacy ``llc_secrets`` row first (``SecretService._fetch_active`` already does
this) and only then call this module with that row's id. A revoked/absent
legacy row therefore never reaches — and can never stale-resurrect through —
this dual-read path.

Feature-flagged the same way as the JSON-store cutover
(``services.json_secrets_read.JSON_UNIFIED_READ_ENV``): default off, so
behaviour is byte-identical until explicitly enabled.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

LLC_UNIFIED_READ_ENV = "AUTOBOT_SECRETS_LLC_UNIFIED_READ"
_MARKER = "imported_from_llc_secrets"


def llc_unified_read_enabled() -> bool:
    """Whether the LLC-secrets dual-read (envelope-first) path is enabled."""
    return os.environ.get(LLC_UNIFIED_READ_ENV, "false").strip().lower() in ("1", "true", "yes")


async def _find_by_marker(session, source_id: str):
    from sqlalchemy import select

    from models.secret import Secret

    marker = Secret.extra_data[_MARKER].astext
    result = await session.execute(select(Secret).where(marker == str(source_id), Secret.is_active.is_(True)))
    return result.scalars().first()


async def read_imported_llc_secret_in_session(
    session, *, source_id: str, company_id: str, root_key: bytes
) -> str | None:
    """Resolve + decrypt an imported LLC company secret within *session* (the testable core).

    ``source_id`` is the legacy ``llc_secrets`` row's id, already resolved and
    revocation-checked by the caller (see the module docstring).
    """
    from autobot_shared.secrets_envelope import DecryptionError, UnsupportedFormatError
    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError, SecretNotFoundError

    row = await _find_by_marker(session, source_id)
    if row is None:
        return None  # not yet imported -> legacy llc_secrets fallback
    try:
        plaintext = await EnvelopeSecretsService(root_key=root_key).read(
            session, secret_id=row.id, accessible_vaults={VaultRef(VaultKind.COMPANY, company_id)}
        )
    except (
        SecretAccessError,
        SecretNotFoundError,
        DecryptionError,
        UnsupportedFormatError,
        KeyError,
        ValueError,
    ) as exc:
        logger.warning("Envelope read unusable for imported LLC secret %s: %s — falling back", source_id, exc)
        return None
    return plaintext.decode("utf-8")
