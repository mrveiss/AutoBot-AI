# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hook must not rewrite the file it is executing from (#15532).

``scripts/hooks/post-checkout`` self-syncs: it copies its canonical tracked
copy over ``.git/hooks/post-checkout`` whenever the two differ. That target is
the file the running shell is reading. bash does not slurp a script -- it reads
incrementally and remembers a byte offset -- so a plain ``cp`` over the live
path makes the running shell resume at that offset inside different content.
The observed symptom was ``line 163: 0: command not found`` on the checkout
immediately after a hook change merged, i.e. exactly when the new hook most
needs to run correctly.

Asserted on behaviour, not on source text. A grep for ``cp`` would pass on a
hook that had stopped self-syncing altogether -- the same "absent reads as
clean" failure this class keeps producing. So the real hook is driven inside a
throwaway repo, and :func:`test_cp_form_corrupts_the_running_shell` is the
positive control proving the harness can still produce the failure it claims
the fix removes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL = _REPO_ROOT / "scripts" / "hooks" / "post-checkout"

# The line the padding is inserted above -- a top-level statement that opens the
# self-sync block, so inserted comments can never land inside a construct.
_ANCHOR = 'CANONICAL="$GIT_ROOT/scripts/hooks/post-checkout"'

# The atomic form the fix installs, and the pre-fix form it replaced.
_ATOMIC_MARKER = 'INSTALLED_TMP="${INSTALLED}.new"'
_CP_FORM = '        cp "$CANONICAL" "$INSTALLED"\n        chmod +x "$INSTALLED"\n'

# bash's own diagnostics. Verified against real output: a corrupted resume emits
# "syntax error", "unexpected end of file" or "<token>: command not found".
_CORRUPTION = ("command not found", "syntax error", "unexpected")

# Byte offsets are content-dependent, so several shift sizes are tried.
_PADDINGS = (1, 2, 5, 13, 29)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """#15246: env scrubbed -- an inherited GIT_DIR would aim these calls,
    ``checkout`` included, at the real repository instead of tmp_path.
    """
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, env=scrubbed_git_env()
    )


def _pad(text: str, count: int) -> str:
    """Canonical content differing from the installed copy by ``count`` comment
    lines inserted above the self-sync block -- the byte shift that decides
    where a corrupted resume lands.
    """
    filler = "".join(f"# pad {i}\n" for i in range(count))
    return text.replace(_ANCHOR, filler + _ANCHOR, 1)


def _seed(tmp_path: Path) -> Path:
    """A throwaway repo with two branches, so checkouts have somewhere to go."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "init", "--quiet", "--initial-branch=main", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "seed")
    _git(repo, "branch", "other")
    return repo


def _drive(repo: Path, canonical: str, installed: str) -> str:
    """Commit ``canonical`` as the tracked hook, install ``installed`` as the
    running one, then bounce branches so the hook executes and self-syncs.
    Returns everything the two checkouts wrote to stderr.
    """
    tracked = repo / "scripts" / "hooks" / "post-checkout"
    tracked.write_text(canonical, encoding="utf-8")
    tracked.chmod(0o755)
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "canonical")
    live = repo / ".git" / "hooks" / "post-checkout"
    live.write_text(installed, encoding="utf-8")
    live.chmod(0o755)
    return _git(repo, "checkout", "other").stderr + _git(repo, "checkout", "main").stderr


def _corruptions(stderr: str) -> list[str]:
    """The lines in which bash reported executing something it never read."""
    return [line for line in stderr.splitlines() if any(m in line for m in _CORRUPTION)]


@pytest.fixture(scope="module")
def hook_text() -> str:
    """The real canonical hook. Read once; every test below drives this text."""
    assert _CANONICAL.is_file(), f"FIX THE SWEEP: {_CANONICAL} is gone -- this guard now checks nothing"
    return _CANONICAL.read_text(encoding="utf-8")


def test_population_floor_the_hook_still_self_syncs(hook_text: str) -> None:
    """Evaluated before every behavioural assertion below.

    Each of those asserts that driving the hook produces no corruption. If the
    self-sync block were deleted, or the padding anchor renamed, they would all
    pass while exercising nothing -- a collapsed sweep reading as a clean one.
    """
    for token in (_ANCHOR, 'INSTALLED="${COMMON_HOOKS}/post-checkout"', "$INSTALLED"):
        assert token in hook_text, f"FIX THE SWEEP: {token!r} absent -- the self-sync block this guard covers is gone"
    assert len(_pad(hook_text, 3).splitlines()) == len(hook_text.splitlines()) + 3, (
        "FIX THE SWEEP: padding did not change the file, so no byte shift is exercised"
    )


def test_cp_form_corrupts_the_running_shell(tmp_path: Path, hook_text: str) -> None:
    """Positive control: the pre-fix form still reproduces the defect.

    Without this, the atomic-form test could pass because the harness had
    stopped being able to produce a failure at all.
    """
    assert _ATOMIC_MARKER in hook_text, f"FIX THE SWEEP: {_ATOMIC_MARKER!r} absent -- cannot build the pre-fix form"
    start = hook_text.index(_ATOMIC_MARKER)
    end = hook_text.index('rm -f "$INSTALLED_TMP"\n', start) + len('rm -f "$INSTALLED_TMP"\n')
    cp_form = hook_text[:start].rstrip(" ") + _CP_FORM.lstrip() + hook_text[end:]
    repo = _seed(tmp_path)
    corrupted = [p for p in _PADDINGS if _corruptions(_drive(repo, _pad(cp_form, p), cp_form))]
    assert corrupted == list(_PADDINGS), f"control failed: cp form corrupted only at {corrupted}, expected {_PADDINGS}"


def test_atomic_rename_does_not_corrupt_the_running_shell(tmp_path: Path, hook_text: str) -> None:
    """The shipped hook: every shift the cp form corrupts leaves this one intact."""
    repo = _seed(tmp_path)
    for pad in _PADDINGS:
        found = _corruptions(_drive(repo, _pad(hook_text, pad), hook_text))
        assert not found, f"self-overwrite corruption at padding {pad}: {found}"


def test_sync_leaves_no_stale_temp_and_keeps_the_hook_executable(tmp_path: Path, hook_text: str) -> None:
    """The temp file is cleaned up, and the installed hook is never left
    present-but-not-executable (the chmod happens before the rename).
    """
    repo = _seed(tmp_path)
    _drive(repo, _pad(hook_text, 4), hook_text)
    hooks = repo / ".git" / "hooks"
    assert not list(hooks.glob("post-checkout.*")), f"stale temp survived: {list(hooks.glob('post-checkout.*'))}"
    installed = hooks / "post-checkout"
    assert os.access(installed, os.X_OK), "installed hook lost its executable bit across the rename"
    assert installed.read_text(encoding="utf-8") == _pad(hook_text, 4), "self-sync did not install the canonical hook"
