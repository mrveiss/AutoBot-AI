# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The in-place upgrades a conversation-files database made by an older release gains (#20678, #21404).

One call for the manager's schema init and for migration 001, so a new upgrade is added here once and both
paths pick it up. Each upgrade is idempotent and keeps every row. No request-handling imports.
"""

from __future__ import annotations

import sqlite3

from conversation_file_access_type_schema import ensure_access_type_schema
from conversation_file_quota_owner_schema import ensure_quota_owner_schema


def apply_schema_upgrades(connection: sqlite3.Connection) -> None:
    """Add what the schema file's ``CREATE ... IF NOT EXISTS`` leaves out of a table that already existed."""
    ensure_quota_owner_schema(connection)  # the quota_owner column (#20678)
    ensure_access_type_schema(connection)  # the 'reference' access type (#21404)
