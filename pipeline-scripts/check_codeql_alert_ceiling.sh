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

# --paginate: the API caps a page at 100, and the count is the whole point.
open_json=$(gh api --paginate "repos/${REPO}/code-scanning/alerts?state=open&per_page=100" 2>/dev/null) \
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
