# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pipeline-scripts/check-pre-commit-hook-pr.sh (#6785).

Confirms the generic CI wrapper:

1. Routes the right hook based on argv[1].
2. Skips cleanly when no source files changed.
3. Forwards an explicit file list to the hook in argv mode (so the hook's
   allowlist is the only filter that matters).
4. Surfaces hook exit codes (1 = violation, 0 = clean).

Each test creates a tmp git repo, sets up a synthetic PR commit, and runs
the wrapper with BASE_SHA/HEAD_SHA pointing at it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "pipeline-scripts" / "check-pre-commit-hook-pr.sh"


def _make_pr(tmp_path: Path, files: dict[str, str]) -> tuple[str, str]:
    """Create a tmp git repo with one base commit + one 'PR' commit.

    Returns (base_sha, head_sha) suitable for BASE_SHA/HEAD_SHA env.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    # Empty base commit so we have something to diff against.
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"],
        cwd=tmp_path,
        check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    # Add the PR's files in a second commit.
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "pr"],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    # Hooks live at <REPO_ROOT>/autobot-infrastructure/...; tmp_path doesn't
    # have those, so we run the wrapper from the real REPO_ROOT and pass
    # the diff endpoints via env. The wrapper does `git diff` on cwd's repo;
    # to make that match tmp_path's diff, we cd to tmp_path AND point GIT_DIR.
    return base, head


def _run_wrapper(tmp_path: Path, hook_name: str, base: str, head: str) -> subprocess.CompletedProcess:
    """Run the wrapper inside ``tmp_path`` so its `git diff` finds the test repo."""
    return subprocess.run(
        ["bash", str(WRAPPER), hook_name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestArgvDispatch:
    """The wrapper's first arg picks which hook to run."""

    def test_unknown_hook_name_exits_2(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"a.py": "x = 1\n"})
        result = subprocess.run(
            ["bash", str(WRAPPER), "pre-commit-does-not-exist"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()

    def test_missing_arg_exits_2(self, tmp_path: Path) -> None:
        result = subprocess.run(
            ["bash", str(WRAPPER)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "Usage" in result.stderr


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestNoChangedFiles:
    """Skip cleanly when the diff has no source files."""

    def test_no_relevant_files_exits_0(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"docs/notes.md": "# unrelated\n"})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode == 0
        assert "No changed source files" in result.stdout


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestForwardsArgvToHooks:
    """End-to-end: wrapper passes argv to hooks correctly."""

    def test_no_print_console_blocks_print(self, tmp_path: Path) -> None:
        # Production .py with a print() call must trip the no-print hook
        base, head = _make_pr(tmp_path, {"src/worker.py": 'print("hi")\n'})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode != 0

    def test_no_print_console_allows_test_files(self, tmp_path: Path) -> None:
        # Test files are allowlisted by the hook's filter
        base, head = _make_pr(tmp_path, {"src/foo_test.py": 'print("hi")\n'})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode == 0

    def test_no_direct_redis_blocks_bare_redis(self, tmp_path: Path) -> None:
        # `redis.Redis()` direct instantiation in production code
        base, head = _make_pr(tmp_path, {"src/r.py": "import redis\nclient = redis.Redis()\n"})
        result = _run_wrapper(tmp_path, "pre-commit-no-direct-redis", base, head)
        assert result.returncode != 0


def _run_wrapper_python(
    tmp_path: Path, validator: Path, base: str, head: str, ext: str = ""
) -> subprocess.CompletedProcess:
    """Run the wrapper in --python mode from tmp_path."""
    args = ["bash", str(WRAPPER), "--python", str(validator)]
    if ext:
        args += ["--ext", ext]
    return subprocess.run(
        args,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestPythonValidatorMode:
    """--python flag: routes to a Python validator instead of a bash hook."""

    def test_missing_validator_exits_2(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"a.py": "x = 1\n"})
        result = subprocess.run(
            ["bash", str(WRAPPER), "--python", "tools/lint/nonexistent.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()

    def test_no_changed_py_files_skips(self, tmp_path: Path) -> None:
        # Write a dummy validator that always exits 1
        validator = tmp_path / "check_always_fail.py"
        validator.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"docs/README.md": "# docs\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext="py")
        assert result.returncode == 0
        assert "No changed source files" in result.stdout

    def test_python_validator_exit_code_propagated(self, tmp_path: Path) -> None:
        # A validator that exits 1 must cause the wrapper to exit non-zero
        validator = tmp_path / "check_always_fail.py"
        validator.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext="py")
        assert result.returncode != 0

    def test_python_validator_clean_exit_0(self, tmp_path: Path) -> None:
        # A validator that exits 0 (clean) passes
        validator = tmp_path / "check_always_pass.py"
        validator.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext="py")
        assert result.returncode == 0
