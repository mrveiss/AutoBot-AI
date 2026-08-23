# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    r"""Write a workflow file and invoke the hook via argv mode.

    The path goes in REPO-RELATIVE with cwd at its root, because that is the
    only shape a real caller produces: pre-commit and the CI wrappers both hand
    the hook paths relative to the repository root.

    GH#14884: this used to pass ``str(f)`` — an absolute ``/tmp/pytest-.../...``
    path. GH#13936 made ``get_staged_files`` apply the caller's own pattern to
    the argv branch as well as the staged branch, and this hook's pattern is
    anchored: ``^\.github/(workflows|actions)/.*\.ya?ml$``. An absolute path
    cannot match that anchor, so the hook received an empty file list, took its
    ``[ -z "$files" ] && exit 0`` path and reported clean. The seven "must
    reject" tests read that as a missing rejection and went red; worse, the
    three "must allow" tests went green having exercised nothing at all.
    """
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return subprocess.run(
        [str(HOOK_PATH), rel],
        cwd=tmp_path,
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


def test_no_staged_files_in_a_real_repo_exits_cleanly(tmp_path):
    """Nothing staged, inside an actual git repo — the real 'nothing to
    check' case a git hook invocation always runs in. Replaces the old
    test_empty_file, which ran the hook OUTSIDE any git repository at all;
    that is not "no files staged", it is git itself failing to answer the
    question — now covered by TestFailsClosedWhenGitCannotAnswer below
    (GH#14151)."""
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    result = subprocess.run([str(HOOK_PATH)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


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


# === GH#14151: fails closed when git itself cannot answer ===


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path):
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _stage_tag_pinned_workflow(repo):
    wf = repo / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text("jobs:\n  build:\n    steps:\n      - uses: dorny/paths-filter@v3\n", encoding="utf-8")
    _git(repo, "add", ".github/workflows/ci.yml")


class TestFailsClosedWhenGitCannotAnswer:
    """GH#14151: `set -uo pipefail` (no `-e`) plus an unguarded `source
    lib/_common.sh`, combined with get_staged_files()'s former blanket
    `|| true`, meant a broken dependency OR a `git diff --cached` failure
    degraded to an empty file list — read as "nothing to check" and exited
    0 even with a genuinely staged tag-pinned action present. Unlike the
    other hooks in this family, THIS one has no banner echo referencing a
    color variable at the top of main(), so `set -u` alone never caught the
    missing-lib case either — both reproductions below are genuine fail-open
    bugs in the pre-fix script, not merely defense-in-depth.
    """

    def test_a_missing_common_lib_does_not_report_clean(self, tmp_path):
        repo = _init_repo(tmp_path)
        _stage_tag_pinned_workflow(repo)

        # A copy of the hook with no `lib/` beside it — the dependency is gone.
        isolated = tmp_path.parent / "isolated-no-tag-pinned-action"
        isolated.mkdir()
        hook_copy = isolated / HOOK_PATH.name
        hook_copy.write_bytes(HOOK_PATH.read_bytes())
        hook_copy.chmod(0o755)

        result = subprocess.run([str(hook_copy)], cwd=repo, capture_output=True, text=True)
        assert result.returncode != 0, "the hook reported clean with a staged violation and no dependency"

    def test_a_git_failure_does_not_report_clean(self, tmp_path):
        repo = _init_repo(tmp_path)
        _stage_tag_pinned_workflow(repo)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run([str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
