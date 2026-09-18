# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``post-checkout`` must not revert #16923's pre-commit hook.

Found in review on PR #16938 (which closes #16923). ``scripts/hooks/
post-checkout`` auto-installs/refreshes ``.git/hooks/pre-commit`` on every
branch checkout. Before this fix, section 4 decided "is the installed hook
already wrapped" by grepping it for the literal string ``"Issue #1689"`` -- a
marker that only ever identified ``pre-commit-branch-guard-wrapper``. #16923
added a THIRD kind of pre-commit hook, ``tools/git-hooks/pre-commit`` (branch
guard chained into formatter dispatch, installed by
``scripts/install-git-hooks.sh``), which never contained that string either. So
the very next checkout after installing it, ``post-checkout`` mistook it for
"the raw pre-commit framework, not yet wrapped" and silently overwrote it with
the OLD wrapper -- discarding the formatter dispatch #16923 exists to run. AC2
("the Target Branch Guard must not be traded away for the formatter") held only
inside #16923's own test fixture, which has no ``post-checkout`` hook present,
never in a real checkout with both hooks installed.

The fix drops the marker-string check for this case and instead diffs the
installed hook against ``tools/git-hooks/pre-commit``'s own tracked content --
content-addressed rather than string-matched, so it keeps working across any
future edit to that file with nothing to keep in sync by hand.

