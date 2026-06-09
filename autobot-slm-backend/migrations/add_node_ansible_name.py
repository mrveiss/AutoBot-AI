# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add ansible_name column to nodes table (#1814).

The hostname column stores user-facing display names (e.g., '00-SLM-Manager')
which are unsuitable for Ansible --limit and SSH operations. This adds an
explicit ansible_name column for Ansible inventory host targeting, with
ip_address fallback for nodes where it is not set.
"""

import logging

from migrations.utils import add_column_if_not_exists, get_connection

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add ansible_name column to nodes table (#1814)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    add_column_if_not_exists(cursor, "nodes", "ansible_name", "VARCHAR(255)")

    conn.commit()
    conn.close()
    logger.info("Migration: added ansible_name column to nodes")
