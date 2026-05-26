# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration Runner - Automatic database schema updates.

This module provides automatic migration running on SLM server startup.
Migrations are tracked in a `migrations_applied` table to prevent re-running.
Uses PostgreSQL for all database operations (Issue #786).

Usage:
    # Run all pending migrations
    python3 -m migrations.runner

    # Or import and call
    from migrations.runner import run_migrations
    await run_migrations()
"""

import importlib
import logging
import sys
from datetime import datetime, timezone
from typing import List, Tuple

import psycopg2

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
    "add_external_agents",
    "fix_services_memory_bytes_bigint",
    "add_role_metadata_fields",
    "widen_code_status_column",
    "add_fleet_sync_jobs_table",
    # Issue #1854: rename SLM admin table to avoid FK collision with
    # user_management users table (UUID PK).
    "rename_users_to_slm_users",
    # Issue #1900: consolidate slm_users (integer PK) into users (UUID PK)
    # and drop the now-orphaned slm_users table.
    "consolidate_slm_users_to_uuid",
    # Issue #1814: add ansible_name column for proper Ansible targeting
    "add_node_ansible_name",
    # Issue #2011: add unique constraint on ansible_name
    "add_ansible_name_unique_constraint",
    # Issue #1980: add failure_reason column to fleet_sync_jobs
    "add_failure_reason_to_fleet_sync_jobs",
    # Issue #5385: convert all TIMESTAMP columns to TIMESTAMPTZ (UTC-aware)
    "migrate_timestamps_to_timestamptz",
]


def get_db_url() -> str:
    """Get PostgreSQL database URL from environment or config (#786, #2293)."""
    import os

    # 1. Check environment variable first (set by systemd EnvironmentFile
    #    or Ansible environment: block)
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url.replace("postgresql+asyncpg://", "postgresql://")

    # 2. Try loading from credentials env file directly (#2293)
    creds_file = "/etc/autobot/db-credentials.env"
    if os.path.isfile(creds_file):
        with open(creds_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return url.replace("postgresql+asyncpg://", "postgresql://")

    # 3. Fall back to config module
    from config import settings

    url = settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _parse_db_url(url: str) -> dict:
    """Parse PostgreSQL URL into connection parameters (#786)."""
    # postgresql://user:pass@host:port/database
    # postgresql://user@host:port/database (no password)
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") if parsed.path else "slm",
        "user": parsed.username or "slm_app",
        "password": parsed.password,
    }


def get_connection(db_url: str = None, timeout: int = 10) -> psycopg2.extensions.connection:
    """Get a PostgreSQL connection (#786).

    Args:
        db_url: Database URL (defaults to get_db_url())
        timeout: Connection timeout in seconds (default 10s)
    """
    if db_url is None:
        db_url = get_db_url()
    params = _parse_db_url(db_url)
    # Remove None password to use peer auth if available
    if params["password"] is None:
        del params["password"]
    # Add timeout to prevent indefinite hangs during startup
    params["connect_timeout"] = timeout
    return psycopg2.connect(**params)


def ensure_migrations_table(conn: psycopg2.extensions.connection) -> None:
    """Create migrations tracking table if it doesn't exist (#786, #5515)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS migrations_applied (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Upgrade existing deployments that have the old TIMESTAMP column (#5515)
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'migrations_applied'
                      AND column_name = 'applied_at'
                      AND data_type = 'timestamp without time zone'
                ) THEN
                    ALTER TABLE migrations_applied
                        ALTER COLUMN applied_at TYPE TIMESTAMPTZ
                        USING applied_at AT TIME ZONE 'UTC';
                END IF;
            END
            $$;
        """)
    conn.commit()


def get_applied_migrations(conn: psycopg2.extensions.connection) -> List[str]:
    """Get list of already applied migration names (#786)."""
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM migrations_applied ORDER BY id")
        return [row[0] for row in cur.fetchall()]


def mark_migration_applied(conn: psycopg2.extensions.connection, name: str) -> None:
    """Mark a migration as applied (#786)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO migrations_applied (name, applied_at) VALUES (%s, %s)",
            (name, datetime.now(timezone.utc)),
        )
    conn.commit()


def run_migration(db_url: str, name: str) -> Tuple[bool, str]:
    """
    Run a single migration by name (#786).

    Args:
        db_url: PostgreSQL connection URL
        name: Migration module name

    Returns:
        Tuple of (success, message)
    """
    try:
        # Import the migration module
        module = importlib.import_module(f"migrations.{name}")

        # Check if it has a migrate() function (passes db_url)
        if hasattr(module, "migrate"):
            module.migrate(db_url)
            return True, f"Applied migration: {name}"
        elif hasattr(module, "run"):
            module.run(db_url)
            return True, f"Applied migration: {name}"
        else:
            # Some migrations might just be seed scripts
            return True, f"Loaded migration: {name} (no migrate function)"

    except Exception as e:
        return False, f"Failed to apply {name}: {e}"


def run_all_migrations(db_url: str = None) -> List[Tuple[str, bool, str]]:
    """
    Run all pending migrations (#786).

    Returns:
        List of (migration_name, success, message) tuples
    """
    if db_url is None:
        db_url = get_db_url()

    results = []
    conn = None

    try:
        logger.debug("Connecting to PostgreSQL for migrations")
        conn = get_connection(db_url)
        logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to connect to database after 10s timeout: %s", e)
        logger.error("Check that PostgreSQL is running and accepting connections on the configured host/port")
        return [("database_connection", False, f"Connection failed: {e}")]

    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)

        pending = [m for m in MIGRATIONS if m not in applied]

        if not pending:
            logger.info("No pending migrations")
            return results

        logger.info("Running %d pending migration(s)", len(pending))

        for migration_name in pending:
            success, message = run_migration(db_url, migration_name)
            results.append((migration_name, success, message))

            if success:
                mark_migration_applied(conn, migration_name)
                logger.info(message)
            else:
                logger.error(message)
                # Stop on first failure
                break

    except Exception as e:
        logger.error("Migration execution failed: %s", e)
        if results == []:
            results.append(("migrations_execution", False, f"Execution error: {e}"))
    finally:
        if conn:
            conn.close()

    return results


def check_schema_sync(db_url: str = None) -> Tuple[bool, List[str]]:
    """
    Check if schema is in sync (no pending migrations) (#786).

    Returns:
        Tuple of (is_synced, pending_migrations)
    """
    if db_url is None:
        db_url = get_db_url()

    conn = get_connection(db_url)
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        pending = [m for m in MIGRATIONS if m not in applied]
        return len(pending) == 0, pending
    finally:
        conn.close()


# Async wrapper for use with FastAPI startup
async def run_migrations_async(db_url: str = None) -> List[Tuple[str, bool, str]]:
    """Async wrapper for run_all_migrations (#786)."""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_all_migrations, db_url)


if __name__ == "__main__":
    # Allow running directly: python3 -m migrations.runner
    logging.basicConfig(level=logging.INFO)

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info(f"Running migrations on PostgreSQL: {db_url}")

    results = run_all_migrations(db_url)

    if results:
        logger.info("\nMigration Results:")
        for name, success, message in results:
            status = "✓" if success else "✗"
            logger.info(f"  {status} {message}")
    else:
        logger.info("No migrations to run")
