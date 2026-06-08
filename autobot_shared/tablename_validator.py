# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tablename collision detection utility (#2413).

Provides :func:`check_tablename_collisions` — a standalone, importable function
that detects overlapping ``__tablename__`` values across two independent
SQLAlchemy ``MetaData`` objects.

This was extracted from ``autobot-slm-backend/main._check_tablename_collisions``
so the logic can be tested directly without importing the full SLM application
stack (which carries heavy transitive imports: FastAPI routers, SQLAlchemy
models, all services, etc.).

See also: GitHub issues #1878 (original incident), #2226 (test added), #2413 (extraction).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def check_tablename_collisions(slm_metadata: Any, um_metadata: Any) -> None:
    """Detect shared tablenames across two SQLAlchemy MetaData objects (#1878).

    The SLM backend uses two independent ``DeclarativeBase`` subclasses that each
    target a **different** PostgreSQL database:

    * ``models.database.Base`` — SLM admin models (nodes, deployments, …)
      → connects to the main SLM database (``settings.database_url``)
    * ``user_management.models.base.Base`` — User management models (users, roles, …)
      → connects to the ``slm_users`` database (``SLM_USERS_DATABASE_URL``)

    Because each Base has its own ``MetaData`` object, SQLAlchemy cannot enforce
    cross-Base uniqueness.  A developer who accidentally assigns the same
    ``__tablename__`` to models from both bases will get no compile-time error; the
    table will simply be created in the wrong database and FK references will silently
    break, exactly as happened with the ``users`` / ``slm_users`` incident (#1854).

    This function logs a WARNING for every overlapping tablename so that such
    regressions are surfaced immediately at startup rather than discovered later via
    mysterious query failures.

    Note: This does NOT raise because several names (e.g. ``roles``, ``audit_logs``)
    are intentionally shared between the two databases for independent domain purposes.
    The warning is the signal; renaming is the developer's responsibility.

    Args:
        slm_metadata: The ``MetaData`` object from the SLM ``DeclarativeBase``
            (e.g. ``models.database.Base.metadata``).
        um_metadata: The ``MetaData`` object from the UserManagement ``DeclarativeBase``
            (e.g. ``user_management.models.base.Base.metadata``).
    """
    slm_tables: set[str] = set(slm_metadata.tables.keys())
    um_tables: set[str] = set(um_metadata.tables.keys())
    collisions: set[str] = slm_tables & um_tables

    if collisions:
        sorted_names = sorted(collisions)
        logger.warning(
            "Tablename overlap detected between SLM Base and UserManagement Base — "
            "%d shared name(s): %s. "
            "These names refer to tables in different databases, but sharing names "
            "increases the risk of future model misplacement. "
            "See GitHub issue #1878.",
            len(sorted_names),
            sorted_names,
        )
    else:
        logger.info(
            "Tablename collision check passed — %d SLM tables, %d UM tables, 0 shared names",
            len(slm_tables),
            len(um_tables),
        )
