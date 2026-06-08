# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add unique constraint on nodes.ansible_name (#2011).

Prevents two nodes from sharing the same ansible_name, which would
cause silent misrouting of Ansible --limit targeting.

NULL values are permitted (not all nodes have an ansible_name set),
and PostgreSQL's partial unique index correctly allows multiple NULLs.
"""

import logging

from migrations.utils import get_connection, index_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add unique index on nodes.ansible_name (#2011)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    index_name = "uq_nodes_ansible_name"
    if not index_exists(cursor, index_name):
        cursor.execute(
            "CREATE UNIQUE INDEX uq_nodes_ansible_name" " ON nodes (ansible_name)" " WHERE ansible_name IS NOT NULL"
        )
        logger.info(
            "Migration: created unique index %s on nodes.ansible_name",
            index_name,
        )
    else:
        logger.info("Migration: index %s already exists, skipping", index_name)

    conn.commit()
    conn.close()
