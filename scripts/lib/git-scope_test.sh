#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/git-scope.sh (#13984).
# Run: bash scripts/lib/git-scope_test.sh
#
# These build REAL throwaway repositories rather than stubbing git. The rules
# under test are all about what git actually does with merge commits, shallow
# clones and unresolvable refs, so a stub would only re-assert this file's own
# assumptions about git -- the exact way #13880's four green no-ops survived.
#
# This suite runs `git init`, `git commit` and `git checkout` against tmp
# directories it builds below. An inherited GIT_DIR/GIT_WORK_TREE -- exactly
# what a pre-commit/pre-push hook hands its children -- sends every one of
# those writes to the REAL repository instead (#15246): reproduced live while
# fixing #15245, where an unscrubbed run of this exact file committed onto the
# real checkout and left a stray user.email/core.bare in its shared config.
# Scrub first, same list as .claude/hooks/block-dangerous-commands_test.sh.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/git-scope.sh
source "${HERE}/git-scope.sh"

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
trap 'rm -rf "$TMP"' EXIT

# A repository shaped like a pull_request checkout: base tip, PR head, and the
# MERGE COMMIT of the two checked out as HEAD -- which is what actions/checkout
# produces and what every rule below is really about.
make_merge_repo() {
    local dir="$1"
    mkdir -p "$dir" && cd "$dir" || return 1
    git init --quiet -b main .
    git config user.email t@t; git config user.name t
    echo base0 > base.txt; git add .; git commit --quiet -m "root"
    git checkout --quiet -b feature
    echo feat > feature.py; git add .; git commit --quiet -m "feature"
    git checkout --quiet main
    echo other > other.py; git add .; git commit --quiet -m "another PR landed on base"
    # Captured BEFORE the merge: afterwards `main` IS the merge commit, so
    # comparing against it compares HEAD with itself and finds nothing --
    # a control that silently proves nothing.
    PRE_MERGE_BASE_TIP=$(git rev-parse HEAD)
    git merge --quiet --no-ff feature -m "merge" >/dev/null
    # actions/checkout leaves HEAD detached at the merge commit, and the merge
    # commit is FROZEN for the life of the run while the base branch keeps
    # moving. Modelled explicitly, because that gap is the whole reason
    # origin/<base> is the wrong base to resolve: on a re-run HEAD is the same
    # old merge and origin/<base> is fetched fresh.
    local merge_ref; merge_ref=$(git rev-parse HEAD)
    echo later > later.py; git add .; git commit --quiet -m "a THIRD PR lands while this run is queued"
    BASE_BRANCH_TIP=$(git rev-parse HEAD)
    git checkout --quiet "$merge_ref"
    cd - >/dev/null || return 1
}

echo "== git_scope_resolve_base =="
make_merge_repo "$TMP/merge"
cd "$TMP/merge" || exit 1
base=$(git_scope_resolve_base HEAD)
check "merge ref resolves to HEAD^1" "HEAD^1" "$base"
# The rule this encodes: HEAD^1..HEAD is THIS change set only. The commit that
# landed on the base in between must not appear.
changed=$(git_scope_diff_names "$base" HEAD | tr '\n' ' ')
check "merge-parent range excludes another PR's file" "feature.py " "$changed"
# The control that gives the rule its teeth: resolving the base branch's CURRENT
# tip instead reports `later.py` -- a file this change set never touched -- and
# does NOT report feature.py, which it did. Not merely noisier: wrong in both
# directions. This assertion fails if the resolver is ever weakened to the
# branch-tip route.
via_branch=$(git diff --name-only "$BASE_BRANCH_TIP" HEAD | sort | tr '\n' ' ')
check "control: the branch-tip route reports the WRONG file set" "later.py " "$via_branch"

echo "== git_scope_resolve_base: fallbacks =="
mkdir -p "$TMP/linear" && cd "$TMP/linear" || exit 1
git init --quiet -b main . ; git config user.email t@t; git config user.name t
echo a > a.py; git add .; git commit --quiet -m one
echo b > b.py; git add .; git commit --quiet -m two
payload=$(git rev-parse HEAD~1)
check "event payload base sha is used when there is no merge ref" "$payload" "$(git_scope_resolve_base HEAD "$payload")"
check "falls back to HEAD^ with no payload and no merge ref" "HEAD^" "$(git_scope_resolve_base HEAD)"
check "an unresolvable payload does not win over HEAD^" "HEAD^" "$(git_scope_resolve_base HEAD deadbeefdeadbeefdeadbeefdeadbeefdeadbeef)"

echo "== unresolvable base is FATAL, never 'no changes' =="
mkdir -p "$TMP/root" && cd "$TMP/root" || exit 1
git init --quiet -b main . ; git config user.email t@t; git config user.name t
echo a > a.py; git add .; git commit --quiet -m only
out=$(git_scope_resolve_base HEAD 2>&1); rc=$?
check "root commit: resolve_base fails"  "1" "$rc"
check "root commit: prints nothing on stdout" "" "$(git_scope_resolve_base HEAD 2>/dev/null)"
case "$out" in *"refusing to report an uncomputed scope"*) pass=$((pass+1)) ;; *) fail=$((fail+1)); echo "  FAIL: fatal message missing, got [$out]" ;; esac

