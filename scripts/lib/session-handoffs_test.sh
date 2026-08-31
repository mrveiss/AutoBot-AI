#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/session-handoffs.sh -- the #13848 handoff reaper.
# Run: bash scripts/lib/session-handoffs_test.sh
#
# Hermetic: a throwaway git repo per run, no network, no `gh`, and the real
# repository is never touched -- which depends on scrubbing the git
# environment first. An inherited GIT_DIR (exactly what a pre-commit/pre-push
# hook hands its children) is honoured over `-C`'s directory, so without this
# the `git -C "$TMP_REPO" init/add/commit/branch/checkout` calls below write
# to the REAL repository's real refs while treating $TMP_REPO as its work
# tree (#15246): reproduced live while fixing #15245, where the sibling
# suite git-scope_test.sh did exactly this and left a stray commit and
# config on the checkout's shared .git/config before this file was audited
# too. Same scrub as .claude/hooks/block-dangerous-commands_test.sh.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/session-handoffs.sh
source "${HERE}/session-handoffs.sh"

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

echo "== handoff_branch_name =="
check "issue branch"     "issue-1234"                "$(handoff_branch_name '.session/HANDOFF-issue-1234.md')"
check "slug branch"      "chore-triage-umbrellas"    "$(handoff_branch_name '/tmp/x/HANDOFF-chore-triage-umbrellas.md')"
check "suffixed branch"  "issue-14111-stable-shard"  "$(handoff_branch_name 'HANDOFF-issue-14111-stable-shard.md')"

echo "== handoff_status =="
TMP_STATUS="$(mktemp -d)"
trap 'rm -rf "${TMP_STATUS}" "${TMP_REPO:-}"' EXIT
printf '# Handoff: a\nstatus: complete\npr: #1\n'                > "${TMP_STATUS}/plain.md"
printf '# Handoff: b\nstatus: complete (design phase only)\n'    > "${TMP_STATUS}/qualified.md"
printf '# Handoff: c\nStatus: BLOCKED\nblocked_on: review\n'     > "${TMP_STATUS}/blocked.md"
printf '# Handoff: d\nstatus: partial\n'                         > "${TMP_STATUS}/partial.md"
printf '# Handoff: e\nno status field here\n'                    > "${TMP_STATUS}/nostatus.md"
check "plain status"      "complete" "$(handoff_status "${TMP_STATUS}/plain.md")"
check "qualified status"  "complete" "$(handoff_status "${TMP_STATUS}/qualified.md")"
check "mixed-case status" "blocked"  "$(handoff_status "${TMP_STATUS}/blocked.md")"
check "partial status"    "partial"  "$(handoff_status "${TMP_STATUS}/partial.md")"
check "missing status"    ""         "$(handoff_status "${TMP_STATUS}/nostatus.md")"
check "missing file"      ""         "$(handoff_status "${TMP_STATUS}/does-not-exist.md")"

# The template-paste family. `.session/README.md` documents the schema as a
# literal `status: complete | blocked | partial` line, so a half-written handoff
# routinely contains that string alongside the real field. A first-match search
# reads the template and reaps unlanded work; these pin the scoping that stops
# it. Every ambiguous shape must yield "" -- which routes to keep-unlanded.
printf '# Handoff: f\n```markdown\n# Handoff: <branch-name>\nstatus: complete | blocked | partial\n```\nstatus: blocked\nblocked_on: review\n' \
    > "${TMP_STATUS}/fenced-schema-above.md"
printf '# Handoff: g\nstatus: complete | blocked | partial\nstatus: blocked\n' \
    > "${TMP_STATUS}/two-status-lines.md"
printf '# Handoff: h\nstatus: complete | blocked | partial\npr: #1\n' \
    > "${TMP_STATUS}/schema-only.md"
printf '# Handoff: i\npr: #1\n\nNotes for the reader:\nstatus: complete\n' \
    > "${TMP_STATUS}/status-in-prose.md"
printf '# Handoff: j\nstatus: complete\npr: #1\n\nSchema, for reference:\n```markdown\nstatus: complete | blocked | partial\n```\n' \
    > "${TMP_STATUS}/fenced-schema-below.md"
check "fenced schema above the real field" "blocked"  "$(handoff_status "${TMP_STATUS}/fenced-schema-above.md")"
check "two competing status lines"         ""         "$(handoff_status "${TMP_STATUS}/two-status-lines.md")"
check "unfilled schema alternation"        ""         "$(handoff_status "${TMP_STATUS}/schema-only.md")"
check "status only in later prose"         ""         "$(handoff_status "${TMP_STATUS}/status-in-prose.md")"
check "fenced schema below the real field" "complete" "$(handoff_status "${TMP_STATUS}/fenced-schema-below.md")"

echo "== reaper, against a throwaway repo =="
# The deliberate-failure check the issue asks for: a handoff for a branch that
# exists must survive; the same handoff must be reaped once the branch is gone.
TMP_REPO="$(mktemp -d)"
git -C "$TMP_REPO" init -q -b Dev_new_gui
git -C "$TMP_REPO" config user.email t@example.invalid
git -C "$TMP_REPO" config user.name t
echo seed > "${TMP_REPO}/seed.txt"
git -C "$TMP_REPO" add seed.txt
git -C "$TMP_REPO" commit -qm seed
git -C "$TMP_REPO" branch issue-live

