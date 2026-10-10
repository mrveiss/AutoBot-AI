# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Decision helpers shared by the bandit and flake8 exclude-anchoring guards (#14896).

``check_bandit_exclude_anchoring`` and ``check_flake8_exclude_anchoring`` carried
byte-identical copies of :func:`unanchored_source_entries` and near-identical
copies of :func:`tracked_py_files`; they differ only in what "bare" means for
their tool, so that predicate is passed in.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Callable, Collection

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _scan_helpers import tracked_paths  # noqa: E402


def unanchored_source_entries(
    entries: list[str],
    bare_entries: Callable[[list[str]], list[str]],
    artifact_names: Collection[str],
) -> list[str]:
    """Bare entries (per *bare_entries*) that are not a sanctioned artifact name.

    The decision the guards turn on, kept separate so callers can put a
    synthetic list through it instead of asserting on the config's text.
    """
    return [entry for entry in bare_entries(entries) if entry not in artifact_names]


def tracked_py_files(root: pathlib.Path) -> list[str]:
    """Every tracked ``*.py`` path under *root*, enumerated by git.

    Through the shared enumerator so the scrubbed git environment is not a
    per-hook repeat, and a failed or empty listing raises instead of reading as
    "the tool excludes nothing".
    """
    return tracked_paths(root, "*.py")
