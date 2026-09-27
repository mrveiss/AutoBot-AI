# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stylelint job's changed-file list must not contain deleted paths (#17571).

``git diff --name-only`` reports a DELETED file's path, and the job then hands
that list to ``npx stylelint``.  stylelint answers ``NoFilesFoundError`` for a
path that is not in the checkout and exits 123 -- *before* linting any of the
files that do exist.  So a PR that removed one CSS file received **zero** lint
coverage on the CSS it actually changed, and because the job is
``continue-on-error: true`` the outcome rendered as an ordinary red badge:
indistinguishable from "ran and found problems" when nothing had been read.
#17571 hit it by deleting ``autobot-frontend/src/assets/tokens.css``.

The fix is ``--diff-filter=d``.  ``import-hermeticity-sweep.yml`` already used
it for the same reason, so this was the one workflow out of step, not a class.

These tests run the workflow's own ``run:`` script in a throwaway repo rather
than grepping it for the flag, following ``prepush_diff_range_16637_test.py``:
a flag can be present and the pipeline still wrong, and a guard that only reads
the text cannot tell those apart.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_WORKFLOW = repo_root() / ".github" / "workflows" / "stylelint-tokens.yml"
_STEP = "Determine changed frontend CSS/Vue files"

# Cross-derived population: every workflow that turns `git diff --name-only`
# into a list a per-file tool is then made to open.  Both must skip deletions.
_DELETION_SENSITIVE = ("stylelint-tokens.yml", "import-hermeticity-sweep.yml")


def _run(cwd: Path, *args: str) -> str:
    """A git write in the throwaway repo, with the ambient git vars removed.

    The pre-push hook exports GIT_DIR and GIT_INDEX_FILE into its environment,
    so an unscrubbed subprocess here writes to the REAL repository instead of
    `cwd` -- #15246, and the #15783 family `scrubbed_git_env` exists to end.
    This guard learned it the direct way: green standalone, `git commit` exit 1
    inside the hook.

    `_listed` needs no scrub: it passes a complete env dict rather than
    inheriting one, so no ambient git var reaches the workflow script.
    """
    done = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=scrubbed_git_env(),
    )
    return done.stdout


def _changed_step_script() -> str:
    spec = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    for job in spec["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == _STEP:
                return step["run"]
    raise AssertionError(f"{_WORKFLOW.name} has no step named {_STEP!r}")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo whose HEAD adds one CSS file, edits another, and deletes a third."""
    root = tmp_path / "repo"
    (root / "autobot-frontend" / "src").mkdir(parents=True)
    _run(root, "git", "init", "-q", "-b", "main")
    _run(root, "git", "config", "user.email", "t@example.invalid")
    _run(root, "git", "config", "user.name", "t")

    fe = root / "autobot-frontend" / "src"
    (fe / "kept.css").write_text("a{color:red}\n", encoding="utf-8")
    (fe / "removed.css").write_text("b{color:red}\n", encoding="utf-8")
    _run(root, "git", "add", "-A")
    _run(root, "git", "commit", "-qm", "base")
    base = _run(root, "git", "rev-parse", "HEAD").strip()
    # The job diffs against `origin/$BASE_REF`; no network is involved in
    # creating that ref, and `git fetch ... || true` in the script tolerates
    # the absent remote.
    _run(root, "git", "update-ref", "refs/remotes/origin/main", base)

    (fe / "kept.css").write_text("a{color:blue}\n", encoding="utf-8")
    (fe / "added.vue").write_text("<style>c{color:red}</style>\n", encoding="utf-8")
    (fe / "removed.css").unlink()
    _run(root, "git", "add", "-A")
    _run(root, "git", "commit", "-qm", "change")
    return root


def _listed(repo: Path) -> list[str]:
    outputs = repo / "gh-output"
    outputs.touch()
    subprocess.run(
        ["bash", "-c", _changed_step_script()],
        cwd=repo,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "BASE_REF": "main",
            "GITHUB_OUTPUT": str(outputs),
            "HOME": str(repo),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    listed = (repo / "changed-frontend.txt").read_text(encoding="utf-8").split()
    return sorted(listed)


def test_deleted_file_is_not_handed_to_stylelint(repo: Path) -> None:
    """The path stylelint would fail on is the one that must not be listed."""
    assert "src/removed.css" not in _listed(repo)


def test_added_and_modified_files_are_still_listed(repo: Path) -> None:
    """Skipping deletions must not also skip the files that need linting.

    Asserted separately from the deletion: a script that emitted nothing at all
    would satisfy the test above while checking even less than the bug did.
    """
    assert _listed(repo) == ["src/added.vue", "src/kept.css"]


def test_the_count_matches_the_list_it_gates(repo: Path) -> None:
    """`frontend_count` gates whether the lint step runs at all.

    A count taken before the deletion filter would start stylelint for a list
    that no longer justifies it -- or, on a deletion-only PR, start it for an
    empty list and reproduce the original exit 123.
    """
    listed = _listed(repo)
    output = (repo / "gh-output").read_text(encoding="utf-8")
    count = re.search(r"^frontend_count=(\d+)$", output, re.M)
    assert count is not None, output
    assert int(count.group(1)) == len(listed)


@pytest.mark.parametrize("name", _DELETION_SENSITIVE)
def test_every_deletion_sensitive_workflow_skips_deletions(name: str) -> None:
    """Both workflows feeding a changed-file list to a per-file tool must filter.

    Population cross-derived by grepping `.github/workflows/` for
    `diff --name-only`; the parametrisation fails loudly if a listed workflow
    stops containing the command rather than passing vacuously.
    """
    text = (repo_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")
    uses = [ln.strip() for ln in text.splitlines() if "diff --name-only" in ln]
    assert uses, f"{name} no longer runs `git diff --name-only`; re-derive the population"
    assert all("--diff-filter=d" in ln for ln in uses), uses
