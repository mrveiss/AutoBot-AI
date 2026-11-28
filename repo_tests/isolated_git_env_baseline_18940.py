# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Test files that build git repos without `autobot_shared.isolated_git`, each a PERMANENT exception (#18940).

Owner ruling 2026-10-22: every file outside this list is migrated; the files below stay on their own
environment for good, each for the reason recorded beside it. The list may only SHRINK: a new offender
fails `isolated_git_env_guard_18940_test.py`, and an entry that was migrated (or left the tree) fails
it too until the line is deleted. `FROZEN_TOTAL` caps the length, so adding a line also means raising
a number a reviewer sees, and every row must be a PERMANENT row (the guard checks the prefix).
"""

from __future__ import annotations

PERMANENT_PREFIX = "PERMANENT (owner decision #18940, 2026-10-22): "

ALLOWLIST: dict[str, str] = {
    "autobot-backend/api/git_mcp_env_scrub_15991_test.py": PERMANENT_PREFIX
    + "its subject is an ambient GIT_DIR outranking `-C`; the decoy/validated repos are built with the bare "
    "`scrubbed_git_env()` so the only environment variable in play is the one under test",
    "autobot_shared/git_probe_test.py": PERMANENT_PREFIX
    + "tests `git_probe`, whose contract is that no call shape inherits the ambient env; the fixture "
    "builds with the bare `scrubbed_git_env()` so the probe's own scrub is the only thing exercised",
    "autobot_shared/paths_test.py": PERMANENT_PREFIX
    + "tests `project_root()` resolution against a real main-tree/worktree layout, and `autobot_shared.paths` "
    "is the module `isolated_git` imports its scrub from, so the fixture keeps its own env "
    "(`scrubbed_git_env()` plus null global/system config) and does not depend on a helper built on it",
    "repo_tests/git_repo_root_scrub_test.py": PERMANENT_PREFIX
    + "asserts on the scrub itself (GIT_DIR, GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES), so it "
    "must control exactly which variables reach git rather than take them from a helper",
    "repo_tests/hooks_path_override_15961_test.py": PERMANENT_PREFIX
    + "pins git's DEFAULT hook lookup (`core.hooksPath` unset, shared `$GIT_COMMON_DIR/hooks`) against a "
    "worktree; `isolated_git` documents that it does not force `core.hooksPath`, and the fixture asserts "
    "the key is unset itself, so it keeps a plain scrubbed env",
    "repo_tests/one_git_enumeration_15926_test.py": PERMANENT_PREFIX
    + "tests `tracked_paths`/`exclude=` enumeration against fixtures that demonstrate a GIT_DIR hazard, "
    "so the repo is built with the bare `scrubbed_git_env()` to keep the enumerator the only variable",
    "repo_tests/one_static_data_copy_18556_test.py": PERMANENT_PREFIX
    + "asserts that a global `core.excludesFile` cannot untrack a file in its throwaway tree, i.e. it tests "
    "the hermetic-config behaviour itself with its own null global/system config",
}

#: Caps the length of ALLOWLIST; lower it when an entry goes, never raise it.
FROZEN_TOTAL = 7
