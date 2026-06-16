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
    """Strict ownership policy for transcriber rows (recordings/projects).

    Only the row owner may access the row.  The caller_id must equal the
    stored user_id exactly:

    - owner == caller_id  → allow (includes single_user: "default" == "default")
    - different real users → deny
    - DEFAULT_USER row + real caller  → DENY  (this was the IDOR — #9968)
    - unowned / falsy user_id row    → deny (create_recording always stamps user_id)

    Cross-user access to legacy DEFAULT_USER rows is intentionally NOT
    supported.  If a future multi-user migration needs to reassign those rows
    to real owners, that is tracked separately — do not re-introduce the
    shared-DEFAULT_USER bypass here.

    All transcriber-data access checks must go through this helper so the
    policy cannot fork between routes (#9863 review).
    """
    owner = row.get("user_id")
    return bool(owner) and owner == caller_id
