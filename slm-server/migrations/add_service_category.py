# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add category column to services table

Adds the 'category' column and auto-categorizes existing services
based on naming patterns.

Run: python migrations/add_service_category.py
"""

import logging
import re
import sqlite3
import sys
from pathlib import Path

# Configure logging for CLI execution
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

# Patterns for AutoBot services (same as service_categorizer.py)
AUTOBOT_PATTERNS = [
    r"^autobot",
    r"^slm-",
    r"^redis",
    r"^nginx$",
    r"^postgresql",
    r"^chromadb",
    r"^ollama",
    r"^uvicorn",
    r"^gunicorn",
    r"^celery",
    r"^docker",
    r"^containerd",
    r"^podman",
    r"^openvino",
    r"^tensorrt",
    r"^triton",
    r"^rabbitmq",
    r"^kafka",
    r"^prometheus",
    r"^grafana",
    r"^node.exporter",
    r"^playwright",
    r"^puppeteer",
    r"autobot",
    r"slm",
]


def categorize_service(service_name: str) -> str:
    """Determine category for a service."""
    # Python 3.8 compatible - removesuffix requires 3.9+
    suffix = ".service"
    if service_name.endswith(suffix):
        name = service_name[: -len(suffix)]
    else:
        name = service_name
    for pattern in AUTOBOT_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return "autobot"
    return "system"


def migrate(db_path: str) -> None:
    """Run the migration."""
    logger.info("Running migration on: %s", db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(services)")
    columns = [col[1] for col in cursor.fetchall()]

    if "category" in columns:
        logger.info("Column 'category' already exists. Updating existing NULL values...")
    else:
        logger.info("Adding 'category' column to services table...")
        cursor.execute(
            "ALTER TABLE services ADD COLUMN category VARCHAR(20) DEFAULT 'system'"
        )
        logger.info("Column added successfully.")

    # Get all services and update categories
    logger.info("Auto-categorizing existing services...")
    cursor.execute("SELECT id, service_name FROM services")
    services = cursor.fetchall()

    autobot_count = 0
    system_count = 0

    for service_id, service_name in services:
        category = categorize_service(service_name)
        cursor.execute(
            "UPDATE services SET category = ? WHERE id = ?",
            (category, service_id),
        )
        if category == "autobot":
            autobot_count += 1
        else:
            system_count += 1

    conn.commit()
    conn.close()

    logger.info("Migration complete!")
    logger.info("  AutoBot services: %d", autobot_count)
    logger.info("  System services: %d", system_count)


if __name__ == "__main__":
    # Default database path
    db_path = Path(__file__).parent.parent / "data" / "slm.db"

    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    migrate(str(db_path))
