# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One reader for a model's context window in ``config/context_windows.yaml`` (#20884).

Kept apart from ``context_window_manager`` (a size-frozen file) so every caller that needs a window from the
table, from any working directory, reads it the same way instead of writing the number.
"""

from __future__ import annotations

from pathlib import Path

from context_window_manager import get_context_window_manager

_CONTEXT_WINDOWS_YAML = Path(__file__).resolve().parent / "config" / "context_windows.yaml"


def known_context_window_tokens(model_name: str) -> int:
    """The context window in the table for *model_name*, or 0 when it has no entry (unknown, never a guess).

    A ``provider/`` prefix is ignored.
    """
    models = get_context_window_manager(str(_CONTEXT_WINDOWS_YAML)).config.get("models")
    if not isinstance(models, dict):
        return 0  # a malformed table is "no entry", never an exception for the caller
    # A gateway spells the model ``provider/model``: the table is keyed by the bare ID.
    entry = models.get(model_name.lower().rsplit("/", 1)[-1])
    if not isinstance(entry, dict):
        return 0
    return int(entry.get("context_window_tokens", 0))
