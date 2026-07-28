# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Shared text helpers for agent_loop (#12724).

Canonical ``slugify`` extracted from the byte-identical duplicates
previously defined in ``belief_state.py`` and
``extractors/web_search.py``.
"""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Return a lowercase, whitespace-collapsed slug capped at 80 chars."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:80]
