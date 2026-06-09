# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Convert all TIMESTAMP columns to TIMESTAMP WITH TIME ZONE

Issue #5385 — slm-backend datetime.utcnow() → now_utc() migration gate.

Converts every Column(DateTime) (naive TIMESTAMP) in models/database.py to
TIMESTAMP WITH TIME ZONE, interpreting all existing stored values as UTC.
This is correct because every write path used datetime.utcnow() (naive UTC).

The USING clause converts each value to timestamptz:
    ALTER COLUMN x TYPE TIMESTAMPTZ USING x AT TIME ZONE 'UTC'

After this migration:
- Column reads return timezone-aware UTC datetimes
- now_utc() assignments are stored correctly
- Python in-code comparisons (row.col - now_utc()) are aware-vs-aware
"""

import logging
import sys

from migrations.utils import get_connection, table_exists

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# All (table, column) pairs from models/database.py Column(DateTime) definitions
TIMESTAMP_COLUMNS = [
    ("nodes", "last_heartbeat"),
    ("nodes", "created_at"),
    ("nodes", "updated_at"),
    ("deployments", "started_at"),
    ("deployments", "completed_at"),
    ("deployments", "created_at"),
    ("deployments", "updated_at"),
    ("backups", "started_at"),
    ("backups", "completed_at"),
    ("backups", "created_at"),
    ("settings", "updated_at"),
    ("node_events", "created_at"),
    ("node_events", "resolved_at"),
    ("certificates", "not_before"),
    ("certificates", "not_after"),
    ("certificates", "created_at"),
    ("certificates", "updated_at"),
    ("replications", "started_at"),
    ("replications", "completed_at"),
    ("replications", "created_at"),
    ("replications", "updated_at"),
    ("update_info", "applied_at"),
    ("update_info", "created_at"),
    ("update_jobs", "started_at"),
    ("update_jobs", "completed_at"),
    ("update_jobs", "created_at"),
    ("update_jobs", "updated_at"),
    ("fleet_sync_jobs", "created_at"),
    ("fleet_sync_jobs", "completed_at"),
    ("fleet_sync_node_states", "started_at"),
    ("fleet_sync_node_states", "completed_at"),
    ("services", "last_checked"),
    ("services", "created_at"),
    ("services", "updated_at"),
    ("node_configs", "created_at"),
    ("node_configs", "updated_at"),
    ("service_conflicts", "created_at"),
    ("agents", "created_at"),
    ("agents", "updated_at"),
    ("maintenance_windows", "start_time"),
    ("maintenance_windows", "end_time"),
    ("maintenance_windows", "created_at"),
    ("maintenance_windows", "updated_at"),
    ("blue_green_deployments", "monitoring_started_at"),
    ("blue_green_deployments", "started_at"),
    ("blue_green_deployments", "switched_at"),
    ("blue_green_deployments", "completed_at"),
    ("blue_green_deployments", "rollback_at"),
    ("blue_green_deployments", "created_at"),
    ("blue_green_deployments", "updated_at"),
    ("system_secrets", "created_at"),
    ("system_secrets", "updated_at"),
    ("node_credentials", "tls_expires_at"),
    ("node_credentials", "last_used"),
    ("node_credentials", "created_at"),
    ("node_credentials", "updated_at"),
    ("audit_logs", "timestamp"),
    ("audit_logs", "created_at"),
    ("security_events", "timestamp"),
    ("security_events", "acknowledged_at"),
    ("security_events", "resolved_at"),
    ("security_events", "created_at"),
    ("security_events", "updated_at"),
    ("security_policies", "last_evaluated"),
    ("security_policies", "created_at"),
    ("security_policies", "updated_at"),
    ("update_schedules", "last_run"),
    ("update_schedules", "next_run"),
    ("update_schedules", "created_at"),
    ("update_schedules", "updated_at"),
    ("roles", "created_at"),
    ("roles", "updated_at"),
    ("node_roles", "last_synced_at"),
    ("node_roles", "created_at"),
    ("node_roles", "updated_at"),
    ("node_code_versions", "deployed_at"),
    ("node_code_versions", "updated_at"),
    ("code_sources", "last_notified_at"),
    ("code_sources", "created_at"),
    ("code_sources", "updated_at"),
    ("performance_traces", "created_at"),
    ("trace_spans", "start_time"),
    ("trace_spans", "end_time"),
    ("slo_definitions", "created_at"),
    ("slo_definitions", "updated_at"),
    ("alert_rules", "last_triggered"),
    ("alert_rules", "created_at"),
    ("alert_rules", "updated_at"),
    ("external_agents", "card_fetched_at"),
    ("external_agents", "created_at"),
    ("external_agents", "updated_at"),
]


def _is_already_timestamptz(cursor, table: str, column: str) -> bool:
    """Return True if column is already TIMESTAMP WITH TIME ZONE."""
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table, column),
    )
    row = cursor.fetchone()
    if row is None:
        return True  # column doesn't exist — skip
    return row[0] == "timestamp with time zone"


def migrate(db_url: str) -> None:
    """Convert all TIMESTAMP columns to TIMESTAMPTZ (#5385)."""
    logger.info("Running timestamps → timestamptz migration (#5385)")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    converted = 0
    skipped = 0

    for table, column in TIMESTAMP_COLUMNS:
        if not table_exists(cursor, table):
            logger.info("Table %s does not exist — skipping", table)
            skipped += 1
            continue

        if _is_already_timestamptz(cursor, table, column):
            logger.info("%s.%s already TIMESTAMPTZ — skipping", table, column)
            skipped += 1
            continue

        sql = f"ALTER TABLE {table} " f"ALTER COLUMN {column} TYPE TIMESTAMPTZ " f"USING {column} AT TIME ZONE 'UTC'"
        logger.info("Converting %s.%s → TIMESTAMPTZ", table, column)
        cursor.execute(sql)
        converted += 1

    conn.commit()
    conn.close()
    logger.info("Migration complete: %d columns converted, %d skipped", converted, skipped)


def main():
    """Entry point for running migration directly."""
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)


if __name__ == "__main__":
    main()
