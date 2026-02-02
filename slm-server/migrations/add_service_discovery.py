# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add service discovery, node config, and service conflicts (Issue #760)

Adds:
- Discovery fields to services table (port, protocol, endpoint_path, is_discoverable)
- node_configs table for per-node configuration
- service_conflicts table for incompatible services

Run: python migrations/add_service_discovery.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

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


def add_column_if_not_exists(
    cursor: sqlite3.Cursor, table: str, column: str, column_def: str
) -> bool:
    """Add column if it doesn't exist. Returns True if added."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [col[1] for col in cursor.fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
        return True
    return False


def migrate(db_path: str) -> None:
    """Run the migration."""
    logger.info("Running service discovery migration on: %s", db_path)

    conn = sqlite3.connect(db_path)
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
        cursor, "services", "is_discoverable", "BOOLEAN DEFAULT 1"
    ):
        added.append("is_discoverable")

    if added:
        logger.info("  Added columns: %s", ", ".join(added))
    else:
        logger.info("  All columns already exist")

    # 2. Create node_configs table
    logger.info("Creating node_configs table...")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS node_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_node_configs_node_id ON node_configs(node_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_node_configs_key ON node_configs(config_key)"
    )

    # 3. Create service_conflicts table
    logger.info("Creating service_conflicts table...")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS service_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name_a VARCHAR(128) NOT NULL,
            service_name_b VARCHAR(128) NOT NULL,
            reason TEXT,
            conflict_type VARCHAR(32) DEFAULT 'port',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(service_name_a, service_name_b)
        )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_service_conflicts_a ON service_conflicts(service_name_a)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_service_conflicts_b ON service_conflicts(service_name_b)"
    )

    # 4. Seed known conflicts
    logger.info("Seeding known service conflicts...")
    conflict_count = 0
    for service_a, service_b, reason, conflict_type in KNOWN_CONFLICTS:
        try:
            cursor.execute(
                """INSERT INTO service_conflicts
                   (service_name_a, service_name_b, reason, conflict_type)
                   VALUES (?, ?, ?, ?)""",
                (service_a, service_b, reason, conflict_type),
            )
            conflict_count += 1
        except sqlite3.IntegrityError:
            pass  # Already exists

    logger.info("  Seeded %d conflicts", conflict_count)

    # 5. Auto-populate service discovery fields for known services
    logger.info("Auto-populating discovery fields for known services...")
    updated_count = 0
    for service_name, defaults in SERVICE_DEFAULTS.items():
        cursor.execute(
            """UPDATE services
               SET port = COALESCE(port, ?),
                   protocol = COALESCE(protocol, ?),
                   endpoint_path = COALESCE(endpoint_path, ?)
               WHERE service_name = ? AND port IS NULL""",
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
    db_path = Path(__file__).parent.parent / "data" / "slm.db"

    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    migrate(str(db_path))
