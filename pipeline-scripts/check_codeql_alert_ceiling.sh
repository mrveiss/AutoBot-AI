#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Fail when the repository carries more open CodeQL alerts than its ceiling.
#
# The ceiling and the reasoning live in pipeline-scripts/codeql_alert_ceiling.txt.
# Short version: CodeQL already found the defects (#17300); nothing required
# anyone to adjudicate them, so 111 accumulated and an arbitrary file write hid
# among them. This makes the backlog unable to grow (#15333).
#
# FAIL-CLOSED. Every way of not getting an answer is a failure, never a pass:
# no token, an API error, a non-numeric body. "Could not look" and "found
# nothing" must not produce the same green tick — that confusion is the whole
# reason this file exists.

set -uo pipefail

CEILING_FILE="${CEILING_FILE:-pipeline-scripts/codeql_alert_ceiling.txt}"
REPO="${GITHUB_REPOSITORY:-mrveiss/AutoBot-AI}"

fail() { printf '[codeql-ceiling] FAIL: %s\n' "$*" >&2; exit 1; }

[ -r "$CEILING_FILE" ] || fail "no ceiling file at '$CEILING_FILE' — refusing to report a pass on an unrun check"

# Exactly one value, and outer whitespace only. `head -1` accepted a file with a
# second number silently below the first, and `tr -d [:space:]` turned "9 0"
# into "90" -- both make a malformed ceiling into a MORE permissive one, which
# is the direction that matters (#17303 review).
mapfile -t ceiling_values < <(grep -vE '^[[:space:]]*(#|$)' "$CEILING_FILE")
[ "${#ceiling_values[@]}" -eq 1 ] \
  || fail "expected exactly one value in $CEILING_FILE, found ${#ceiling_values[@]}: ${ceiling_values[*]}"