Every test here drives the REAL ``scripts/hooks/post-checkout`` against a real
throwaway git repository via ``git checkout`` (never a mock of the hook's
logic), the same harness shape as ``hook_self_sync_atomic_test.py`` uses for
this file's own self-sync section. :func:`test_the_old_detection_condition_
would_have_swapped_the_new_hook_out` is the negative control: it reconstructs
the pre-fix section 4 from the real hook text and proves the exact scenario
the positive tests depend on WOULD have failed against it -- so those tests
are not vacuously true against both the old and the new code.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = repo_root()
_POST_CHECKOUT = _REPO_ROOT / "scripts" / "hooks" / "post-checkout"
_NEW_PRECOMMIT_TEMPLATE = _REPO_ROOT / "tools" / "git-hooks" / "pre-commit"
_OLD_WRAPPER = _REPO_ROOT / "scripts" / "hooks" / "pre-commit-branch-guard-wrapper"

# The section this test rewrites, bounded by two anchors stable across
# unrelated edits: the line the fix's new variable is declared on, and the
# next section's own header comment.
_SECTION4_START = 'WRAPPER_SRC="$GIT_ROOT/scripts/hooks/pre-commit-branch-guard-wrapper"'
_SECTION5_HEADER = (
    "\n\n# ---------------------------------------------------------------------------\n# 5. Inject flock wrapper"
)

# The pre-fix form of section 4 (verbatim, minus the leading WRAPPER_SRC line
# which _SECTION4_START already anchors): grepped the installed hook for
# "Issue #1689" to decide "already wrapped", with no notion of a third,
# #16923-style hook at all. This is what PR #16938 originally shipped, before
# review caught the swap this test guards against.
_PRE_FIX_SECTION4_BODY = """
if [ -d "$HOOKS_DIR" ] && [ -f "$WRAPPER_SRC" ]; then
    PRECOMMIT_HOOK="$HOOKS_DIR/pre-commit"
    FRAMEWORK_HOOK="$HOOKS_DIR/pre-commit.pre-commit-framework"

    # Install wrapper if no hook exists yet (fresh clone)
    if [ ! -f "$PRECOMMIT_HOOK" ] && [ ! -f "$FRAMEWORK_HOOK" ]; then
        if command -v pre-commit > /dev/null 2>&1; then
            pre-commit install > /dev/null 2>&1 || true
            if [ -f "$PRECOMMIT_HOOK" ]; then
                mv "$PRECOMMIT_HOOK" "$FRAMEWORK_HOOK"
                cp "$WRAPPER_SRC" "$PRECOMMIT_HOOK"
                chmod +x "$PRECOMMIT_HOOK" "$FRAMEWORK_HOOK"
            fi
        fi
    # Wrap if current hook is the raw pre-commit framework (no wrapper)
    elif [ -f "$PRECOMMIT_HOOK" ] && ! grep -q "Issue #1689" "$PRECOMMIT_HOOK" 2>/dev/null; then
        mv "$PRECOMMIT_HOOK" "$FRAMEWORK_HOOK"
        cp "$WRAPPER_SRC" "$PRECOMMIT_HOOK"
        chmod +x "$PRECOMMIT_HOOK" "$FRAMEWORK_HOOK"
    # Update stale wrapper if source template has changed (#2519)
    elif [ -f "$PRECOMMIT_HOOK" ] && grep -q "Issue #1689" "$PRECOMMIT_HOOK" 2>/dev/null; then
        # Strip flock block before comparing (flock is injected separately)
        _installed=$(sed '/^# --- AUTOBOT_FLOCK/,/^# --- END AUTOBOT_FLOCK/d' "$PRECOMMIT_HOOK")
        _source=$(cat "$WRAPPER_SRC")
        if [ "$_installed" != "$_source" ]; then
            cp "$WRAPPER_SRC" "$PRECOMMIT_HOOK"
            chmod +x "$PRECOMMIT_HOOK"
        fi
    fi
fi"""


def _git(cwd: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    """#15246: env scrubbed -- an inherited GIT_DIR would point these calls,
    checkout included, at the real repository instead of tmp_path."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check, env=scrubbed_git_env())


def _install(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    os.chmod(path, 0o755)


def _seed_repo(tmp_path: Path, post_checkout_text: str, *, with_new_template: bool) -> Path:
    """A throwaway repo tracking real post-checkout + real wrapper, and
    optionally the real #16923 template -- with a second branch to bounce
    to, so a plain ``git checkout`` triggers post-checkout at all.
    """
    repo = tmp_path / "repo"
    (repo / "tools" / "git-hooks").mkdir(parents=True)
    (repo / "scripts" / "hooks").mkdir(parents=True)
    _install(repo / "scripts" / "hooks" / "post-checkout", post_checkout_text.encode("utf-8"))
    _install(repo / "scripts" / "hooks" / "pre-commit-branch-guard-wrapper", _OLD_WRAPPER.read_bytes())
    if with_new_template:
        _install(repo / "tools" / "git-hooks" / "pre-commit", _NEW_PRECOMMIT_TEMPLATE.read_bytes())
    _git(tmp_path, "init", "--quiet", "--initial-branch=main", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "seed")
    _git(repo, "branch", "other")
    return repo


def _install_live_post_checkout(repo: Path) -> None:
    """Simulates "post-checkout is already the hook running here" -- copies
    the TRACKED copy into .git/hooks, same as a prior checkout would have."""
    live = repo / ".git" / "hooks" / "post-checkout"
    _install(live, (repo / "scripts" / "hooks" / "post-checkout").read_bytes())


def _bounce(repo: Path) -> None:
    """Switches away and back, so post-checkout runs twice."""
    _git(repo, "checkout", "other")
    _git(repo, "checkout", "main")


@pytest.fixture(scope="module")
def post_checkout_text() -> str:
    """The real, fixed post-checkout hook. Read once; every test drives this."""
    assert _POST_CHECKOUT.is_file(), f"FIX THE SWEEP: {_POST_CHECKOUT} is gone -- this guard now checks nothing"
    return _POST_CHECKOUT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pre_fix_post_checkout_text(post_checkout_text: str) -> str:
    """The hook as PR #16938 originally shipped it: section 4 swapped in the
    WRAPPER, not the #16923 template, whenever the installed hook lacked
    "Issue #1689".
    """
    assert (
        _SECTION4_START in post_checkout_text
    ), f"FIX THE SWEEP: {_SECTION4_START!r} absent -- cannot build the pre-fix form"
    assert (
        _SECTION5_HEADER in post_checkout_text
    ), f"FIX THE SWEEP: {_SECTION5_HEADER!r} absent -- cannot bound the pre-fix form"
    start = post_checkout_text.index(_SECTION4_START)
    end = post_checkout_text.index(_SECTION5_HEADER)
    pre_fix = post_checkout_text[:start] + _SECTION4_START + _PRE_FIX_SECTION4_BODY + post_checkout_text[end:]
    assert "NEW_PRECOMMIT_SRC" not in pre_fix, "the pre-fix reconstruction leaked the fix's own new variable"
    return pre_fix


def test_fixture_files_exist() -> None:
    assert _NEW_PRECOMMIT_TEMPLATE.is_file(), f"{_NEW_PRECOMMIT_TEMPLATE} is missing -- this guard has no subject"
    assert _OLD_WRAPPER.is_file(), f"{_OLD_WRAPPER} is missing"


# ---------------------------------------------------------------------------
# The fix: the #16923 hook survives a checkout once it is installed.
# ---------------------------------------------------------------------------


def test_the_installed_formatter_dispatch_hook_survives_a_checkout(tmp_path: Path, post_checkout_text: str) -> None:
    """The exact scenario caught in review on PR #16938: install-git-hooks.sh
    already installed tools/git-hooks/pre-commit, then a plain checkout must
    not touch it."""
    repo = _seed_repo(tmp_path, post_checkout_text, with_new_template=True)
    _install_live_post_checkout(repo)
    _install(repo / ".git" / "hooks" / "pre-commit", _NEW_PRECOMMIT_TEMPLATE.read_bytes())

    _bounce(repo)

    installed = (repo / ".git" / "hooks" / "pre-commit").read_bytes()
    assert installed == _NEW_PRECOMMIT_TEMPLATE.read_bytes(), (
        "post-checkout swapped the #16923 formatter-dispatch hook for something else -- "
        f"got:\n{installed.decode('utf-8', 'replace')[:400]}"
    )
    assert b"Issue #1689" not in installed, "the hook was reverted to the branch-guard-only wrapper"


def test_an_older_copy_of_the_new_template_is_refreshed_not_reverted(tmp_path: Path, post_checkout_text: str) -> None:
    """Proves the fix is not anchored to a marker string: an installed copy
    that predates a hypothetical future edit to tools/git-hooks/pre-commit
    (simulated here by tweaking a comment) is refreshed to the CURRENT
    template, never reverted to the wrapper -- so a later, unrelated edit to
    that file cannot silently reopen this defect."""
    repo = _seed_repo(tmp_path, post_checkout_text, with_new_template=True)
    _install_live_post_checkout(repo)
    older = _NEW_PRECOMMIT_TEMPLATE.read_text(encoding="utf-8").replace(
        "Target Branch Guard, then formatter dispatch", "Target Branch Guard, then formatter dispatch (older wording)"
    )
    assert older != _NEW_PRECOMMIT_TEMPLATE.read_text(encoding="utf-8"), "the tweak did not change the text"
    _install(repo / ".git" / "hooks" / "pre-commit", older.encode("utf-8"))

    _bounce(repo)

    installed = (repo / ".git" / "hooks" / "pre-commit").read_bytes()
    assert installed == _NEW_PRECOMMIT_TEMPLATE.read_bytes(), "a stale copy of the new template was not refreshed"
    assert b"Issue #1689" not in installed, "a stale copy of the new template was reverted to the old wrapper"


def test_a_fresh_clone_installs_the_new_template_directly(tmp_path: Path, post_checkout_text: str) -> None:
    """No pre-commit hook installed at all yet, and the #16923 template
    exists in this checkout -- it is installed directly."""
    repo = _seed_repo(tmp_path, post_checkout_text, with_new_template=True)
    _install_live_post_checkout(repo)
    assert not (repo / ".git" / "hooks" / "pre-commit").exists()

    _bounce(repo)

    installed = (repo / ".git" / "hooks" / "pre-commit").read_bytes()
    assert installed == _NEW_PRECOMMIT_TEMPLATE.read_bytes()


def test_a_real_pre_commit_framework_generated_hook_is_never_clobbered(tmp_path: Path, post_checkout_text: str) -> None:
    """Parity with scripts/install-git-hooks.sh's own exception (#11598):
    a hook `pre-commit install` generated itself already runs the full
    quality suite and must not be replaced by either template."""
    repo = _seed_repo(tmp_path, post_checkout_text, with_new_template=True)
    _install_live_post_checkout(repo)
    framework_hook = "#!/usr/bin/env bash\n# File generated by pre-commit: https://pre-commit.com\nexit 0\n"
    _install(repo / ".git" / "hooks" / "pre-commit", framework_hook.encode("utf-8"))

    _bounce(repo)

    installed = (repo / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert installed == framework_hook, "a real pre-commit-framework-generated hook was overwritten"


# ---------------------------------------------------------------------------
# Existing intended behaviour, unaffected: an old checkout that predates
# #16923 (no tools/git-hooks/pre-commit at all) still wraps a genuinely raw
# hook with the wrapper, exactly as before.
# ---------------------------------------------------------------------------


def test_a_stale_hook_on_an_old_checkout_is_still_wrapped(tmp_path: Path, post_checkout_text: str) -> None:
    repo = _seed_repo(tmp_path, post_checkout_text, with_new_template=False)
    _install_live_post_checkout(repo)
    framework_hook = "#!/usr/bin/env bash\n# File generated by pre-commit: https://pre-commit.com\nexit 0\n"
    _install(repo / ".git" / "hooks" / "pre-commit", framework_hook.encode("utf-8"))

    _bounce(repo)

    installed = (repo / ".git" / "hooks" / "pre-commit").read_bytes()
    assert installed == _OLD_WRAPPER.read_bytes(), (
        "an old checkout with no tools/git-hooks/pre-commit template must still wrap a raw "
        "framework hook with the branch-guard wrapper, same as before this fix"
    )
    backup = repo / ".git" / "hooks" / "pre-commit.pre-commit-framework"
    assert backup.read_text(encoding="utf-8") == framework_hook, "the original raw hook was not preserved as a backup"


# ---------------------------------------------------------------------------
# Negative control: the pre-fix detection condition really did (and, if
# reintroduced, still would) swap the #16923 hook out. Without this, the
# tests above could be passing for an unrelated reason.
# ---------------------------------------------------------------------------


def test_the_old_detection_condition_would_have_swapped_the_new_hook_out(
    tmp_path: Path, pre_fix_post_checkout_text: str
) -> None:
    repo = _seed_repo(tmp_path, pre_fix_post_checkout_text, with_new_template=True)
    _install_live_post_checkout(repo)
    _install(repo / ".git" / "hooks" / "pre-commit", _NEW_PRECOMMIT_TEMPLATE.read_bytes())

    _bounce(repo)

    installed = (repo / ".git" / "hooks" / "pre-commit").read_bytes()
    assert installed != _NEW_PRECOMMIT_TEMPLATE.read_bytes(), (
        "control failed: the pre-fix detection condition did not reproduce the defect -- "
        "the positive tests above are not proving what they claim to"
    )
    assert (
        installed == _OLD_WRAPPER.read_bytes()
    ), "the pre-fix code corrupted the hook in some OTHER way than the documented swap"
