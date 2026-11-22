# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE home of the ``secrets (owner_vault, name)`` uniqueness DDL (#17850).

Revision ``20261120_117`` and the app both call :func:`ensure_secret_unique_constraint`, so the constraint is
defined once and every update path (docker, ansible, code-sync) ends the same way: the constraint exists when
no duplicate group does, and the schema chain never fails because of duplicate credentials. Choosing which copy
survives is a person's decision, taken through the approval queue (#17038); this module never touches a row.

Takes a SYNC connection: the migration passes ``op.get_bind()``, the app passes
``await conn.run_sync(ensure_secret_unique_constraint)``.
"""

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from models.secret import SECRET_OWNER_VAULT_NAME_UNIQUE

logger = get_logger(__name__)

TABLE = "secrets"

#: How long the ALTER waits for its ACCESS EXCLUSIVE lock before giving up (the caller logs the timeout by type and
#: the next startup retries), so a long-running reader never stalls every query on ``secrets`` behind it.
LOCK_TIMEOUT_MS = env_int_clamped("AUTOBOT_SECRET_UNIQUE_LOCK_TIMEOUT_MS", 5000, 100, 60000)

#: Outcomes of :func:`ensure_secret_unique_constraint`.
CREATED, EXISTS, PENDING, SKIPPED = "created", "exists", "pending_duplicates", "skipped"

_DUPLICATE_GROUPS = (
    "SELECT count(*) FROM (SELECT 1 FROM secrets WHERE owner_vault IS NOT NULL "
    "GROUP BY owner_vault, name HAVING count(*) > 1) AS d"
)


def has_constraint(bind: Connection) -> bool:
    inspector = sa.inspect(bind)
    return SECRET_OWNER_VAULT_NAME_UNIQUE in {c["name"] for c in inspector.get_unique_constraints(TABLE)}


def ensure_secret_unique_constraint(bind: Connection) -> str:
    """Create the constraint iff it is missing and no duplicate group exists. Idempotent; touches no row.

    Returns ``CREATED``, ``EXISTS``, ``PENDING`` (duplicates remain: a loud counts-only warning, nothing
    changed) or ``SKIPPED`` (not PostgreSQL, or no ``secrets`` table).
    """
    if bind.dialect.name != "postgresql" or not sa.inspect(bind).has_table(TABLE):
        return SKIPPED
    if has_constraint(bind):
        return EXISTS
    groups = bind.execute(sa.text(_DUPLICATE_GROUPS)).scalar_one()
    if groups:
        logger.warning(
            "constraint %s NOT created: %d duplicated (owner_vault, name) secret group(s) remain; resolve them "
            "through the Approvals inbox (POST /api/admin/secret-duplicates/requests). The app creates the "
            "constraint once none remain",
            SECRET_OWNER_VAULT_NAME_UNIQUE,
            groups,
        )
        return PENDING
    bind.execute(sa.text(f"SET LOCAL lock_timeout = {int(LOCK_TIMEOUT_MS)}"))
    bind.execute(
        sa.text(f"ALTER TABLE {TABLE} ADD CONSTRAINT {SECRET_OWNER_VAULT_NAME_UNIQUE} UNIQUE (owner_vault, name)")
    )
    logger.info("constraint %s created", SECRET_OWNER_VAULT_NAME_UNIQUE)
    return CREATED
