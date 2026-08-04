#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for scripts/check_script_exec_bits.py (#13355).

The checker's whole value is that it fires only on a real mismatch. Its first
draft matched any backtick-wrapped path and reported six prose mentions —
``see `scripts/format.sh` for the wrapper`` and similar. A checker that is
wrong on correct work gets ignored, so the discrimination between *naming* a
script and *running* one is what these tests pin.

Run: python3 -m pytest scripts/check_script_exec_bits_test.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "check_script_exec_bits.py"
_spec = importlib.util.spec_from_file_location("check_script_exec_bits", _MODULE_PATH)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)  # type: ignore[union-attr]


# --------------------------------------------------------------- invocations


@pytest.mark.parametrize(
    "line",
    [
        "scripts/start-services.sh start",
        "  scripts/start-services.sh restart backend",
        "$ scripts/cleanup-worktrees.sh --dry-run",
        "Bulk: `scripts/cleanup-worktrees.sh --dry-run` then something",
        './scripts/gh-pr-update-body.sh $PR "body"',
        "scripts/start-services.sh",
    ],
)
def test_recognises_an_invocation(line):
    hits = {m.group(1) for m in checker._INVOCATION_WITH_ARGS.finditer(line)}
    alone = checker._INVOCATION_ALONE.match(line)
    if alone:
        hits.add(alone.group(1))
    assert hits, f"should be read as running a script: {line!r}"


# ------------------------------------------------------------ mere mentions


@pytest.mark.parametrize(
    "line",
    [
        "- **`scripts/cleanup-worktrees.sh`** prunes stale worktrees and branches",
        "`scripts/format.sh` wrapper + make targets; Python 3.14 settings pinned",
        "- `scripts/setup_daily_health_check.sh` - Configures daily cron job",
        "Safety guards (shared in `scripts/lib/branch-guards.sh`, tested by ...)",
        "A convenience wrapper is available at `scripts/gh-pr-update-body.sh`:",
    ],
)
def test_ignores_a_bare_mention(line):
    """Naming a file is not running it — this is what the first draft got wrong."""
    hits = {m.group(1) for m in checker._INVOCATION_WITH_ARGS.finditer(line)}
    alone = checker._INVOCATION_ALONE.match(line)
    if alone:
        hits.add(alone.group(1))
    assert not hits, f"should NOT be read as running a script: {line!r}"


# ------------------------------------------------------ interpreter-prefixed


@pytest.mark.parametrize(
    "line",
    [
        "bash scripts/format.sh --check",
        "bash scripts/lib/branch-guards_test.sh",
        "sh scripts/format.sh path/to/file.py",
        "source scripts/lib/branch-guards.sh",
        "# shellcheck source=scripts/lib/branch-guards.sh",
    ],
)
def test_ignores_interpreter_prefixed_and_directives(line):
    """A script handed to an interpreter needs no exec bit — 644 is correct there."""
    assert checker._INTERPRETED.search(line) or checker._DIRECTIVE.search(line), line


# ------------------------------------------------------------- end to end


def test_repository_is_currently_clean():
    """The tree must satisfy its own invariant."""
    problems = checker.find_disagreements()
    assert problems == [], "\n".join(problems[:10])


def test_archival_files_are_not_scanned():
    """A changelog records what someone once ran; it is not an instruction."""
    assert "CHANGELOG.md" in checker._ARCHIVAL
    assert ".session/" in checker._ARCHIVAL
