# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response payloads for the chat unshare endpoints (#18890)."""

from pydantic import BaseModel


class SessionParticipantsData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}/share (#18890)."""

    session_id: str
    participants: list[str]


class SessionUnshareData(BaseModel):
    """data payload for DELETE /chat/sessions/{session_id}/share/{user_id} (#18890)."""

    session_id: str
    user_id: str
    removed: bool
