# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared path constants and helpers for code-source clone directories (#11129)."""
from pathlib import Path

CODE_SOURCES_BASE: Path = Path("/opt/autobot/data/code-sources")


def make_clone_path(source_id: str) -> str:
    """Return the canonical clone path for a source ID."""
    return str(CODE_SOURCES_BASE / source_id)
