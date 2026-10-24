# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resolve the API-key HMAC pepper from the SLM secrets store (#19120, #16299).

The pepper is a rotatable credential, so it lives in the SLM secrets store
(``SystemSecret``, managed on ``/slm/settings/admin/secrets``) like every other
system secret. Resolution order:

1. the secrets store (``retrieve_secret``) -- always wins;
2. ``SLM_HMAC_API_KEY_SECRET`` from the environment, imported into the store
   ONCE when the store holds no value (a migration of an existing value);
3. neither: ``None``. Callers fail closed for new keys.

Nothing here generates, seeds or rotates a value: creating the pepper is a human
action (the secrets page). The value is never logged.

Rotation limitation: ``SystemSecret`` keeps a single value, with no previous
one, so there is no dual-verify window. See
``autobot-slm-backend/docs/api-key-pepper.md``.

Own session (#19117 review): ``system_secrets`` exists only in the main SLM
database, while ``APIKeyService`` runs on the ``slm_users`` session. The resolver
therefore opens its own session on the main DB (``db_service.session()``, as SCIM's
``_load_scim_token`` does) and never takes the caller's.

The result is cached per process for ``SLM_AUTH_LOOKUP_CACHE_TTL`` seconds and
dropped at once when the secret is written through the secrets page
(``invalidate_pepper_cache``); other workers pick a change up within the TTL. The
"unset" WARNING is emitted at most once per TTL.

Stdlib logging, deliberately: the SLM test harness mocks ``config``
(see ``generated_system_secrets.py``).
"""

from __future__ import annotations

import logging
import os
import time

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

#: ``SystemSecret.key`` the operator sets on the secrets page.
HMAC_PEPPER_KEY = "slm_hmac_api_key_secret"  # nosec B105  # key name, not a credential
HMAC_PEPPER_DESCRIPTION = "Pepper for API-key hashing (#19120). Required to create API keys."
SECRETS_PAGE_PATH = "/slm/settings/admin/secrets"

#: Seconds a resolved (or unset) pepper is reused by this process.
PEPPER_CACHE_TTL_SECONDS = float(os.getenv("SLM_AUTH_LOOKUP_CACHE_TTL", "60"))

WARN_UNCONFIGURED = (
    "API-key pepper is not configured: add the secret '%s' on the SLM page %s "
    "(or set SLM_HMAC_API_KEY_SECRET once, to be imported). New API keys cannot be "
    "created and existing keys are not re-hashed until it is set."
)

# (expires_at monotonic, value-or-None); None value = cached "unset".
_cache: tuple[float, str | None] | None = None
_last_warned: float | None = None


def invalidate_pepper_cache() -> None:
    """Forget the cached pepper (call after the secret is written or deleted)."""
    global _cache, _last_warned
    _cache = None
    _last_warned = None


def _warn_unconfigured_once() -> None:
    global _last_warned
    now = time.monotonic()
    if _last_warned is None or now - _last_warned >= PEPPER_CACHE_TTL_SECONDS:
        _last_warned = now
        logger.warning(WARN_UNCONFIGURED, HMAC_PEPPER_KEY, SECRETS_PAGE_PATH)


async def resolve_hmac_api_key_secret() -> str | None:
    """Return the pepper (store first, else one-time env import), or ``None``."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now < _cache[0]:
        value = _cache[1]
    else:
        value = await _resolve_uncached()
        _cache = (now + PEPPER_CACHE_TTL_SECONDS, value)
    if value is None:
        _warn_unconfigured_once()
    return value


async def _resolve_uncached() -> str | None:
    """Read the main-DB store; import the env value once when the store is empty."""
    from config import settings
    from services.database import db_service
    from services.system_secrets_vault import retrieve_secret

    async with db_service.session() as db:
        stored = await retrieve_secret(db, HMAC_PEPPER_KEY)
        if stored:
            return stored
        env_value = settings.hmac_api_key_secret
        if not env_value:
            return None
        if not await _insert_env_value(db, env_value):
            # Lost the race: the operator's (or another worker's) value is authoritative.
            return await retrieve_secret(db, HMAC_PEPPER_KEY)
    await _after_import(env_value)
    return env_value


async def _insert_env_value(db, value: str) -> bool:
    """Insert and commit the env value; ``False`` when a row already exists."""
    from models.database import SystemSecret
    from services.encryption import encrypt_data

    row = SystemSecret(
        key=HMAC_PEPPER_KEY,
        encrypted_value=encrypt_data(value),
        category="system",
        description=HMAC_PEPPER_DESCRIPTION,
    )
    try:
        async with db.begin_nested():
            db.add(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.info("api-key-pepper: store already holds %s; import skipped", HMAC_PEPPER_KEY)
        return False
    return True


async def _after_import(value: str) -> None:
    """Vault mirror and audit line, only once the row is committed."""
    from services.system_secrets_vault import mirror_secret_to_vault

    await mirror_secret_to_vault(HMAC_PEPPER_KEY, value)
    logger.info(
        "AUDIT api-key-pepper: imported SLM_HMAC_API_KEY_SECRET from env into secret '%s' "
        "(one-time import; value not logged)",
        HMAC_PEPPER_KEY,
    )
