# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Durable channel-event-stream tuning constants (#14817, #14818).

Every value is env-var backed at module import so nothing here is hard-coded at
a call site, per the project's TTL/config rule.
"""

import os

# Redis key prefixes for per-channel sequence allocation and replay storage.
CHANNEL_SEQ_KEY_PREFIX: str = os.getenv("AUTOBOT_CHANNEL_SEQ_KEY_PREFIX", "autobot:events:seq:")
CHANNEL_STREAM_KEY_PREFIX: str = os.getenv("AUTOBOT_CHANNEL_STREAM_KEY_PREFIX", "autobot:events:channel:")

# How many events are retained per channel for replay.  A client whose
# last_event_id has fallen out of this window is told to resync rather than
# handed a partial history.
CHANNEL_STREAM_MAX_ENTRIES: int = int(os.getenv("AUTOBOT_CHANNEL_STREAM_MAX_ENTRIES", "1000"))

# Idle channel streams expire so per-session and per-chat channels do not
# accumulate in Redis forever.
CHANNEL_STREAM_TTL_SECONDS: int = int(os.getenv("AUTOBOT_CHANNEL_STREAM_TTL_SECONDS", "86400"))
