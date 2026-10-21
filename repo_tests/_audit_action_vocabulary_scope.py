# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which files the audit action vocabulary guard reads (#18716).

Judged on the repo-relative path split into parts, never on a substring of the absolute path:
a checkout that sits under a directory named ``tests`` would otherwise make every file look
like a test (#18972).
"""

from __future__ import annotations

from pathlib import Path

from tools.lint._scan_helpers import tracked_paths

ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend")


def source_python(rel: str) -> bool:
    """True for non-test Python under one of ``ROOTS``; *rel* is repo-relative."""
    parts = rel.split("/")
    name = parts[-1]
    is_test = name.endswith("_test.py") or name.startswith("test_") or "tests" in parts[:-1]
    return rel.endswith(".py") and parts[0] in ROOTS and not is_test


def scoped_sources(root: Path) -> list[str]:
    """The tracked non-test Python the guard reads, repo-relative; one enumeration for every caller."""
    return [rel for rel in tracked_paths(root, *ROOTS) if source_python(rel)]
