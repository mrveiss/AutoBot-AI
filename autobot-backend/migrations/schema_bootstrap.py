# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard for runtime schema creation (#10001 Phase C).

Historical startup ``metadata.create_all`` built fleet Postgres schemas with
no ``alembic_version`` stamp while the Ansible migration step silently
failed — the schema-without-provenance state that #10026 case 3 documents.
From Phase C on, Alembic migrations are the only schema authority for the
alembic-managed database; runtime ``create_all`` is permitted only for local
SQLite data files (app-owned, not migration-managed) or behind an explicit
opt-in for development profiles.

Every runtime ``metadata.create_all`` call site must invoke
:func:`ensure_create_all_allowed` first and be allowlisted in
tests/migrations/test_schema_authority.py.
"""

import os

CREATE_ALL_FLAG = "AUTOBOT_DB_CREATE_ALL"


def create_all_opted_in() -> bool:
    """True when the operator explicitly re-enabled runtime create_all."""
    return os.environ.get(CREATE_ALL_FLAG, "").lower() in ("1", "true", "yes")


def ensure_create_all_allowed(dialect_name: str) -> None:
    """Refuse runtime schema creation against migration-managed databases.

    Args:
        dialect_name: SQLAlchemy dialect of the engine about to create_all
            (e.g. ``engine.dialect.name``).

    Raises:
        RuntimeError: dialect is not SQLite and AUTOBOT_DB_CREATE_ALL is not
            set — production schemas must come from ``migrations.baseline`` +
            ``alembic upgrade head``.
    """
    if dialect_name == "sqlite":
        return
    if create_all_opted_in():
        return
    raise RuntimeError(
        f"Refusing runtime metadata.create_all against '{dialect_name}': this "
        "database is migration-managed and create_all leaves schema without an "
        "alembic_version stamp (#10001). Run 'python -m migrations.baseline' "
        "then 'alembic upgrade head', or set "
        f"{CREATE_ALL_FLAG}=true for development profiles only. "
        "See docs/operations/migration-recovery.md."
    )
