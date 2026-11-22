# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place agent orchestration decides who the KB librarian reads as (#19591, #16665).

The reader is the verified triggering user the caller passed in, else nobody -- and the
librarian returns no facts for nobody. Never a wider principal: an A2A peer is not a local
user, and nothing here reads a user out of request ``context``, which the caller controls.
"""

from typing import Any, Dict


def reading_user(user_id: str | None) -> str | None:
    """The user the librarian reads as: the verified triggering user, or None."""
    if isinstance(user_id, str) and user_id.strip():
        return user_id
    return None


async def librarian_query(librarian: Any, query: str, user_id: str | None) -> Dict[str, Any]:
    """Run *query* on the KB librarian as the triggering user (the only librarian call here)."""
    return await librarian.process_query(query, user_id=reading_user(user_id))
