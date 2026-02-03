# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking Database Module

SQLite database schema, initialization, and sync helper functions
for use with asyncio.to_thread().

Part of Issue #381 - God Class Refactoring
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

from .models import StateSnapshot
from .types import TrackingMetric

logger = logging.getLogger(__name__)

# Issue #281: SQL schema definitions
DATABASE_SCHEMA_TABLES = (
    # State snapshots table
    """
    CREATE TABLE IF NOT EXISTS state_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL,
        phase_states TEXT NOT NULL,
        active_capabilities TEXT NOT NULL,
        system_metrics TEXT NOT NULL,
        configuration TEXT NOT NULL,
        validation_results TEXT NOT NULL,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # State changes table
    """
    CREATE TABLE IF NOT EXISTS state_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL,
        change_type TEXT NOT NULL,
        before_state TEXT,
        after_state TEXT NOT NULL,
        description TEXT NOT NULL,
        user_id TEXT,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Metrics history table
    """
    CREATE TABLE IF NOT EXISTS metrics_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        value REAL NOT NULL,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Milestones table
    """
    CREATE TABLE IF NOT EXISTS milestones (
        name TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        criteria TEXT NOT NULL,
        achieved BOOLEAN DEFAULT FALSE,
        achieved_at TIMESTAMP,
        evidence TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Events table for detailed tracking
    """
    CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        event_data TEXT NOT NULL,
        source TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
)

# Issue #281: Index creation SQL statements
DATABASE_SCHEMA_INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON metrics_history (metric_name, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_event_type ON system_events (event_type)",
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON system_events (timestamp)",
)


def init_database(db_path: str) -> None:
    """
    Initialize SQLite database for enhanced state tracking.

    Issue #281: Refactored to use module-level constants.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Create tables from module-level schema definitions
        for table_sql in DATABASE_SCHEMA_TABLES:
            cursor.execute(table_sql)

        # Create indices from module-level definitions
        for index_sql in DATABASE_SCHEMA_INDICES:
            cursor.execute(index_sql)

        conn.commit()


# ============================================================================
# Sync SQLite helper functions for asyncio.to_thread() (Issue #357)
# ============================================================================


def save_snapshot_sync(
    db_path: str,
    timestamp_iso: str,
    phase_states_json: str,
    capabilities_json: str,
    metrics_json: str,
    config_json: str,
    validation_json: str,
    metadata_json: str,
    metrics_list: List[Tuple[str, str, float]],
) -> None:
    """Save snapshot to database synchronously (Issue #357: for use with asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO state_snapshots
            (timestamp, phase_states, active_capabilities, system_metrics,
             configuration, validation_results, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                timestamp_iso,
                phase_states_json,
                capabilities_json,
                metrics_json,
                config_json,
                validation_json,
                metadata_json,
            ),
        )

        # Issue #397: Fix N+1 pattern - use executemany for batch insert
        if metrics_list:
            cursor.executemany(
                """
                INSERT INTO metrics_history (metric_name, timestamp, value)
                VALUES (?, ?, ?)
            """,
                metrics_list,
            )

        conn.commit()


def record_state_change_sync(
    db_path: str,
    timestamp_iso: str,
    change_type: str,
    before_state_json: Optional[str],
    after_state_json: str,
    description: str,
    user_id: Optional[str],
    metadata_json: str,
) -> None:
    """Record state change to database synchronously (Issue #357: for use with asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO state_changes
            (timestamp, change_type, before_state, after_state,
             description, user_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                timestamp_iso,
                change_type,
                before_state_json,
                after_state_json,
                description,
                user_id,
                metadata_json,
            ),
        )

        conn.commit()


def save_milestone_sync(
    db_path: str,
    name: str,
    description: str,
    criteria_json: str,
    achieved: bool,
    achieved_at_iso: Optional[str],
    evidence_json: str,
    updated_at_iso: str,
) -> None:
    """Save milestone to database synchronously (Issue #357: for use with asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO milestones
            (name, description, criteria, achieved, achieved_at, evidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                name,
                description,
                criteria_json,
                achieved,
                achieved_at_iso,
                evidence_json,
                updated_at_iso,
            ),
        )

        conn.commit()


def load_snapshots_from_db(db_path: str, limit: int = 100) -> List[StateSnapshot]:
    """Load recent snapshots from database."""
    snapshots = []

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, phase_states, active_capabilities,
                   system_metrics, configuration, validation_results, metadata
            FROM state_snapshots
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        for row in cursor.fetchall():
            snapshot = StateSnapshot(
                timestamp=datetime.fromisoformat(row[0]),
                phase_states=json.loads(row[1]),
                active_capabilities=set(json.loads(row[2])),
                system_metrics={
                    TrackingMetric(k): v for k, v in json.loads(row[3]).items()
                },
                configuration=json.loads(row[4]),
                validation_results=json.loads(row[5]),
                metadata=json.loads(row[6]) if row[6] else {},
            )
            snapshots.append(snapshot)

    return snapshots


def load_milestones_from_db(db_path: str, milestones: dict) -> None:
    """Load milestones from database and update the provided dict."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM milestones")

        for row in cursor.fetchall():
            name = row[0]
            if name not in milestones:
                continue

            milestones[name].achieved = bool(row[3])
            if row[4]:
                milestones[name].achieved_at = datetime.fromisoformat(row[4])
            if row[5]:
                milestones[name].evidence = json.loads(row[5])
