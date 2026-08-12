# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Common shell library for pre-commit hooks (Issue #7185).
#
# Sourced via:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/lib/_common.sh"
#
# Provides:
# - ANSI color codes (RED, YELLOW, GREEN, CYAN, BOLD, NC)
# - get_staged_files <pattern> [argv...]: returns staged files matching regex,
#   with positional-args override per #6785 generic-wrapper convention.

# Exit early if already sourced (idempotent — multiple hooks in pre-commit may share env)
if [ -n "${_AUTOBOT_HOOK_COMMON_LOADED:-}" ]; then
    return 0
fi
_AUTOBOT_HOOK_COMMON_LOADED=1

# ANSI color codes (matching existing hooks pattern).
# Use printf '%b' to interpret these — `echo` won't.
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Get staged files matching a regex pattern, with argv override.
#
# Issue #6785: positional args override the staged-files lookup so that the
# same hook script can be invoked by:
#   - pre-commit (no args, reads `git diff --cached`)
#   - CI wrappers (passes file list explicitly via argv)
#
# Usage:
#   get_staged_files '\.py$' "$@"
#   get_staged_files '^\.github/(workflows|actions)/.*\.ya?ml$' "$@"
# GH#13936: the argv branch used to `printf '%s\n' "$@"` and return WITHOUT
# applying $pattern, so a hook's own file-type filter was silently bypassed in
# CI (which always passes argv) while working correctly in pre-commit (which
# does not). That handed a .vue file to pre-commit-no-direct-redis' Python
# tokenizer, and the resulting IndentationError was reported to the user as
# "1 direct Redis connection(s) found" in a file containing no Redis at all.
# The pattern now applies to both branches, so the two invocation paths agree.
# GH#14151: the no-argv branch used to pipe `git diff --cached` straight into
# `grep ... || true` — the trailing `|| true` swallowed BOTH "grep matched
# nothing" (normal) AND "git diff itself failed" (e.g. a corrupted index)
# identically, returning empty output either way. Every caller's own
# `[ -z "$files" ] && exit 0` then read a broken git as "nothing staged" and
# reported clean. `git diff`'s own exit status is now captured separately so
# a real git failure propagates as get_staged_files' own non-zero return
# (which `set -e` in every caller turns into a hard stop), while an empty-but
# -successful diff still yields empty output via the same `|| true` as before.
get_staged_files() {
    local pattern="$1"
    shift
    if [ "$#" -gt 0 ]; then
        printf '%s\n' "$@" | grep -E "$pattern" || true
        return
    fi
    local diff_output
    diff_output="$(git diff --cached --name-only --diff-filter=ACMRT)" || {
        echo "FATAL: git diff --cached failed — cannot determine staged files, refusing to report clean" >&2
        return 1
    }
    printf '%s\n' "$diff_output" | grep -E "$pattern" || true
}
