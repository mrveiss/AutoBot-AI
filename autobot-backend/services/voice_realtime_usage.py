# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Usage deltas for realtime voice sessions (#21678).

Usage is accounted as additive deltas, never as whole-record snapshots: a delta that could not be committed
(Redis down, telemetry off, a failed write) is kept pending and added with the next one, so no write failure,
consent flip or missing-key race can replace a larger total with a smaller one.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass
class UsageDelta:
    """Usage to ADD to a session record: tokens, audio seconds and tool calls (cost derives from these)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    audio_in_s: float = 0.0
    audio_out_s: float = 0.0
    tool_calls: int = 0

    def merged(self, other: "UsageDelta") -> "UsageDelta":
        """A new delta holding both."""
        return UsageDelta(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})

    def apply_to(self, record: Any) -> None:
        """Add this delta onto *record* in place."""
        for f in fields(self):
            setattr(record, f.name, getattr(record, f.name) + getattr(self, f.name))
