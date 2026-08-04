#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# gh-pr-update-body.sh — update a PR body via the REST API
#
# Replaces `gh pr edit --body` which silently fails on repos with classic
# Projects attached (GraphQL deprecation error, exit 1, body unchanged).
#
# Usage:
#   scripts/gh-pr-update-body.sh <PR_NUMBER> "<body text>"
#   scripts/gh-pr-update-body.sh <PR_NUMBER> "$(cat body.md)"
#
# Copyright: mrveiss

set -euo pipefail

REPO="mrveiss/AutoBot-AI"

usage() {
    echo "Usage: $0 <PR_NUMBER> <body>" >&2
    echo "  PR_NUMBER  integer pull-request number" >&2
    echo "  body       new body text (use \"\$(cat file.md)\" for files)" >&2
    exit 1
}

[[ $# -lt 2 ]] && usage

PR_NUMBER="$1"
BODY="$2"

if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
    echo "error: PR_NUMBER must be an integer, got: $PR_NUMBER" >&2
    exit 1
fi

gh api "repos/${REPO}/pulls/${PR_NUMBER}" -X PATCH -f body="${BODY}"
