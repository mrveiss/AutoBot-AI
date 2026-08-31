# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from migrations import utils as _migration_utils

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
    # Issue #10764: rename the integer-PK SLM node audit table off 'audit_logs'
    # so the UUID/org-aware user_management model is the sole owner of that name.
    "rename_audit_logs_to_slm_node_audit_logs",
    # Issue #11303: per-component async drift/resolve job tracking table so job
    # status survives the SLM backend restarting itself during a self-resolve.
    "add_component_sync_jobs_table",
    # Issue #12647: the new canonical user_management declarative base bakes
    # created_at/updated_at into Base unconditionally (matching the backend's
    # already-migrated design). role_permissions and audit_logs never opted
    # into TimestampMixin, so they need the columns added — mirrors #10636.
    "add_role_permission_audit_log_timestamps",
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


def get_user_management_db_url() -> str:
    """URL for the separate user_management database (#14300).

    ``role_permissions`` and ``audit_logs`` are user_management tables,
    which live in a database of their own — distinct from the primary SLM
    database ``get_db_url()`` returns for ``DATABASE_URL``. Production opens
    that second database the same way the SLM backend itself already does
    at startup (``main.py``'s ``_init_user_management_tables`` via
    ``user_management.database.get_slm_engine``): through
    ``user_management.config.get_slm_db_config``, which reads
    ``SLM_USERS_DATABASE_URL`` (falling back to discrete
    ``SLM_POSTGRES_*`` env vars). No connection string is hardcoded here —
    this function is a thin sync-URL adapter over that existing config
    source, not a second source of truth for it.
    """
    from user_management.config import get_slm_db_config

    return get_slm_db_config().sync_url


# A migration module may declare which database it targets by setting a
# module-level ``TARGET_DB`` constant to one of these. Migrations that don't
# declare one default to TARGET_DB_SLM (DATABASE_URL) -- every migration
# written before #14300 is unaffected.
TARGET_DB_SLM = "slm"
TARGET_DB_USER_MANAGEMENT = "user_management"


def _resolve_migration_db_url(module, default_db_url: str) -> str:
    """Pick the connection URL a migration module should run against (#14300).

    Reading ``TARGET_DB`` off the module, rather than always handing every
    migration ``DATABASE_URL``, is what makes a cross-database migration
    like ``add_role_permission_audit_log_timestamps`` reachable at all: it
    alters ``role_permissions``/``audit_logs``, which live in the
    user_management database, never in ``DATABASE_URL``'s database — no
    connection to the latter can ever see those tables, by construction.

    An unrecognized ``TARGET_DB`` value is a configuration mistake in the
    migration itself, not something to quietly defer around: it raises here,
    at the moment the migration is loaded, so the mismatch is a loud,
    diagnosable failure instead of a deferral that looks identical to the
    ordinary "table not created yet" case and retries forever without
    anyone noticing the target database was wrong in the first place.
    """
    target = getattr(module, "TARGET_DB", TARGET_DB_SLM)
    if target == TARGET_DB_SLM:
        return default_db_url
    if target == TARGET_DB_USER_MANAGEMENT:
        return get_user_management_db_url()
    raise ValueError(
        f"{module.__name__} declares unknown TARGET_DB={target!r}; "
        f"expected {TARGET_DB_SLM!r} or {TARGET_DB_USER_MANAGEMENT!r}"
    )


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
    """Create migrations tracking table if it doesn't exist (#786, #5515, #14321)."""
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
        # #14321: seed_agents was recorded applied by the "no migrate()
        # function == success" default in run_migration below, without ever
        # seeding a row (see migrations/seed_agents.py). Clear that stale
        # entry once, on hosts where the roster genuinely never got seeded,
        # so the next run picks it up as pending and applies the real
        # migrate() this issue added. Guarded on the 'agents' table and a
        # known roster member so it never re-fires once seeding has run,
        # and never errors on a fresh DB where 'agents' doesn't exist yet.
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM migrations_applied WHERE name = 'seed_agents'
                )
                AND to_regclass('public.agents') IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM agents WHERE agent_id = 'chat'
                ) THEN
                    DELETE FROM migrations_applied WHERE name = 'seed_agents';
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

        # Resolve which database this migration actually targets (#14300) --
        # defaults to db_url (DATABASE_URL) unchanged for every migration
        # that doesn't declare TARGET_DB.
        target_db_url = _resolve_migration_db_url(module, db_url)

        # Check if it has a migrate() function (passes db_url)
        if hasattr(module, "migrate"):
            module.migrate(target_db_url)
            return True, f"Applied migration: {name}"
        elif hasattr(module, "run"):
            module.run(target_db_url)
            return True, f"Applied migration: {name}"
        else:
            # A module with no entry point did NOT run, so it must not report
            # success (#14321). This branch is what hid the defect this change
            # fixes: `seed_agents` exposed only a standalone async function, so
            # the runner never called anything, returned success here, and
            # recorded the migration in `migrations_applied` — a migration that
            # is permanently "applied" while its table stays unseeded, and no
            # bookkeeping check can ever see it because the bookkeeping is what
            # lied. Marking a migration applied when it did nothing is strictly
            # worse than failing: a failure is retried, a false success is not.
            #
            # Verified reachable-by-nobody at the time of the change: all 27
            # entries in MIGRATIONS expose `migrate()` or `run()`, so nothing
            # depends on the old permissive behaviour. Any migration that hits
            # this branch in future is malformed, and saying so loudly is the
            # only way the next one does not repeat #14321.
            return False, (
                f"{name} exposes no migrate(db_url) or run(db_url) entry point — "
                "nothing was executed. A migration module must expose one, or be "
                "removed from MIGRATIONS if it is not a migration."
            )

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
            _migration_utils.reset_deferrals()
            success, message = run_migration(db_url, migration_name)
            deferred = _migration_utils.deferrals()

            if success and deferred:
                # #14300: it "succeeded" having skipped every schema change it
                # was asked to make, because the tables were not in this
                # database. Marking it applied is what made that permanent —
                # leave it pending so the next boot retries it.
                message = f"Deferred {migration_name}: tables not present yet ({', '.join(deferred)})"
                logger.warning(message)
                results.append((migration_name, True, message))
                continue

            results.append((migration_name, success, message))

            if success:
                mark_migration_applied(conn, migration_name)
                logger.info(message)
            else:
                logger.error(message)
                # Stop on first failure
                break

    except Exception as e:
        # #14300: this used to record the error only when NOTHING had run yet.
        # An exception after one success left `results` all-successes, so the
        # startup caller saw a clean run and carried on with the schema half
        # migrated. The failure is always recorded now.
        logger.error("Migration execution failed: %s", e)
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


def _exit_code_for(results: List[Tuple[str, bool, str]]) -> int:
    """Non-zero exit whenever any migration in ``results`` failed (#14326).

    Extracted so the SLM migration gate's core assertion — a real migration
    failure must fail the process, not print a checkmark and exit 0 — is a
    plain function a unit test can call, rather than logic buried in
    ``__main__`` that only a live subprocess run could exercise.
    """
    return 1 if any(not success for _, success, _ in results) else 0


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

    sys.exit(_exit_code_for(results))
