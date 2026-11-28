# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Shared text helpers for agent_loop (#12724).

Canonical ``slugify`` extracted from the byte-identical duplicates
previously defined in ``belief_state.py`` and
``extractors/web_search.py``.
"""

from __future__ import annotations

from autobot_shared.slug import sanitize_token


def slugify(text: str) -> str:
    """Return a lowercase, whitespace-collapsed slug capped at 80 chars."""
    return sanitize_token(
        text,
        allowed=r"\w\s-",
        replacement="",
        collapse=False,
        separator_chars=r"\s_-",
        separator="_",
        case="lower",
        strip_input=True,
        max_length=80,
    )
