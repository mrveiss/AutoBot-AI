# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ownership-resolution failure, separate from "no owner recorded" (#14033).

Its own module because both `security/session_ownership.py` and
`chat_history/session.py` are at their recorded size ceilings, and a
grandfathered file may not grow to host it (#14236).
"""

from __future__ import annotations


class SessionOwnerUnreadable(RuntimeError):
    """Ownership could not be determined for a session.

    Distinct from ``get_session_owner`` returning ``None``, which means the
    session exists and genuinely records no owner. This means the answer is
    unknown — the file could not be read or decrypted — and a caller must not
    treat that as "unowned". Two callers did exactly that, so an unreadable
    session file granted access to another user's conversation.
    """

    def __init__(self, session_id: str) -> None:
        super().__init__(f"cannot determine ownership for session {session_id!r}")
        self.session_id = session_id
