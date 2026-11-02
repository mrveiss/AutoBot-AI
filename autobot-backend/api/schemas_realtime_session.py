# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response schema for the realtime voice session list (#18451)."""

from pydantic import BaseModel


class RealtimeSessionSummary(BaseModel):
    session_id: str
    user_id: str | None
    model: str
    started_at: str
    ended_at: str | None
    duration_s: float
    audio_in_s: float
    audio_out_s: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    estimated_cost_usd: float
    disconnect_reason: str
