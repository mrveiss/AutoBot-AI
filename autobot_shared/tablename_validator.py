# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tablename collision detection utility (#2413).

Provides :func:`check_tablename_collisions` — a standalone, importable function
that detects overlapping ``__tablename__`` values across two independent
SQLAlchemy ``MetaData`` objects.

This was extracted from ``autobot-slm-backend/main._check_tablename_collisions``
so the logic can be tested directly without importing the full SLM application
stack (which carries heavy transitive imports: FastAPI routers, SQLAlchemy
models, all services, etc.).

See also: GitHub issues #1878 (original incident), #2226 (test added), #2413 (extraction),
#10764 (audit_logs collision fixed by renaming SLM node table to slm_node_audit_logs),
#10862 (promote WARNING to RAISE for unallowlisted collisions).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tablenames that are intentionally shared across the SLM Base and the
# UserManagement Base.  Both bases target DIFFERENT PostgreSQL databases
# (``slm`` vs ``slm_users``), so these names refer to independent tables — not
# a single table written to two schemas.  Sharing a name is still undesirable
# (it risks confusion and future misplacement), so allowlisted collisions are
# logged at WARNING rather than silently ignored.
#
# History:
#   "roles"     — SLM admin roles (models.database.Role → slm DB) and UM roles
#                 (user_management.models.role.Role → slm_users DB) have always
#                 had the same tablename.  The tables serve the same conceptual
#                 domain in their respective databases and the overlap is tracked.
#                 Added to allowlist at #10862.
#   "audit_logs" — was shared until #10764 renamed the SLM node table to
#                  slm_node_audit_logs, removing the collision.  Do NOT re-add.
INTENTIONALLY_SHARED_TABLENAMES: frozenset[str] = frozenset(
    {
        "roles",  # SLM admin roles (slm DB) vs UM roles (slm_users DB) — see #10862
    }
)


class TableNameCollisionError(RuntimeError):
    """Raised when a cross-Base ``__tablename__`` collision is detected (#10862).

    This indicates that a tablename is present in both the SLM ``DeclarativeBase``
    registry and the UserManagement ``DeclarativeBase`` registry, and the name is
    **not** in :data:`INTENTIONALLY_SHARED_TABLENAMES`.

    Because each Base binds to a different PostgreSQL database, SQLAlchemy cannot
    enforce uniqueness at the ORM level.  A collision that is not in the allowlist
    is almost certainly a developer error — either the wrong Base was used, or the
    same table was accidentally modeled twice.  The application must not start in
    this state.
    """


def check_tablename_collisions(slm_metadata: Any, um_metadata: Any) -> None:
    """Detect shared tablenames across two SQLAlchemy MetaData objects (#1878, #10862).

    The SLM backend uses two independent ``DeclarativeBase`` subclasses that each
    target a **different** PostgreSQL database:

    * ``models.database.Base`` — SLM admin models (nodes, deployments, …)
      → connects to the main SLM database (``settings.database_url``)
    * ``user_management.models.base.Base`` — User management models (users, roles, …)
      → connects to the ``slm_users`` database (``SLM_USERS_DATABASE_URL``)

    Because each Base has its own ``MetaData`` object, SQLAlchemy cannot enforce
    cross-Base uniqueness.  A developer who accidentally assigns the same
    ``__tablename__`` to models from both bases will get no compile-time error; the
    table will simply be created in the wrong database and FK references will
    silently break.

    **Behaviour (as of #10862):**

    * Collisions whose name is in :data:`INTENTIONALLY_SHARED_TABLENAMES` are
      logged at WARNING — these are tracked duplicates that are known to be
      intentional (different tables in different databases with the same name).
    * Collisions NOT in the allowlist **raise** :exc:`TableNameCollisionError`
      immediately.  This terminates startup so the regression is caught in CI
      and never reaches production.

    Args:
        slm_metadata: The ``MetaData`` object from the SLM ``DeclarativeBase``
            (e.g. ``models.database.Base.metadata``).
        um_metadata: The ``MetaData`` object from the UserManagement ``DeclarativeBase``
            (e.g. ``user_management.models.base.Base.metadata``).

    Raises:
        TableNameCollisionError: If any tablename overlap is found that is not
            listed in :data:`INTENTIONALLY_SHARED_TABLENAMES`.
    """
    slm_tables: set[str] = set(slm_metadata.tables.keys())
    um_tables: set[str] = set(um_metadata.tables.keys())
    collisions: set[str] = slm_tables & um_tables

    if not collisions:
        logger.info(
            "Tablename collision check passed — %d SLM tables, %d UM tables, 0 shared names",
            len(slm_tables),
            len(um_tables),
        )
        return

    allowlisted = collisions & INTENTIONALLY_SHARED_TABLENAMES
    unallowlisted = collisions - INTENTIONALLY_SHARED_TABLENAMES

    if allowlisted:
        logger.warning(
            "Tablename overlap detected between SLM Base and UserManagement Base — "
            "%d allowlisted shared name(s): %s. "
            "These names exist in INTENTIONALLY_SHARED_TABLENAMES because each "
            "Base targets a different PostgreSQL database. "
            "The tables are independent; this warning is a reminder to keep the "
            "allowlist current. See GitHub issues #1878, #10862.",
            len(sorted(allowlisted)),
            sorted(allowlisted),
        )

    if unallowlisted:
        sorted_names = sorted(unallowlisted)
        raise TableNameCollisionError(
            f"Cross-Base tablename collision(s) detected — {len(sorted_names)} "
            f"unallowlisted shared name(s): {sorted_names}. "
            f"The SLM Base (slm DB) and UserManagement Base (slm_users DB) must "
            f"not share tablenames unless the overlap is intentional and recorded "
            f"in INTENTIONALLY_SHARED_TABLENAMES. "
            f"This was the root cause of #10764 (audit_logs). "
            f"Fix: rename the table in the correct Base or add the name to the "
            f"allowlist with a justifying comment. See GitHub issue #10862."
        )
