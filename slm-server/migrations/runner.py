# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration Runner - Automatic database schema updates.

This module provides automatic migration running on SLM server startup.
Migrations are tracked in a `migrations_applied` table to prevent re-running.

Usage:
    # Run all pending migrations
    python3 -m migrations.runner

    # Or import and call
    from migrations.runner import run_migrations
    await run_migrations()
"""

import importlib
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Migration files in order of execution
# Add new migrations to this list
MIGRATIONS = [
    "add_ssh_columns",
    "add_services_table",
    "add_replications_table",
    "add_events_certificates_updates_tables",
    "001_add_health_monitoring_columns",
    "add_service_category",
    "add_node_credentials_table",
    "add_tls_columns",
    "add_code_version_columns",
    "add_service_discovery",
    "add_agents",
    "seed_agents",
    "add_error_resolution_fields",
]


def get_db_path() -> str:
    """Get database path from environment or default."""
    base_dir = Path(__file__).parent.parent
    return os.environ.get("SLM_DATABASE_PATH", str(base_dir / "data" / "slm.db"))


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create migrations tracking table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations_applied (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> List[str]:
    """Get list of already applied migration names."""
    cursor = conn.execute("SELECT name FROM migrations_applied ORDER BY id")
    return [row[0] for row in cursor.fetchall()]


def mark_migration_applied(conn: sqlite3.Connection, name: str) -> None:
    """Mark a migration as applied."""
    conn.execute(
        "INSERT INTO migrations_applied (name, applied_at) VALUES (?, ?)",
        (name, datetime.utcnow().isoformat()),
    )
    conn.commit()


def run_migration(db_path: str, name: str) -> Tuple[bool, str]:
    """
    Run a single migration by name.

    Args:
        db_path: Path to the SQLite database file
        name: Migration module name

    Returns:
        Tuple of (success, message)
    """
    try:
        # Import the migration module
        module = importlib.import_module(f"migrations.{name}")

        # Check if it has a migrate() function (passes db_path)
        if hasattr(module, "migrate"):
            module.migrate(db_path)
            return True, f"Applied migration: {name}"
        elif hasattr(module, "run"):
            module.run(db_path)
            return True, f"Applied migration: {name}"
        else:
            # Some migrations might just be seed scripts
            return True, f"Loaded migration: {name} (no migrate function)"

    except Exception as e:
        return False, f"Failed to apply {name}: {e}"


def run_all_migrations(db_path: str = None) -> List[Tuple[str, bool, str]]:
    """
    Run all pending migrations.

    Returns:
        List of (migration_name, success, message) tuples
    """
    if db_path is None:
        db_path = get_db_path()

    results = []

    # Ensure database directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)

        pending = [m for m in MIGRATIONS if m not in applied]

        if not pending:
            logger.info("No pending migrations")
            return results

        logger.info(f"Running {len(pending)} pending migration(s)")

        for migration_name in pending:
            success, message = run_migration(db_path, migration_name)
            results.append((migration_name, success, message))

            if success:
                mark_migration_applied(conn, migration_name)
                logger.info(message)
            else:
                logger.error(message)
                # Stop on first failure
                break

    finally:
        conn.close()

    return results


def check_schema_sync(db_path: str = None) -> Tuple[bool, List[str]]:
    """
    Check if schema is in sync (no pending migrations).

    Returns:
        Tuple of (is_synced, pending_migrations)
    """
    if db_path is None:
        db_path = get_db_path()

    if not Path(db_path).exists():
        return False, MIGRATIONS

    conn = sqlite3.connect(db_path)
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        pending = [m for m in MIGRATIONS if m not in applied]
        return len(pending) == 0, pending
    finally:
        conn.close()


# Async wrapper for use with FastAPI startup
async def run_migrations_async(db_path: str = None) -> List[Tuple[str, bool, str]]:
    """Async wrapper for run_all_migrations."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_all_migrations, db_path)


if __name__ == "__main__":
    # Allow running directly: python3 -m migrations.runner
    logging.basicConfig(level=logging.INFO)

    db_path = sys.argv[1] if len(sys.argv) > 1 else get_db_path()
    print(f"Running migrations on: {db_path}")

    results = run_all_migrations(db_path)

    if results:
        print("\nMigration Results:")
        for name, success, message in results:
            status = "✓" if success else "✗"
            print(f"  {status} {message}")
    else:
        print("No migrations to run")