ceiling="${ceiling_values[0]}"
ceiling="${ceiling#"${ceiling%%[![:space:]]*}"}"   # trim leading
ceiling="${ceiling%"${ceiling##*[![:space:]]}"}"   # trim trailing -- OUTER only, so "9 0" stays "9 0" and is rejected
[[ "$ceiling" =~ ^[0-9]+$ ]] || fail "ceiling '${ceiling_values[0]}' in $CEILING_FILE is not a number"

# THE REF UNDER TEST, not the default branch (#18065). Without a `ref` the API
# answers for the DEFAULT BRANCH, so this gate counted main's backlog whatever
# the pull request contained. That made it unable to validate the one thing it
# demands: a PR that removes an alert still read main's count and still failed,
# so the only way to go green was to be merged already. Three fixes were
# attempted against a check that could not see any of them.
#
# On a `pull_request` run GITHUB_REF is `refs/pull/<n>/merge`, which is the ref
# CodeQL uploads a PR analysis against; on a push it is `refs/heads/<branch>`.
# ALERT_REF overrides both, for local runs and for the tests.
ALERT_REF="${ALERT_REF:-${GITHUB_REF:-}}"

alerts_query="repos/${REPO}/code-scanning/alerts?state=open&per_page=100"
if [ -n "$ALERT_REF" ]; then
  # FAIL CLOSED ON AN UNSCANNED REF. An empty alert list is returned both for
  # "scanned, nothing found" and for "never scanned", and this script exists
  # because those must not share a green tick. So the analysis must be shown to
  # EXIST before a 0 from that ref is believed.
  analyses_json=$(gh api "repos/${REPO}/code-scanning/analyses?ref=${ALERT_REF}&per_page=100" 2>/dev/null) \
    || fail "could not read code-scanning analyses for ${ALERT_REF} (token scope, or the API errored)"
  # "An analysis exists for this ref" was NOT enough, and that was a fail-open in
  # the first version of this scoping. A pull request ref keeps its analyses when
  # a new commit lands, so a STALE scan of the previous commit satisfied it; and
  # any other tool uploading SARIF to the same ref satisfied it too. Both let the
  # gate count alerts that do not describe the commit under test.
  #
  # So the analysis must be CodeQL's AND must name the commit being tested.
  # GITHUB_SHA on a `pull_request` run is the merge-ref commit the analysis is
  # recorded against, which is what makes this comparable.
  analyses_count=$(printf '%s' "$analyses_json" | jq -e --arg sha "${GITHUB_SHA:-}" '
    if type != "array" then error("expected an array of analyses")
    elif $sha == "" then [.[] | select(.tool.name == "CodeQL")] | length
    else [.[] | select(.tool.name == "CodeQL" and .commit_sha == $sha)] | length
    end
  ' 2>/dev/null)
  [[ "$analyses_count" =~ ^[0-9]+$ ]] \
    || fail "the analyses API did not return a list for ${ALERT_REF} (an error body, or an empty response)"
  if [ -z "${GITHUB_SHA:-}" ]; then
    printf '[codeql-ceiling] GITHUB_SHA unset — the analysis commit is NOT verified\n'
  fi
  [ "$analyses_count" -gt 0 ] \
    || fail "no CodeQL analysis for ${ALERT_REF}${GITHUB_SHA:+ at commit ${GITHUB_SHA}} — refusing to report 0 open alerts for a ref that was never scanned (a stale or non-CodeQL analysis does not count)"
  alerts_query="${alerts_query}&ref=${ALERT_REF}"
  printf '[codeql-ceiling] counting alerts on %s\n' "$ALERT_REF"
else
  printf '[codeql-ceiling] no ref available — counting the default branch\n'
fi

# --paginate: the API caps a page at 100, and the count is the whole point.
open_json=$(gh api --paginate "$alerts_query" 2>/dev/null) \
  || fail "could not read code-scanning alerts for ${REPO} (token missing the security-events scope, or the API errored)"

# Every page must BE an array before anything is counted. `jq -s 'add | length'`
# returns a number for any JSON: an API error object with nine keys counted as
# nine alerts, which at a ceiling of nine PASSED. A gate that accepts an error
# body as a clean result is the exact failure this script was written to prevent,
# so it was doing it to itself (#17303 review).
count=$(printf '%s' "$open_json" | jq -es '
  if length > 0 and all(.[]; type == "array")
  then map(length) | add
  else error("expected one or more JSON arrays, got something else")
  end
' 2>/dev/null)
[[ "$count" =~ ^[0-9]+$ ]] \
  || fail "the alerts API did not return a list of alerts (an error body, or an empty response)"

printf '[codeql-ceiling] %s open alert(s), ceiling %s\n' "$count" "$ceiling"

if [ "$count" -gt "$ceiling" ]; then
  printf '%s\n' "" >&2
  printf '[codeql-ceiling] FAIL: the open-alert backlog GREW: %s > %s\n' "$count" "$ceiling" >&2
  printf '%s\n' "" >&2
  printf '  Every alert must end FIXED, or DISMISSED WITH A WRITTEN REASON.\n' >&2
  printf '  A dismissal with no reasoning is not adjudication.\n' >&2
  printf '%s\n' "" >&2
  printf '  gh api "repos/%s/code-scanning/alerts?state=open&per_page=100" \\\n' "$REPO" >&2
  printf '    --jq %s.[]|\\"\\\\(.number) \\\\(.rule.id) \\\\(.most_recent_instance.location.path)\\"%s\n' "'" "'" >&2
  printf '%s\n' "" >&2
  printf '  Then lower the number in %s in the same change.\n' "$CEILING_FILE" >&2
  exit 1
fi

if [ "$count" -lt "$ceiling" ]; then
  printf '[codeql-ceiling] FAIL: %s open alert(s) is BELOW the ceiling of %s.\n' "$count" "$ceiling" >&2
  printf '  Lower it to %s in %s — a ceiling left above the real count re-licenses\n' "$count" "$CEILING_FILE" >&2
  printf '  exactly the alerts that were just adjudicated, which is how the backlog grew before.\n' >&2
  exit 1
fi

printf '[codeql-ceiling] OK\n'