echo "== git_scope_resolve_base_explicit: an explicit base is an INSTRUCTION =="
cd "$TMP/merge" || exit 1
# The regression this pins, caught by check-pre-commit-hook-pr_test.py during
# #13984: an explicitly supplied base that does not resolve must be returned
# verbatim so the validation step fails LOUDLY. Treating it as a skippable
# fallback silently substitutes "<head>^" -- a different, smaller scope --
# and reports a successful scan of it.
absent="0000000000000000000000000000000000000000"
check "an explicit base is used verbatim, even when absent" "$absent" \
  "$(git_scope_resolve_base_explicit HEAD "$absent")"
check "no explicit base falls back to the merge rule" "HEAD^1" \
  "$(git_scope_resolve_base_explicit HEAD)"
check "and it is the VALIDATOR that rejects the absent one" "1" \
  "$(git_scope_require_commits "$absent" 2>/dev/null; echo $?)"
# The contrast that gives the rule its teeth: the payload route DOES skip it.
check "control: the payload route skips an absent base" "HEAD^1" \
  "$(git_scope_resolve_base HEAD "$absent")"

echo "== git_scope_require_commits =="
cd "$TMP/linear" || exit 1
git_scope_require_commits HEAD "HEAD^" 2>/dev/null; check "both resolvable -> 0" "0" "$?"
git_scope_require_commits HEAD nope-not-a-ref 2>/dev/null; check "one unresolvable -> 1" "1" "$?"
# Captured into a variable first: under `set -o pipefail` a pipeline's status is
# the rightmost NON-ZERO one, so `git_scope_require_commits ... | grep -q ...`
# reports the (correctly) failing function and the `&& echo` never runs.
msg=$(git_scope_require_commits nope-not-a-ref 2>&1)
case "$msg" in *nope-not-a-ref*) check "names the offending ref" "yes" "yes" ;; *) check "names the offending ref" "yes" "[$msg]" ;; esac

echo "== git_scope_split_range =="
check "two-dot base"    "A"   "$(git_scope_split_range 'A..B' base)"
check "two-dot head"    "B"   "$(git_scope_split_range 'A..B' head)"
check "three-dot base"  "A"   "$(git_scope_split_range 'A...B' base)"
check "three-dot head"  "B"   "$(git_scope_split_range 'A...B' head)"
# The regression this pins: stripping `..` from a three-dot range leaves a
# trailing dot on the base ref, which then does not resolve.
check "three-dot base has no trailing dot" "origin/Dev_new_gui" "$(git_scope_split_range 'origin/Dev_new_gui...HEAD' base)"
git_scope_split_range 'not-a-range' base >/dev/null 2>&1; check "a non-range is fatal" "1" "$?"

echo "== git_scope_diff_names: a failed diff is not an empty diff =="
cd "$TMP/linear" || exit 1
check "pathspec narrows the scope" "b.py" "$(git_scope_diff_names 'HEAD^' HEAD -- '*.py' | tr -d '\n')"
check "a non-matching pathspec yields empty, exit 0" "" "$(git_scope_diff_names 'HEAD^' HEAD -- '*.ts')"
git_scope_diff_names 'HEAD^' HEAD -- '*.ts' >/dev/null 2>&1; check "empty diff still exits 0" "0" "$?"
git_scope_diff_names 'no-such-ref' HEAD >/dev/null 2>&1; check "a failed diff exits non-zero" "1" "$?"

echo "== git_scope_diff_names_symmetric: three-dot excludes the base's own moves =="
cd "$TMP/merge" || exit 1
check "three-dot from base tip sees only this branch's file" "feature.py" \
  "$(git_scope_diff_names_symmetric "$PRE_MERGE_BASE_TIP" feature | tr -d '\n')"

echo "== git_scope_existing_files =="
cd "$TMP/linear" || exit 1
rm -f b.py
check "a deleted path is dropped" "a.py" "$(printf 'a.py\nb.py\n' | git_scope_existing_files | tr -d '\n')"
check "blank lines are dropped"   "a.py" "$(printf '\na.py\n\n' | git_scope_existing_files | tr -d '\n')"

echo "== git_scope_require_nonempty =="
git_scope_require_nonempty 3 'HEAD^1..HEAD' 2>/dev/null; check "non-zero count passes" "0" "$?"
git_scope_require_nonempty 0 'HEAD^1..HEAD' 2>/dev/null; check "zero count is fatal"   "1" "$?"

echo "== git_scope_require_base_ref =="
git_scope_require_base_ref HEAD 2>/dev/null;              check "resolvable base -> 0" "0" "$?"
git_scope_require_base_ref origin/nope 2>/dev/null;       check "missing base -> 1"    "1" "$?"

echo
echo "git-scope: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ] || exit 1
