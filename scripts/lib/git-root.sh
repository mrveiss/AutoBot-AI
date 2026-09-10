#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Canonical repository-root resolution for shell scripts, asked of git with
# the ambient git environment scrubbed (#15245).
#
# `git rev-parse --show-toplevel` is not safe to call bare. A hook run in a
# **worktree** -- this repository's entire workflow -- is handed
# `GIT_DIR=<main>/.git/worktrees/<name>` and no `GIT_WORK_TREE` (measured on
# git 2.34.1, for both `pre-commit` and `pre-push`). With `GIT_DIR` set and
# `GIT_WORK_TREE` unset, git treats the **current directory** as the work
# tree, so `--show-toplevel` answers with wherever the caller happens to be
# standing rather than the repository root -- wrong without being an error.
# #15176 fixed the five Python sites this way (`autobot_shared.paths.
# git_repo_root`); this is the same fix for shell, gathered into one helper
# rather than pasted at each of the sixteen call sites that needed it.
#
# Source this file -- do not execute it. Resolve it from your own location
# (`${BASH_SOURCE[0]}`), not via `git rev-parse`: that would recreate the
# exact bootstrap problem this file exists to remove.
#
#     source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/git-root.sh"
#     REPO_ROOT="$(git_repo_root)" || { echo "not a git repo" >&2; exit 2; }

# Mirrors `autobot_shared.paths.AMBIENT_GIT_VARS`. The two lists HAD diverged --
# GIT_OBJECT_DIRECTORY and GIT_ALTERNATE_OBJECT_DIRECTORIES were added on the
# Python side only, which is precisely the hole this comment warned about and
# could not prevent (#15877). `repo_tests/ambient_git_vars_mirror_test.py` now
# compares them, so the claim is checked rather than asserted.
GIT_ROOT_AMBIENT_VARS=(GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE \
                       GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES)

# Print the repository root containing DIR (default: the caller's CWD), with
# GIT_ROOT_AMBIENT_VARS unset for the git call. Prints nothing and returns 1
# on failure -- never a guess, so every caller must check the exit status
# rather than trust a possibly-empty string.
git_repo_root() {
    local dir="${1:-.}" root
    root="$(
        unset "${GIT_ROOT_AMBIENT_VARS[@]}"
        git -C "$dir" rev-parse --show-toplevel 2>/dev/null
    )" || return 1
    [ -n "$root" ] || return 1
    printf '%s\n' "$root"
}

# Run `git ls-files` under DIR with GIT_ROOT_AMBIENT_VARS unset. Remaining
# arguments are passed to git verbatim, so every flag and pathspec form works:
# `-v` for index bits, `-- '*.sh'` for a pathspec. Forcing a `--` in here looked
# tidier and silently broke `-v`, turning a flag into a pathspec that matches
# nothing -- an empty result that reads exactly like a clean tree.
#
# DIR is required and always explicit: making it optional would make
# `git_tracked_files '*.sh'` ambiguous between a directory and a pathspec, and
# the wrong reading enumerates the wrong tree -- the defect this helper exists
# to remove, reintroduced through its own API.
#
# `git ls-files` has the same dependency as `--show-toplevel`: an inherited
# GIT_DIR outranks `-C`, so a correct directory still enumerates the *other*
# checkout's index, and answers without erroring (#14896, #15506).
#
# Returns git's own exit status. An empty result with status 0 is a real answer
# -- a pathspec that matches nothing -- and is NOT an error here. Callers that
# require a non-empty set must say so themselves; a floor belongs at the caller,
# where "the tree is clean" and "the sweep lost its reach" are distinguishable.
# That split mirrors tracked_paths()/enforce_reach() on the Python side.
#
#     source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/git-root.sh"
#     files="$(git_tracked_files "$REPO_ROOT" '*.sh')" || exit 2
git_tracked_files() {
    local dir="${1:?git_tracked_files: DIR required}"
    shift
    (
        unset "${GIT_ROOT_AMBIENT_VARS[@]}"
        git -C "$dir" ls-files "$@"
    )
}
