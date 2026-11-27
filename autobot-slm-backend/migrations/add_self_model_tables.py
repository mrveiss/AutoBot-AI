# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add the self-model tables self_model_entities and self_model_history (#22277).

SLM Postgres is the system of record of the connected self-model. Nothing is ever deleted from either
table. Reversible by removing the two tables; nothing else references them.
"""

import logging
import sys

from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import redact_url_credentials
from migrations.utils import get_connection, table_exists

logger = get_logger(__name__)

_ENTITIES_DDL = """
    CREATE TABLE self_model_entities (
        id BIGSERIAL PRIMARY KEY,
        entity_key VARCHAR(512) NOT NULL UNIQUE,
        kind VARCHAR(16) NOT NULL,
        name VARCHAR(255) NOT NULL,
        parent_key VARCHAR(512),
        node_id VARCHAR(64) REFERENCES nodes(node_id) ON DELETE SET NULL,
        status VARCHAR(16) NOT NULL,
        version VARCHAR(128),
        first_seen TIMESTAMPTZ NOT NULL,
        last_seen TIMESTAMPTZ NOT NULL,
        removed_at TIMESTAMPTZ,
        attrs JSONB NOT NULL DEFAULT '{}'::jsonb
    )
"""

_HISTORY_DDL = """
    CREATE TABLE self_model_history (
        id BIGSERIAL PRIMARY KEY,
        entity_key VARCHAR(512) NOT NULL,
        event VARCHAR(24) NOT NULL,
        old_status VARCHAR(16),
        new_status VARCHAR(16),
        old_version VARCHAR(128),
        new_version VARCHAR(128),
        observed_at TIMESTAMPTZ NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX ix_self_model_entities_kind_status ON self_model_entities (kind, status)",
    "CREATE INDEX ix_self_model_entities_node_id ON self_model_entities (node_id)",
    "CREATE INDEX ix_self_model_entities_parent_key ON self_model_entities (parent_key)",
    "CREATE INDEX ix_self_model_history_entity_key ON self_model_history (entity_key, id)",
)


def migrate(db_url: str) -> None:
    """Create the self-model tables (#22277)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if table_exists(cursor, "self_model_entities"):
        logger.info("self_model_entities table already exists")
        conn.close()
        return

    if not table_exists(cursor, "nodes"):
        logger.error("nodes table does not exist. Database may not be initialized.")
        conn.close()
        return

    logger.info("Creating self_model_entities and self_model_history tables...")
    for statement in (_ENTITIES_DDL, _HISTORY_DDL, *_INDEXES):
        cursor.execute(statement)

    conn.commit()
    conn.close()
    logger.info("Created the self-model tables")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", redact_url_credentials(db_url))
    migrate(db_url)
