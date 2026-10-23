# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response schema for the chat turn-cancel route (#17273)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TurnCancelData(BaseModel):
    """Outcome of a turn-cancel request."""

    session_id: str
    status: Literal["cancelled", "no_active_turn", "unconfirmed"]
    cancelled_turns: int
