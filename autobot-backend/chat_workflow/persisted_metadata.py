# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The metadata a workflow message is persisted with (#13424).

In flight, an ``execution_summary`` carries each tool's raw ``base64_image`` so the vision loop can read the
latest screenshot from ``execution_history``. The persisted copy does not need it: the screenshot is already
stored once, as the ``image_payload`` of its ``command_output`` message, and a second full-size copy only bloats
the session.
"""

from __future__ import annotations

from typing import Any

_SUMMARY_TYPE = "execution_summary"
_IMAGE_KEY = "base64_image"


def _without_bulk(result: dict[str, Any]) -> dict[str, Any]:
    """*result* without its raw screenshot and without the step's value literals (#21976: kept in flight only)."""
    kept = {k: v for k, v in result.items() if k != _IMAGE_KEY}
    if isinstance(kept.get("step"), dict):
        kept["step"] = {k: v for k, v in kept["step"].items() if k != "literals"}
    return kept


def persisted_metadata(message: Any) -> dict[str, Any] | None:
    """``message.metadata`` for the history entry; an execution summary's copy has no raw screenshots.

    The message itself is never mutated: the in-flight summary still feeds the vision loop.
    """
    metadata = message.metadata
    if message.type != _SUMMARY_TYPE or not metadata:
        return metadata
    results = metadata.get("execution_results")
    if not isinstance(results, list):
        return metadata
    stripped = [_without_bulk(r) if isinstance(r, dict) else r for r in results]
    return {**metadata, "execution_results": stripped}
