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

ceiling=$(grep -vE '^\s*(#|$)' "$CEILING_FILE" | head -1 | tr -d '[:space:]')
[[ "$ceiling" =~ ^[0-9]+$ ]] || fail "ceiling '$ceiling' in $CEILING_FILE is not a number"

# --paginate: the API caps a page at 100, and the count is the whole point.
open_json=$(gh api --paginate "repos/${REPO}/code-scanning/alerts?state=open&per_page=100" 2>/dev/null) \
  || fail "could not read code-scanning alerts for ${REPO} (token missing the security-events scope, or the API errored)"

count=$(printf '%s' "$open_json" | jq -s 'add | length' 2>/dev/null)
[[ "$count" =~ ^[0-9]+$ ]] || fail "could not count alerts from the API response"

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
