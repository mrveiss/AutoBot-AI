# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A worktree's first commit must not re-index the live doc collection (#16934).

`post-commit-doc-sync` fired on every commit in every worktree, with no branch
or origin check, and indexed that worktree's own tree into the shared, live
`autobot_docs` ChromaDB collection -- a fresh worktree has no per-checkout hash
cache, so its first commit read as 304 changed files and wrote unmerged branch
docs into production for 5+ minutes.

The fix moved doc-sync from `post-commit` to `post-merge` (Issue #16934) and
gated it explicitly on branch == "main" and HEAD == origin/main's own tip, so
indexing only ever happens on real code that already reached the base branch.

These tests drive the real hook scripts against a throwaway repo via actual
`git commit`/`git merge`, not a reimplementation of their logic -- the same
technique `git_hooks_formatter_dispatch_16923_test.py` uses. The indexer itself
is stubbed to a marker-file write so the tests need no ChromaDB or embedding
model; only the gating this hook owns is under test.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = repo_root()
_HOOK = _REPO_ROOT / "autobot-infrastructure/shared/scripts/hooks/post-merge-doc-sync"
_COMMON_LIB = _REPO_ROOT / "autobot-infrastructure/shared/scripts/hooks/lib/_common.sh"
_POST_COMMIT = _REPO_ROOT / "scripts/hooks/post-commit"

_MARKER_NAME = "INDEXER_INVOKED_MARKER"

_INDEXER_STUB = """\
#!/usr/bin/env python3
import sys
from pathlib import Path
Path(__file__).resolve().parent.parent.joinpath("{marker}").write_text("invoked")
""".format(
    marker=_MARKER_NAME
)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """#15246: env scrubbed -- an inherited GIT_DIR would point these calls at
    the real repository instead of the throwaway one under tmp_path."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check, env=scrubbed_git_env())


def _seed_repo(tmp_path: Path, *, name: str, branch: str) -> Path:
    """A throwaway repo carrying the real post-merge-doc-sync hook, a stub
    indexer in place of the real one (no ChromaDB/embeddings needed), and an
    initial commit on *branch*."""
    repo = tmp_path / name
    (repo / "docs").mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / ".git" / "hooks" / "lib").mkdir(parents=True)

    (repo / "docs" / "placeholder.md").write_text("# Placeholder\n", encoding="utf-8")
    (repo / "tools" / "index_documentation.py").write_text(_INDEXER_STUB, encoding="utf-8")
    (repo / "tools" / "index_documentation.py").chmod(0o755)

    hook_dest = repo / ".git" / "hooks" / "post-merge"
    hook_dest.write_bytes(_HOOK.read_bytes())
    hook_dest.chmod(0o755)
    (repo / ".git" / "hooks" / "lib" / "_common.sh").write_bytes(_COMMON_LIB.read_bytes())

    _git(tmp_path, "init", "--quiet", f"--initial-branch={branch}", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "seed")
    return repo


def _mark_as_origin_tip(repo: Path) -> None:
    """Point `origin/main` at the current HEAD, as a real `git pull` would
    leave it -- without needing an actual remote."""
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head)


def _change_a_doc_and_merge(repo: Path, *, into: str) -> None:
    """Branch off, change a tracked doc, and merge it back into *into* --
    exercising the real `git merge` that fires `.git/hooks/post-merge`."""
    _git(repo, "checkout", "--quiet", "-b", "topic")
    (repo / "docs" / "placeholder.md").write_text("# Placeholder\n\nChanged.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "change a doc")
    _git(repo, "checkout", "--quiet", into)
    _git(repo, "merge", "--quiet", "--no-ff", "-m", "merge topic", "topic")


def _indexer_was_invoked(repo: Path, *, timeout: float = 3.0) -> bool:
    """Poll for the stub's marker file -- the real hook backgrounds the
    indexer with `nohup ... &`, so it has not necessarily written it yet by
    the time the foreground `git merge`/`git commit` call returns."""
    marker = repo / _MARKER_NAME
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            return True
        time.sleep(0.05)
    return marker.exists()


def _seed_bare_remote_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare "upstream" plus a clone with the real hook installed.

    Unlike `_seed_repo`, origin/main here is a real tracking ref that `git
    pull` advances itself -- the positive control needs that: a manually
    faked origin/main can only ever equal a commit chosen before the merge
    exists, and Gate 2 will correctly (but uninterestingly) reject it.
    """
    bare = tmp_path / "upstream.git"
    _git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(bare))

    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "--quiet", str(bare), str(seed))
    (seed / "docs").mkdir()
    (seed / "tools").mkdir()
    (seed / "docs" / "placeholder.md").write_text("# Placeholder\n", encoding="utf-8")
    (seed / "tools" / "index_documentation.py").write_text(_INDEXER_STUB, encoding="utf-8")
    (seed / "tools" / "index_documentation.py").chmod(0o755)
    _git(seed, "config", "user.email", "t@t")
    _git(seed, "config", "user.name", "t")
    _git(seed, "add", "-A")
    _git(seed, "commit", "--quiet", "-m", "seed")
    _git(seed, "push", "--quiet", "origin", "main")

    work = tmp_path / "work"
    _git(tmp_path, "clone", "--quiet", str(bare), str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / ".git" / "hooks" / "lib").mkdir(parents=True, exist_ok=True)
    hook_dest = work / ".git" / "hooks" / "post-merge"
    hook_dest.write_bytes(_HOOK.read_bytes())
    hook_dest.chmod(0o755)
    (work / ".git" / "hooks" / "lib" / "_common.sh").write_bytes(_COMMON_LIB.read_bytes())

    return bare, work


