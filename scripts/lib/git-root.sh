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

# Mirrors `autobot_shared.paths.AMBIENT_GIT_VARS` -- keep the two lists in
# sync; a variable added to one side and not the other reopens the hole on
# whichever language was missed.
GIT_ROOT_AMBIENT_VARS=(GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE)

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
