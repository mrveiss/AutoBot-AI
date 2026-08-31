#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/git-root.sh -- the shared shell root resolver
# (#15245). Run: bash scripts/lib/git-root_test.sh
#
# Hermetic: builds a real throwaway repository under mktemp, then reproduces
# the exact ambient environment a pre-commit/pre-push hook hands its children
# on this repository -- GIT_DIR exported, GIT_WORK_TREE unset -- and asserts
# git_repo_root() still names the real root from a subdirectory. Deliberately
# also runs the RAW, unscrubbed call under the same ambient environment first:
# without that contrast, a git version where the defect no longer reproduces
# would make every assertion below pass by there being nothing left to catch,
# which is exactly the "reported clean, read nothing" failure #15176/#15245
# exist to stop (mirrors repo_tests/git_repo_root_scrub_test.py's
# `_require_the_defect_is_reproducible`).

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/git-root.sh
source "${HERE}/git-root.sh"

# This suite is itself registered with repo_tests/shell_lib_test.py and run
# under pytest from the pre-push hook -- which is exactly a process that
# exports GIT_DIR. Left ambient, it corrupts the very `git init` below (git
# writes wherever GIT_DIR points, not "${REPO}"), so every assertion that
# follows would be testing a broken fixture rather than the helper. Scrubbed
# once, up front, same as scripts/install-git-hooks.sh -- GIT_ROOT_AMBIENT_VARS
# so this list can never drift from git-root.sh's own.
unset "${GIT_ROOT_AMBIENT_VARS[@]}"

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

check_status() {
    local name="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "  FAIL: ${name} -- expected exit [${expected}], got [${actual}]"
    fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

REPO="${TMP}/repo"
mkdir -p "${REPO}/sub"
(
    cd "${REPO}" || exit 1
    git init --quiet .
    git config user.email t@t
    git config user.name t
    printf 'x\n' >file.txt
    git add -A
    git commit --quiet --no-verify -m seed
)

echo "== the ordinary cases =="
check "resolves from the repo root itself" "${REPO}" "$(git_repo_root "${REPO}")"
check "resolves from a subdirectory" "${REPO}" "$(git_repo_root "${REPO}/sub")"
check "resolves the CWD when no argument is given" "${REPO}" "$(cd "${REPO}/sub" && git_repo_root)"

echo "== outside any checkout, it fails rather than guesses =="
OUTSIDE="${TMP}/not-a-repo"
mkdir -p "${OUTSIDE}"
git_repo_root "${OUTSIDE}"
check_status "no output on failure" "" "$(git_repo_root "${OUTSIDE}" 2>/dev/null)"
(git_repo_root "${OUTSIDE}" >/dev/null 2>&1)
check_status "non-zero exit outside a checkout" "1" "$?"

echo "== the ambient GIT_DIR reproduction (the #15245 regression) =="
ABS_GIT_DIR="$(cd "${REPO}" && git rev-parse --absolute-git-dir)"

RAW="$(cd "${REPO}/sub" && GIT_DIR="${ABS_GIT_DIR}" git rev-parse --show-toplevel 2>/dev/null)"
if [ "${RAW}" != "${REPO}/sub" ]; then
    echo "  SKIP: this git no longer answers the CWD under a bare GIT_DIR (got [${RAW}]) -- nothing to reproduce"
else
    echo "  (contrast) raw --show-toplevel under ambient GIT_DIR answered [${RAW}], not the root -- this is the defect"
    check "git_repo_root ignores the ambient GIT_DIR" \
        "${REPO}" \
        "$(cd "${REPO}/sub" && GIT_DIR="${ABS_GIT_DIR}" git_repo_root)"
fi

echo
echo "git-root: ${pass} passed, ${fail} failed"
[ "${fail}" -eq 0 ]
