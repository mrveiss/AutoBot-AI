#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env-fork sweep entrypoint (#18094): one env var, one fallback; one SSOT constant, one definition.

Its own CLI, separate from ``check_getenv_ssot_drift``: the two answer different questions over
different populations and floors, and a shared entrypoint let this sweep's floor and SSOT-source
requirement swallow the drift hook's verdict (#19215). The detector, population (``sweep_env_forks``) and
floor (``FORK_READ_FLOOR``) live in ``_env_fork_scan``; exit ``0`` clean, ``1`` finding, ``2`` the
sweep proved nothing (below the floor, SSOT source missing, or not a git toplevel).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Sibling-directory insert (#13842): resolves as a script and as an imported module alike.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _check_harness import run_anchored  # noqa: E402
from _env_fork_scan import FORK_READ_FLOOR, HOOK_ID, collect_env_forks, summary  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Full-repo sweep; always the whole tree, since a fork spans files."""
    del argv
    return run_anchored(
        HOOK_ID,
        collect_env_forks,
        [],
        anchor=Path(__file__),
        floor=FORK_READ_FLOOR,
        summary=summary,
        unit="env fallback read(s)",
    )


if __name__ == "__main__":
    sys.exit(main())
