#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Print a markdown bullet list of the repository's open PRs, excluding one.
# Used by the warn-only runaway detector in
# `.github/workflows/pr-queue-gate.yml` to fill in the "Currently open" section
# of its notice.
#
# #14718: this was inline in the workflow as
#
#     gh pr list --json number,title --jq --argjson skip "$PR_NUMBER" '<expr>'
#
# `gh pr list` has no `--argjson` flag. `gh` consumed `--argjson` as the VALUE
# of `--jq` and then rejected the leftovers as unknown positional arguments, so
# the step died under `set -e` before it could post anything. The detector is
# documented as warn-only and never-blocking; in practice it had never once
# warned, and it failed the check every time the threshold was crossed — which
# is precisely when the PR queue could least afford another red check.
#
# It lives in its own file so the behaviour can be executed by a test rather
# than asserted in a workflow comment (#13880: a guard's own test must run).
#
# Usage: pipeline-scripts/pr-queue-open-list.sh <repo> <pr-number-to-exclude>
#   stdout — the markdown list (empty when no other PR is open)
#   exit 0 — list produced
#   exit 1 — arguments missing, or `gh`/`jq` failed
#
# The CALLER is responsible for making a failure here non-fatal. This script
# reports honestly and does not swallow errors; the workflow decides that a
# broken notice must never block a merge.

set -euo pipefail

REPO="${1:?usage: pr-queue-open-list.sh <repo> <pr-number-to-exclude>}"
SKIP="${2:?usage: pr-queue-open-list.sh <repo> <pr-number-to-exclude>}"

case "$SKIP" in
    '' | *[!0-9]*)
        echo "pr-queue-open-list.sh: PR number must be numeric, got '$SKIP'" >&2
        exit 1
        ;;
esac

# `--argjson` binds $skip as a NUMBER so the `!=` compares like with like;
# `.number` from `gh` is numeric, and a string bound with --arg would never
# match, silently leaving the current PR in its own "currently open" list.
gh pr list --repo "$REPO" --state open --json number,title \
    | jq -r --argjson skip "$SKIP" \
        '[.[] | select(.number != $skip) | "- #\(.number) \(.title)"] | join("\n")'
