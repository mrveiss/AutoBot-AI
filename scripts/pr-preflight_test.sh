#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/pr-preflight.sh -- the local run of the PR gates.
# Run: bash scripts/pr-preflight_test.sh
#
# Each case below corresponds to a gate that has actually gone red in CI, so a
# regression here means the round-trip it exists to prevent comes back.
#
# PREFLIGHT_BASE is pinned to HEAD so the changed-file section finds nothing:
# these tests cover the body/message logic, which is where the recurring
# misses have been. The lint section just shells out to the same tools CI
# runs and has nothing of its own to test.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${HERE}/pr-preflight.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pass=0
fail=0

# Assert that running the script over the given fixtures does (or does not)
# report a failure whose text contains $pattern.
check_reports() {
    local name="$1" expected="$2" pattern="$3" body="$4" message="$5"
    local out
    out=$(PREFLIGHT_BASE=HEAD bash "${SCRIPT}" --issue 9999 \
            ${body:+--body "$body"} ${message:+--message "$message"} 2>&1)
    local actual="no"
    printf '%s' "$out" | grep -q "FAIL.*${pattern}" && actual="yes"
    if [ "$expected" = "$actual" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "  FAIL: ${name} -- expected reported=[${expected}], got [${actual}]"
        printf '%s\n' "$out" | sed 's/^/         /'
    fi
}

# ---------------------------------------------------------------- fixtures

GOOD_BODY="${TMP}/good_body.md"
cat > "${GOOD_BODY}" <<'EOF'
Closes #9999

## Thinking Path
Why.

## What Changed
What.

## Verification
Evidence.

## Model Used
A model.
EOF

# The exact shape that failed CI: heading present, content only a placeholder
# comment. The awk extraction strips comments, so this is empty.
PLACEHOLDER_BODY="${TMP}/placeholder_body.md"
sed 's/^What\.$/<!-- describe the change -->/' "${GOOD_BODY}" > "${PLACEHOLDER_BODY}"

NO_KEYWORD_BODY="${TMP}/no_keyword_body.md"
sed 's/^Closes #9999$/Relates to issue 9999./' "${GOOD_BODY}" > "${NO_KEYWORD_BODY}"

MISSING_SECTION_BODY="${TMP}/missing_section_body.md"
grep -v -e '^## Verification$' -e '^Evidence\.$' "${GOOD_BODY}" > "${MISSING_SECTION_BODY}"

GOOD_MSG="${TMP}/good_msg.txt"
printf 'fix(scope): do the thing (#9999)\n\nBody text.\n' > "${GOOD_MSG}"

BACKTICK_MSG="${TMP}/backtick_msg.txt"
printf 'fix(scope): do the thing (#9999)\n\nSee the `run_it` helper.\n' > "${BACKTICK_MSG}"

BAD_SUBJECT_MSG="${TMP}/bad_subject_msg.txt"
printf 'made some changes\n\nBody text.\n' > "${BAD_SUBJECT_MSG}"

TRAILER_MSG="${TMP}/trailer_msg.txt"
printf 'fix(scope): do the thing (#9999)\n\nBody.\n\nCo-Authored-By: Someone <a@b.c>\n' > "${TRAILER_MSG}"

# ---------------------------------------------------------------- PR body

echo "== PR body =="
check_reports "good body passes template check" \
    "no" "section" "${GOOD_BODY}" ""
check_reports "placeholder-only section is caught" \
    "yes" "What Changed" "${PLACEHOLDER_BODY}" ""
check_reports "missing section is caught" \
    "yes" "Verification" "${MISSING_SECTION_BODY}" ""
check_reports "good body carries a close keyword" \
    "no" "Closes/Fixes/Refs" "${GOOD_BODY}" ""
check_reports "missing close keyword is caught" \
    "yes" "Closes/Fixes/Refs" "${NO_KEYWORD_BODY}" ""

# ---------------------------------------------------------------- commit message

echo "== commit message =="
check_reports "good message passes" \
    "no" "backtick" "" "${GOOD_MSG}"
check_reports "backtick is caught" \
    "yes" "backtick" "" "${BACKTICK_MSG}"
check_reports "malformed subject is caught" \
    "yes" "subject does not match" "" "${BAD_SUBJECT_MSG}"
check_reports "good subject is accepted" \
    "no" "subject does not match" "" "${GOOD_MSG}"
check_reports "authorship trailer is caught" \
    "yes" "authorship trailer" "" "${TRAILER_MSG}"
check_reports "clean message has no trailer reported" \
    "no" "authorship trailer" "" "${GOOD_MSG}"

# ---------------------------------------------------------------- fleet IP rule

echo "== fleet IP rule =="
# The range is never written here -- it is read from the same lint rule the
# script reads, so this test cannot drift from the rule it is checking.
FLEET_RULE="$(cd "${HERE}/.." && pwd)/tools/lint/check_no_hardcoded_ip_fallbacks.py"
if [ -r "${FLEET_RULE}" ]; then
    derived=$(grep -oE '\^[0-9]{1,3}\\\.[0-9]{1,3}\\\.[0-9]{1,3}\\\.' "${FLEET_RULE}" \
              | head -1 | sed 's/^\^//' | sed 's/\\\././g')
    if [ -n "${derived}" ]; then
        pass=$((pass + 1))
        fleet_body="${TMP}/fleet_body.md"
        sed "s/^Why\.$/Deployed at ${derived}9 for testing./" "${GOOD_BODY}" > "${fleet_body}"
        check_reports "fleet IP in body is caught" \
            "yes" "fleet IP" "${fleet_body}" ""
        # Loopback and RFC-1918 example space are legitimate per the lint rule's
        # own stated convention -- flagging them would make the script cry wolf.
        loopback_body="${TMP}/loopback_body.md"
        sed 's/^Why\.$/Bound to 127.0.0.1 and 192.168.1.5 in the example./' "${GOOD_BODY}" > "${loopback_body}"
        check_reports "loopback and example space are not flagged" \
            "no" "fleet IP" "${loopback_body}" ""
    else
        fail=$((fail + 1))
        echo "  FAIL: fleet regex derivation -- got nothing from ${FLEET_RULE}"
    fi
else
    echo "  SKIP: ${FLEET_RULE} not readable"
fi

# ---------------------------------------------------------------- result

echo ""
echo "passed: ${pass}  failed: ${fail}"
[ "${fail}" -eq 0 ] || exit 1
