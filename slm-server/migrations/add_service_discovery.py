# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add service discovery, node config, and service conflicts (Issue #760)

Adds:
- Discovery fields to services table (port, protocol, endpoint_path, is_discoverable)
- node_configs table for per-node configuration
- service_conflicts table for incompatible services

Updated for PostgreSQL (Issue #786).

Run: python migrations/add_service_discovery.py
"""

import logging
import sys

import psycopg2

from migrations.utils import (
    add_column_if_not_exists,
    create_index_if_not_exists,
    get_connection,
    table_exists,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Known service conflicts to seed
KNOWN_CONFLICTS = [
    ("redis-server", "redis-stack-server", "Both bind to port 6379", "port"),
    ("apache2", "nginx", "Both bind to port 80/443", "port"),
    ("mysql-server", "mariadb-server", "Both bind to port 3306", "port"),
    ("postgresql-14", "postgresql-15", "Data directory conflicts", "resource"),
    ("docker", "podman", "Container runtime conflicts", "dependency"),
]

# Default service ports for auto-population
SERVICE_DEFAULTS = {
    "autobot-backend": {"port": 8001, "protocol": "http", "endpoint_path": "/api"},
    "autobot-frontend": {"port": 5173, "protocol": "http", "endpoint_path": "/"},
    "redis-server": {"port": 6379, "protocol": "redis", "endpoint_path": None},
    "redis-stack-server": {"port": 6379, "protocol": "redis", "endpoint_path": None},
    "slm-agent": {"port": 8000, "protocol": "http", "endpoint_path": "/api"},
    "slm-backend": {"port": 8000, "protocol": "http", "endpoint_path": "/api"},
    "ollama": {"port": 11434, "protocol": "http", "endpoint_path": "/api"},
    "playwright-server": {"port": 3000, "protocol": "http", "endpoint_path": None},
    "grafana-server": {"port": 3000, "protocol": "http", "endpoint_path": "/"},
    "prometheus": {"port": 9090, "protocol": "http", "endpoint_path": "/"},
}


def migrate(db_url: str) -> None:
    """Run the migration (#786)."""
    logger.info("Running service discovery migration")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    # 1. Add discovery columns to services table
    logger.info("Adding discovery columns to services table...")
    added = []
    if add_column_if_not_exists(cursor, "services", "port", "INTEGER"):
        added.append("port")
    if add_column_if_not_exists(
        cursor, "services", "protocol", "VARCHAR(10) DEFAULT 'http'"
    ):
        added.append("protocol")
    if add_column_if_not_exists(cursor, "services", "endpoint_path", "VARCHAR(256)"):
        added.append("endpoint_path")
    if add_column_if_not_exists(
        cursor, "services", "is_discoverable", "BOOLEAN DEFAULT TRUE"
    ):
        added.append("is_discoverable")

    if added:
        logger.info("  Added columns: %s", ", ".join(added))
    else:
        logger.info("  All columns already exist")

    # 2. Create node_configs table
    logger.info("Creating node_configs table...")
    if not table_exists(cursor, "node_configs"):
        cursor.execute(
            """
            CREATE TABLE node_configs (
                id SERIAL PRIMARY KEY,
                node_id VARCHAR(64),
                config_key VARCHAR(128) NOT NULL,
                config_value TEXT,
                value_type VARCHAR(20) DEFAULT 'string',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(node_id, config_key)
            )
        """
        )
    create_index_if_not_exists(
        cursor, "ix_node_configs_node_id", "node_configs", "node_id"
    )
    create_index_if_not_exists(
        cursor, "ix_node_configs_key", "node_configs", "config_key"
    )

    # 3. Create service_conflicts table
    logger.info("Creating service_conflicts table...")
    if not table_exists(cursor, "service_conflicts"):
        cursor.execute(
            """
            CREATE TABLE service_conflicts (
                id SERIAL PRIMARY KEY,
                service_name_a VARCHAR(128) NOT NULL,
                service_name_b VARCHAR(128) NOT NULL,
                reason TEXT,
                conflict_type VARCHAR(32) DEFAULT 'port',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(service_name_a, service_name_b)
            )
        """
        )
    create_index_if_not_exists(
        cursor, "ix_service_conflicts_a", "service_conflicts", "service_name_a"
    )
    create_index_if_not_exists(
        cursor, "ix_service_conflicts_b", "service_conflicts", "service_name_b"
    )

    # 4. Seed known conflicts
    logger.info("Seeding known service conflicts...")
    conflict_count = 0
    for service_a, service_b, reason, conflict_type in KNOWN_CONFLICTS:
        try:
            cursor.execute(
                """INSERT INTO service_conflicts
                   (service_name_a, service_name_b, reason, conflict_type)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (service_a, service_b, reason, conflict_type),
            )
            if cursor.rowcount > 0:
                conflict_count += 1
        except psycopg2.IntegrityError:
            conn.rollback()  # Required for PostgreSQL after constraint violation

    logger.info("  Seeded %d conflicts", conflict_count)

    # 5. Auto-populate service discovery fields for known services
    logger.info("Auto-populating discovery fields for known services...")
    updated_count = 0
    for service_name, defaults in SERVICE_DEFAULTS.items():
        cursor.execute(
            """UPDATE services
               SET port = COALESCE(port, %s),
                   protocol = COALESCE(protocol, %s),
                   endpoint_path = COALESCE(endpoint_path, %s)
               WHERE service_name = %s AND port IS NULL""",
            (
                defaults["port"],
                defaults["protocol"],
                defaults["endpoint_path"],
                service_name,
            ),
        )
        updated_count += cursor.rowcount

    logger.info("  Updated %d service records", updated_count)

    conn.commit()
    conn.close()

    logger.info("Migration complete!")


if __name__ == "__main__":
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)
