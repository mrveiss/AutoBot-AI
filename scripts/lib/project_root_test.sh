#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/project_root.sh -- canonical root resolution
# (#13149). Run: bash scripts/lib/project_root_test.sh
#
# Hermetic: every case builds a throwaway directory tree under mktemp, so no
# test depends on where this checkout happens to live.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/project_root.sh
source "${HERE}/project_root.sh"

pass=0
fail=0

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "  FAIL: ${name} -- expected [${expected}], got [${actual}]"
    fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# A checkout: both markers. A deployment: .env and no .git.
mkdir -p "${TMP}/main/autobot_shared" "${TMP}/main/.git"
printf 'X=1\n' > "${TMP}/main/.env"

# A worktree under it: both markers, .git is a FILE, and deliberately no .env.
mkdir -p "${TMP}/main/.worktrees/issue-1/autobot_shared/deep"
printf 'gitdir: /elsewhere\n' > "${TMP}/main/.worktrees/issue-1/.git"

mkdir -p "${TMP}/install/autobot_shared"
printf 'X=1\n' > "${TMP}/install/.env"

mkdir -p "${TMP}/bare/sub"

echo "== explicit environment =="
check "AUTOBOT_PROJECT_ROOT wins over inference" \
    "/explicit/root" \
    "$(AUTOBOT_PROJECT_ROOT=/explicit/root autobot_project_root "${TMP}/main")"

echo "== worktree boundary (the #13149 regression) =="
# The worktree has no .env; the main tree above it does. Checking every ancestor
# for .env first would escape the worktree and return the MAIN tree.
check "worktree resolves to itself, not the main tree" \
    "${TMP}/main/.worktrees/issue-1" \
    "$(autobot_project_root "${TMP}/main/.worktrees/issue-1/autobot_shared/deep")"

echo "== the cases that must still work =="
check "checkout root from a nested dir" \
    "${TMP}/main" \
    "$(autobot_project_root "${TMP}/main/autobot_shared")"
check "deployed install matches on .env without .git" \
    "${TMP}/install" \
    "$(autobot_project_root "${TMP}/install/autobot_shared")"
check "falls back to AUTOBOT_BASE_DIR when nothing matches" \
    "/srv/autobot-test" \
    "$(AUTOBOT_BASE_DIR=/srv/autobot-test autobot_project_root "${TMP}/bare/sub")"

echo "== agrees with the Python resolver =="
# The whole point of a second implementation is that it returns the same answer.
py_root="$(cd "${HERE}/../.." && python3 -c \
    'from autobot_shared.paths import project_root; print(project_root())' 2>/dev/null)"
if [ -n "${py_root}" ]; then
    check "shell PROJECT_ROOT == autobot_shared.paths.project_root()" \
        "${py_root}" "${PROJECT_ROOT}"
else
    echo "  SKIP: python3/autobot_shared unavailable"
fi

echo
echo "passed: ${pass}, failed: ${fail}"
[ "${fail}" -eq 0 ]
