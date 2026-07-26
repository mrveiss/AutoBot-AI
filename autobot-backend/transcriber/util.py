# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/util.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared formatting helpers for transcriber export/knowledge/ai modules."""


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