def test_merge_into_main_at_origin_tip_with_doc_changes_invokes_the_indexer(tmp_path):
    """Positive control: the mechanism fires when every gate is satisfied.

    Uses a real bare remote: a "contributor" clone pushes a doc change to
    origin/main, and `work` (the hook-carrying clone, standing in for a
    developer's own main checkout) pulls it -- the same `git pull` that
    fires `post-merge` in production, with origin/main advanced by the
    fetch exactly as it would be there.
    """
    bare, work = _seed_bare_remote_and_clone(tmp_path)

    contributor = tmp_path / "contributor"
    _git(tmp_path, "clone", "--quiet", str(bare), str(contributor))
    _git(contributor, "config", "user.email", "t@t")
    _git(contributor, "config", "user.name", "t")
    (contributor / "docs" / "placeholder.md").write_text("# Placeholder\n\nChanged.\n", encoding="utf-8")
    _git(contributor, "add", "-A")
    _git(contributor, "commit", "--quiet", "-m", "change a doc")
    _git(contributor, "push", "--quiet", "origin", "main")

    _git(work, "pull", "--quiet", "origin", "main")

    assert _indexer_was_invoked(work), "gates were satisfied but the indexer never ran"


def test_merge_on_a_non_main_branch_does_not_invoke_the_indexer(tmp_path):
    """Gate 1: a branch merging into a local ref not named `main` is never
    the trigger, regardless of what it merges or where `origin/main` points."""
    repo = _seed_repo(tmp_path, name="repo", branch="develop")
    _mark_as_origin_tip(repo)
    _change_a_doc_and_merge(repo, into="develop")

    assert not _indexer_was_invoked(repo, timeout=1.0), "a merge on a non-main branch triggered indexing"


def test_merge_into_main_behind_origin_does_not_invoke_the_indexer(tmp_path):
    """Gate 2: a local branch named `main` that never tracked origin's tip
    must not index -- the name alone is not enough (see hook comment)."""
    repo = _seed_repo(tmp_path, name="repo", branch="main")
    # Deliberately do NOT call _mark_as_origin_tip: origin/main is unset, so
    # `git rev-parse origin/main` fails and Gate 2's HEAD-equality check
    # cannot pass by construction.
    _change_a_doc_and_merge(repo, into="main")

    assert not _indexer_was_invoked(repo, timeout=1.0), "a local-only main (no origin/main) triggered indexing"


def test_plain_commit_on_a_fresh_feature_branch_does_not_invoke_the_indexer(tmp_path):
    """The contamination scenario itself: a worktree's first commit is a
    plain `git commit`, never a merge -- so `post-merge` (unlike the old
    `post-commit` wiring) cannot fire at all, on any branch."""
    repo = _seed_repo(tmp_path, name="repo", branch="issue-99999-fresh-worktree")
    _mark_as_origin_tip(repo)

    (repo / "CLAUDE.md").write_text("# Rules\n\nChanged.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "first commit in a fresh worktree")

    assert not _indexer_was_invoked(repo, timeout=1.0), "a plain commit (no merge) triggered indexing"


def test_post_commit_hook_no_longer_chains_to_doc_sync():
    """Structural check on the real, currently-installed hook: `post-commit`
    must no longer invoke a doc-sync script (a comment noting the #16934
    move is fine; an actual chain -- `source`/exec of a `*-doc-sync` path
    -- is the regression this guards)."""
    text = _POST_COMMIT.read_text(encoding="utf-8")
    invocation_lines = [
        line
        for line in text.splitlines()
        if "doc-sync" in line.lower() and not line.lstrip().startswith("#")
    ]
    assert not invocation_lines, f"post-commit still invokes doc-sync: {invocation_lines}"


def test_negative_control_the_pre_16934_wiring_would_have_indexed_a_fresh_branch_commit(tmp_path):
    """Proves test_plain_commit_on_a_fresh_feature_branch... is not vacuous.

    Reconstructs the pre-#16934 shape: doc-sync chained into `post-commit`,
    unconditionally (no branch/origin gate -- that gate is exactly what
    #16934 added). Run against the identical fresh-branch commit from the
    positive test above, this WOULD invoke the indexer, confirming the
    scenario the fixed hook now blocks is one the old wiring actually hit.
    """
    repo = _seed_repo(tmp_path, name="repo", branch="issue-99999-fresh-worktree")
    _mark_as_origin_tip(repo)

    # The pre-#16934 defect in one line: no branch check, no origin check,
    # straight to invoking the indexer on every commit.
    old_style_hook = (
        "#!/bin/bash\n"
        'PROJECT_ROOT="$(git rev-parse --show-toplevel)"\n'
        'python3 "$PROJECT_ROOT/tools/index_documentation.py" --incremental\n'
    )
    (repo / ".git" / "hooks" / "post-commit").write_text(old_style_hook, encoding="utf-8")
    (repo / ".git" / "hooks" / "post-commit").chmod(0o755)

    (repo / "CLAUDE.md").write_text("# Rules\n\nChanged.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "first commit in a fresh worktree")

    assert _indexer_was_invoked(repo), "the reconstructed pre-16934 hook did not index -- negative control is broken"
