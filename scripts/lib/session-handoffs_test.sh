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
# repository is never touched.

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

# An empty .session/ is not an error.
reap_session_handoffs "${TMP_REPO}/no-such-dir" >/dev/null && r=ok || r=failed
check "missing session dir is not an error" "ok" "$r"

popd >/dev/null || exit 1

echo ""
echo "passed=${pass} failed=${fail}"
[ "$fail" -eq 0 ]
