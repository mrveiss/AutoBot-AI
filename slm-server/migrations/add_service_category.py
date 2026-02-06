# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add category column to services table

Adds the 'category' column and auto-categorizes existing services
based on naming patterns.
Updated for PostgreSQL (Issue #786).

Run: python migrations/add_service_category.py
"""

import logging
import re
import sys

from migrations.utils import add_column_if_not_exists, get_connection

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
    suffix = ".service"
    if service_name.endswith(suffix):
        name = service_name[: -len(suffix)]
    else:
        name = service_name
    for pattern in AUTOBOT_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return "autobot"
    return "system"


def migrate(db_url: str) -> None:
    """Run the migration (#786)."""
    logger.info("Running migration")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Add column if it doesn't exist
    added = add_column_if_not_exists(
        cursor, "services", "category", "VARCHAR(20) DEFAULT 'system'"
    )

    if not added:
        logger.info(
            "Column 'category' already exists. Updating existing NULL values..."
        )

    # Get all services and update categories
    logger.info("Auto-categorizing existing services...")
    cursor.execute("SELECT id, service_name FROM services")
    services = cursor.fetchall()

    autobot_count = 0
    system_count = 0

    for service_id, service_name in services:
        category = categorize_service(service_name)
        cursor.execute(
            "UPDATE services SET category = %s WHERE id = %s",
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
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)
