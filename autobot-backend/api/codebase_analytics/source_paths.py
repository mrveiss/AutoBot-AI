# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared path constants and helpers for code-source clone directories (#11129)."""

from pathlib import Path

from autobot_shared.paths import project_root

# #13149: derived from the canonical project root instead of a hardcoded
# `/opt/autobot` literal, so a dev checkout clones sources under the checkout
# rather than reading/writing the live install's clone directory.
CODE_SOURCES_BASE: Path = project_root() / "data" / "code-sources"


def make_clone_path(source_id: str) -> str:
    """Return the canonical clone path for a source ID."""
    return str(CODE_SOURCES_BASE / source_id)
