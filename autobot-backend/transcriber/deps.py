# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/deps.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FastAPI dependency: provides the transcriber Database instance."""

from fastapi import Request

from transcriber.database import Database

# Placeholder user ID for routes without real authentication.
# Replaced by real auth in future milestone.
DEFAULT_USER = "default"


async def get_db(request: Request) -> Database:
    return request.app.state.transcriber_db


def can_access(row: dict, caller_id: str) -> bool:
    """Single ownership policy for transcriber rows (recordings/projects).

    Rows stamped with DEFAULT_USER (created before real auth wiring) are
    accessible to any authenticated caller; otherwise the owner must match.
    All transcriber-data access checks must go through this helper so the
    policy cannot fork between routes (#9863 review).
    """
    owner = row.get("user_id") or DEFAULT_USER
    return owner in (DEFAULT_USER, caller_id)
