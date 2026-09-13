# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data module for ``check_git_toplevel_env_scrubbed.ALLOWLIST``.

Split out for the same reason as ``python_file_size_ratchet_baseline`` (#14547):
the checker sits at its 600-line ratchet ceiling, and each entry here carries
several lines of reasoning by design. Holding them in the checker would mean
choosing between a documented exemption and a raised ceiling every time one is
added, and the ceiling is never raised to make a check pass.

Every entry is a call that needs the hook environment **intact** to mean
anything, and every entry states why in the comment above it. An entry without
that reasoning is indistinguishable from a bypass.

Entries are POSIX-relative to the repository root, and the granularity is the
FILE — so an entry exempts any future unscrubbed call in that file too. Where
that matters, name the compensating control in the comment.
"""

from __future__ import annotations

#: Files allowed to call ``--show-toplevel`` with an environment that is NOT
#: scrubbed, POSIX-relative to the repository root. Each entry is a call that
#: needs the hook environment *intact* to mean anything.
ALLOWLIST = {
    # The #15926 contrast fixture. `test_the_scrub_is_what_makes_that_work`
    # runs `git ls-files` UNSCRUBBED under a GIT_DIR pointed at a throwaway
    # repository, and asserts it reads the decoy -- proving this machine can
    # exhibit the hazard before the scrubbed helper is credited with avoiding
    # it. Scrubbing it would make the paired test pass on a machine where
    # GIT_DIR never mattered, which is the "detector proved on nothing" shape
    # this file exists to stop.
    #
    # File-level, like every entry here, so a NEW unscrubbed call in that file
    # would also be exempt. The compensating control is its own census:
    # `MAX_DIRECT_INVOCATIONS` is an equality, and it counts direct
    # `git ls-files` invocations in `repo_tests/` INCLUDING that file, so a
    # second raw call there fails that guard even though this one allows it.
    "repo_tests/one_git_enumeration_15926_test.py",
    # The #15991 contrast fixture. `test_an_unscrubbed_call_does_follow_git_dir_here`
    # runs git UNSCRUBBED under a GIT_DIR pointed at a throwaway repository and
    # asserts it reads the decoy — so the paired test cannot credit the scrub for
    # an absence this machine would have produced anyway. Same reasoning as the
    # #15176 entry below, and caught before pushing this time rather than by base
    # going red.
    "autobot-backend/api/git_mcp_env_scrub_15991_test.py",
    # The #15176 reproduction. It runs git with GIT_DIR deliberately exported
    # to confirm the defect still reproduces on this git version before
    # asserting that the six sites survive it; scrubbing there would make the
    # suite assert nothing and pass.
    "repo_tests/git_repo_root_scrub_test.py",
    # scripts/lib/git-root.sh IS the scrub -- its raw calls ARE the
    # implementations the helpers wrap, each run inside a subshell with
    # GIT_ROOT_AMBIENT_VARS unset: `rev-parse --show-toplevel` under
    # `git_repo_root` (#15245) and `ls-files` under `git_tracked_files`
    # (#15506). Said as a count until the second one arrived, which is the
    # kind of comment that goes quietly wrong -- it is now phrased so adding
    # a third helper does not falsify it.
    "scripts/lib/git-root.sh",
    # #15246 already scrubbed this file's entire process environment
    # (`unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE` up front,
    # ahead of every git call the script makes, not only this one) and that
    # fix is covered by repo_tests/git_hooks_installer_test.py. Converging it
    # onto scripts/lib/git-root.sh would need that test's throwaway fixture
    # -- which copies only this file's bytes, not scripts/lib/ -- to seed the
    # helper too; correct today, tracked as follow-up rather than risked here.
    "scripts/install-git-hooks.sh",
    # The #15245 shell reproduction, same reasoning as the Python one above:
    # it deliberately calls git with GIT_DIR exported, unscrubbed, to prove
    # the defect still reproduces before asserting git_repo_root survives it.
    "scripts/lib/git-root_test.sh",
    # A literal command STRING passed as a test case to the branch-switch
    # guard (#15296) -- not a call this test script itself makes. The guard
    # under test is required to ALLOW exactly this shape.
    ".claude/hooks/block-dangerous-commands_test.sh",
}
