# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add node_capability_profiles table (#15495).

One row per node, upserted from its heartbeat's extra_data
(services/node_capability.py) -- SLM's per-node LLM hardware capability
profile (total RAM, total VRAM, GPU present/model, NPU present, free disk on
the model directory). Reversible: DROP TABLE removes it cleanly, since
nothing else depends on it beyond its own FK to nodes(node_id).
"""

import logging
import sys

from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add node_capability_profiles table (#15495)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if table_exists(cursor, "node_capability_profiles"):
        logger.info("node_capability_profiles table already exists")
        conn.close()
        return

    if not table_exists(cursor, "nodes"):
        logger.error("nodes table does not exist. Database may not be initialized.")
        conn.close()
        return

    logger.info("Creating node_capability_profiles table...")
    cursor.execute("""
        CREATE TABLE node_capability_profiles (
            node_id VARCHAR(64) PRIMARY KEY REFERENCES nodes(node_id) ON DELETE CASCADE,
            total_ram_mb INTEGER,
            total_vram_mb INTEGER,
            gpu_present BOOLEAN,
            gpu_model VARCHAR(255),
            npu_present BOOLEAN,
            free_disk_model_dir_mb INTEGER,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Created node_capability_profiles table")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
