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
get_staged_files() {
    local pattern="$1"
    shift
    if [ "$#" -gt 0 ]; then
        printf '%s\n' "$@"
        return
    fi
    git diff --cached --name-only --diff-filter=ACMRT \
        | grep -E "$pattern" \
        || true
}
