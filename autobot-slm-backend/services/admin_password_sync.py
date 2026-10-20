# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep the SLM admin password in step with SLM_ADMIN_PASSWORD, revoking older sessions (#18672).

Startup re-synced the hash from the secrets file on every start and recorded no password
epoch, so a token issued before an admin password change stayed valid until it expired.
The API path (UserService.change_password) already records the epoch (#12924); this does
the same, and only when the password actually changed -- not on every start.
"""

import logging

from autobot_shared.auth.jwt_core import verify_password
from autobot_shared.user_management.password_epoch import set_password_epoch
from services.auth import auth_service

# Stdlib logging, as in the other SLM services: the SLM test conftest mocks config, which
# autobot_shared.logging_manager reads at import (CLAUDE.md's stated exception).
logger = logging.getLogger(__name__)


class EpochNotRecordedError(RuntimeError):
    """The password epoch could not be recorded, so the password was left unchanged (#18672)."""


async def sync_admin_password(db, user, password: str) -> bool:
    """Rehash *user* to *password* if it differs and revoke earlier tokens; True if changed."""
    if user.password_hash and verify_password(password, user.password_hash):
        return False
    # The epoch lives in the SLM database and the hash in slm_users: two transactions. Record the
    # epoch FIRST and refuse to change the password if it did not land -- fail closed (#18672).
    if await set_password_epoch(user.username) is None:
        raise EpochNotRecordedError(f"password epoch not recorded for {user.username!r}; admin password left unchanged")
    user.password_hash = auth_service.hash_password(password)
    await db.flush()
    logger.info("Admin password synced from SLM_ADMIN_PASSWORD; sessions issued before it are revoked")
    return True


async def sync_admin_password_at_startup(db, user, password: str) -> bool:
    """`sync_admin_password` for SLM startup: an epoch-store outage must not abort the boot (#18672).

    The fail-closed contract is to leave the password unchanged when the epoch cannot be
    recorded -- not to stop the whole SLM. Log it critical and carry on with the old hash.
    """
    try:
        return await sync_admin_password(db, user, password)
    except EpochNotRecordedError as exc:
        logger.critical("Admin password not synced from SLM_ADMIN_PASSWORD at startup: %s", exc)
        return False