mkdir -p "${TMP_REPO}/.session"
printf '# Handoff: issue-live\nstatus: complete\n'     > "${TMP_REPO}/.session/HANDOFF-issue-live.md"
printf '# Handoff: issue-gone\nstatus: complete\n'     > "${TMP_REPO}/.session/HANDOFF-issue-gone.md"
printf '# Handoff: issue-stuck\nstatus: blocked\n'     > "${TMP_REPO}/.session/HANDOFF-issue-stuck.md"
printf '# Handoff: issue-half\nstatus: partial\n'      > "${TMP_REPO}/.session/HANDOFF-issue-half.md"
printf '# Handoff: issue-mute\nnothing parseable\n'    > "${TMP_REPO}/.session/HANDOFF-issue-mute.md"

pushd "$TMP_REPO" >/dev/null || exit 1

check "live branch keeps its handoff"    "keep-live"     "$(handoff_disposition .session/HANDOFF-issue-live.md)"
check "gone+complete is reapable"        "reap"          "$(handoff_disposition .session/HANDOFF-issue-gone.md)"
check "gone+blocked is stranded"         "keep-unlanded" "$(handoff_disposition .session/HANDOFF-issue-stuck.md)"
check "gone+partial is stranded"         "keep-unlanded" "$(handoff_disposition .session/HANDOFF-issue-half.md)"
check "gone+unparseable is stranded"     "keep-unlanded" "$(handoff_disposition .session/HANDOFF-issue-mute.md)"

# --dry-run must not touch the filesystem.
reap_session_handoffs .session --dry-run >/dev/null
check "dry-run deletes nothing" "5" "$(find .session -name 'HANDOFF-*.md' | wc -l | tr -d ' ')"

reap_session_handoffs .session >/dev/null
check "only the landed one is reaped" "4" "$(find .session -name 'HANDOFF-*.md' | wc -l | tr -d ' ')"
[ -f .session/HANDOFF-issue-gone.md ] && r=present || r=absent
check "reaped file is gone"    "absent"  "$r"
[ -f .session/HANDOFF-issue-live.md ] && r=present || r=absent
check "live handoff survives"  "present" "$r"
[ -f .session/HANDOFF-issue-stuck.md ] && r=present || r=absent
check "blocked handoff survives" "present" "$r"

# Deliberate failure: delete the live branch, re-run, and the survivor is reaped.
git branch -D issue-live -q
reap_session_handoffs .session >/dev/null
[ -f .session/HANDOFF-issue-live.md ] && r=present || r=absent
check "handoff reaped once its branch is deleted" "absent" "$r"

# A remote-only branch must also count as live.
git update-ref refs/remotes/origin/issue-remote "$(git rev-parse HEAD)"
printf '# Handoff: issue-remote\nstatus: complete\n' > .session/HANDOFF-issue-remote.md
check "remote-only branch keeps its handoff" "keep-live" "$(handoff_disposition .session/HANDOFF-issue-remote.md)"

# The branch name comes from the filename, so a case mismatch between the two
# must not read as "branch gone" -- git refs are case-sensitive, the filesystem
# convention is not.
git checkout -q -b Issue-MixedCase
git checkout -q Dev_new_gui
printf '# Handoff: x\nstatus: complete\n' > .session/HANDOFF-issue-mixedcase.md
check "case-mismatched filename still sees a live branch" "keep-live" \
    "$(handoff_disposition .session/HANDOFF-issue-mixedcase.md)"
git branch -D Issue-MixedCase -q
check "genuinely gone after the case-insensitive pass too" "reap" \
    "$(handoff_disposition .session/HANDOFF-issue-mixedcase.md)"
rm -f .session/HANDOFF-issue-mixedcase.md

# git failing to answer is not the same as "the branch is gone". `git show-ref`
# exits 1 for a missing ref and >=2 for a hard error, and treating the second as
# the first lets one broken git call reap the whole directory in a single sweep.
NON_REPO="$(mktemp -d)"
cp .session/HANDOFF-issue-remote.md "${NON_REPO}/HANDOFF-issue-remote.md"
pushd "${NON_REPO}" >/dev/null || exit 1
handoff_branch_exists issue-remote 2>/dev/null
check "git error is not a negative answer" "2" "$?"
check "unresolvable branch is never reaped" "keep-unknown" \
    "$(handoff_disposition "${NON_REPO}/HANDOFF-issue-remote.md" 2>/dev/null)"
reap_session_handoffs "${NON_REPO}" >/dev/null 2>&1
[ -f "${NON_REPO}/HANDOFF-issue-remote.md" ] && r=present || r=absent
check "handoff survives an unanswerable branch check" "present" "$r"
popd >/dev/null || exit 1
rm -rf "${NON_REPO}"

# Control-flow guard (structural, not behavioural): Phase 4 must never run on
# refs a failed fetch left stale, because "branch is gone" is then a lie.
CW="${HERE}/../cleanup-worktrees.sh"
grep -q 'REMOTE_REFS_FRESH=false' "$CW" && r=recorded || r=swallowed
check "fetch failure is recorded, not swallowed" "recorded" "$r"
awk '/REMOTE_REFS_FRESH.*!=.*true/ { guard = NR } /reap_session_handoffs/ { if (guard && NR > guard) { print "guarded"; exit } }' \
    "$CW" > "${TMP_STATUS}/guard.txt"
check "reaping is gated on fresh refs" "guarded" "$(cat "${TMP_STATUS}/guard.txt")"

# An empty .session/ is not an error.
reap_session_handoffs "${TMP_REPO}/no-such-dir" >/dev/null && r=ok || r=failed
check "missing session dir is not an error" "ok" "$r"

popd >/dev/null || exit 1

echo ""
echo "passed=${pass} failed=${fail}"
[ "$fail" -eq 0 ]
