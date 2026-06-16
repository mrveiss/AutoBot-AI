#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_git_safe_directory (#7219)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_git_safe_directory import find_violations  # noqa: E402


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_unguarded_blocked() -> None:
    body = "      command: git -C {{ git_repo_root }} log -1 --format='%h %s'\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1


def test_guarded_passes() -> None:
    body = "      command: git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }} log -1\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_unguarded_literal_path_blocked() -> None:
    body = "      cmd: git -C /opt/autobot/code_source status --porcelain\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1


def test_guarded_literal_path_passes() -> None:
    body = "      cmd: git -c safe.directory=/opt/autobot/code_source -C /opt/autobot/code_source status\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_git_other_dir_unaffected() -> None:
    """git -C of an UNrelated dir doesn't trigger the check."""
    body = "      cmd: git -C /tmp/some_repo log\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        assert find_violations(f) == []


def test_multiline_play_with_guard_passes() -> None:
    body = (
        "      cmd: >-\n"
        "        git -c safe.directory={{ git_repo_root }} -C {{ git_repo_root }}\n"
        "        log -1 --format='%h %s'\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", body)
        # Single-line-only check; multi-line >- folded form should be on one line by the time YAML parses it.
        # Per-line check: the line containing `git -C` must have `-c safe.directory` on the SAME line.
        # In the above sample, both are on the same line — should pass.
        assert find_violations(f) == []


if __name__ == "__main__":
    test_unguarded_blocked()
    test_guarded_passes()
    test_unguarded_literal_path_blocked()
    test_guarded_literal_path_passes()
    test_git_other_dir_unaffected()
    test_multiline_play_with_guard_passes()
    print("All tests passed.")
