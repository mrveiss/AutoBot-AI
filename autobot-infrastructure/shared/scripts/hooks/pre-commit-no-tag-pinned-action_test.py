# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for pre-commit-no-tag-pinned-action hook.

Issue #7120: lock down hook behavior so future tightening (or relaxation)
of the allowed-action policy can be done safely.

Each test invokes the hook in argv mode (positional file args), reads
exit code + stdout/stderr, and asserts on the rejection messages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-tag-pinned-action"


def _run(tmp_path: Path, content: str, rel: str = ".github/workflows/test.yml") -> subprocess.CompletedProcess:
    """Write a workflow file and invoke the hook via argv mode."""
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return subprocess.run(
        [str(HOOK_PATH), str(f)],
        capture_output=True,
        text=True,
    )


# === Allowed forms ===


def test_allow_first_party_actions_tag_pinned(tmp_path):
    """actions/* (first-party, GitHub-maintained) are allowed with tag pins."""
    result = _run(tmp_path, "jobs:\n  test:\n    steps:\n    - uses: actions/checkout@v6\n")
    assert result.returncode == 0, result.stdout + result.stderr


def test_allow_third_party_sha_pinned(tmp_path):
    """3rd-party actions with 40-char SHA are allowed."""
    sha = "d1c1ffe0248fe513906c8e24db8ea791d46f8590"
    result = _run(
        tmp_path,
        f"jobs:\n  test:\n    steps:\n    - uses: dorny/paths-filter@{sha}  # v3\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_allow_actions_with_subpath_tag_pinned(tmp_path):
    """actions/cache/save@v4 etc. — subpath under actions/* still allowed."""
    result = _run(tmp_path, "jobs:\n  test:\n    steps:\n    - uses: actions/cache/save@v4\n")
    assert result.returncode == 0


# === Rejected forms ===


def test_reject_third_party_tag_pinned_v3(tmp_path):
    """Common 3rd-party tag pin must be rejected."""
    result = _run(tmp_path, "jobs:\n  test:\n    steps:\n    - uses: dorny/paths-filter@v3\n")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "dorny/paths-filter" in result.stdout
    assert "v3" in result.stdout


def test_reject_third_party_branch_pinned(tmp_path):
    """Branch pins (e.g., @main, @master) must be rejected."""
    result = _run(tmp_path, "jobs:\n  test:\n    steps:\n    - uses: dorny/paths-filter@main\n")
    assert result.returncode == 1


def test_reject_github_namespace_tag_pinned(tmp_path):
    """github/* (GitHub-org but not actions/*) is treated as 3rd-party."""
    result = _run(tmp_path, "jobs:\n  test:\n    steps:\n    - uses: github/codeql-action/init@v4\n")
    assert result.returncode == 1
    assert "github/codeql-action" in result.stdout


def test_reject_short_sha(tmp_path):
    """Short SHAs (less than 40 chars) must be rejected — only full SHA pins are immutable."""
    result = _run(
        tmp_path,
        "jobs:\n  test:\n    steps:\n    - uses: dorny/paths-filter@d1c1ffe\n",
    )
    assert result.returncode == 1


def test_reject_semver_patch_tag(tmp_path):
    """Even precise semver tags (v3.0.2) are mutable in principle — reject."""
    result = _run(
        tmp_path,
        "jobs:\n  test:\n    steps:\n    - uses: dorny/paths-filter@v3.0.2\n",
    )
    assert result.returncode == 1


# === Mixed / multi-line ===


def test_multiple_uses_only_violators_reported(tmp_path):
    """File with mixed allowed + rejected — should fail and report only violators."""
    content = (
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "    - uses: actions/checkout@v6\n"
        "    - uses: dorny/paths-filter@v3\n"
        "    - uses: actions/setup-python@v5\n"
        "    - uses: codecov/codecov-action@v6\n"
    )
    result = _run(tmp_path, content)
    assert result.returncode == 1
    assert "dorny/paths-filter" in result.stdout
    assert "codecov/codecov-action" in result.stdout
    assert "actions/checkout" not in result.stdout  # not flagged
    assert "actions/setup-python" not in result.stdout  # not flagged


def test_comment_lines_ignored(tmp_path):
    """Commented-out tag pins should not trigger the hook."""
    result = _run(
        tmp_path,
        "jobs:\n  test:\n    steps:\n    # - uses: dorny/paths-filter@v3\n    - uses: actions/checkout@v6\n",
    )
    assert result.returncode == 0


def test_empty_file(tmp_path):
    """No staged workflow files — hook exits cleanly."""
    result = subprocess.run([str(HOOK_PATH)], capture_output=True, text=True)
    assert result.returncode == 0


def test_actions_path_allowed(tmp_path):
    """Composite actions under .github/actions/ also scanned."""
    # Composite action with allowed first-party uses
    result = _run(
        tmp_path,
        "name: composite\nruns:\n  using: composite\n  steps:\n    - uses: actions/checkout@v6\n",
        rel=".github/actions/setup/action.yml",
    )
    assert result.returncode == 0


def test_actions_path_rejects_third_party_tag(tmp_path):
    """Composite action with 3rd-party tag pin is rejected."""
    result = _run(
        tmp_path,
        "name: composite\nruns:\n  using: composite\n  steps:\n    - uses: dorny/paths-filter@v3\n",
        rel=".github/actions/setup/action.yml",
    )
    assert result.returncode == 1
