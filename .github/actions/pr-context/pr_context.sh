#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Live pull-request facts for a coordinator-dispatched run (#20825). Contract: action.yml next to this file;
# repo_tests/pr_context_test.py drives this script against a fake `gh`.
#
# Inputs (env): PR_NUMBER, HEAD_SHA, BASE_SHA (the dispatch pins), REPO, RUN_ID, RUN_SHA (github.sha),
# RUNNER_TEMP, GITHUB_OUTPUT, CANCEL_WAIT_SECONDS (default 120). `gh` reads GH_TOKEN.
set -euo pipefail

emit() { printf '%s=%s\n' "$1" "$2" >> "${GITHUB_OUTPUT}"; }
fail() { echo "::error::pr-context: $*" >&2; exit 1; }

# Not a pull-request run (push, schedule, merge_group, a manual run): every output is empty.
if [ -z "${PR_NUMBER:-}" ]; then
  for k in number head-sha base-sha base-ref head-ref head-repo same-repo author author-type draft labels admitted commits title body-file pull-file; do emit "$k" ""; done
  emit is-pr false
  exit 0
fi

[[ "${PR_NUMBER}" =~ ^[0-9]+$ ]] || fail "pr_number '${PR_NUMBER}' is not a number"
[[ "${HEAD_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || fail "head_sha is not a full commit SHA"
[[ "${BASE_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || fail "base_sha is not a full commit SHA"
[ "${BASE_SHA}" != "${HEAD_SHA}" ] || fail "base_sha equals head_sha: the diff would be empty and every gate would pass 'not affected'"

pr="$(gh api "repos/${REPO}/pulls/${PR_NUMBER}")" || fail "cannot read pull request #${PR_NUMBER}"
live_head="$(jq -r '.head.sha' <<<"${pr}")"

# A stale dispatch ENDS CANCELLED, never failed: a failure would publish red required contexts on a commit
# that a newer run is about to judge. The run is force-cancelled; if that does not stop this step, fail closed.
if [ "${RUN_SHA}" != "${HEAD_SHA}" ] || [ "${live_head}" != "${HEAD_SHA}" ]; then
  echo "::notice::stale dispatch: pinned ${HEAD_SHA}, run ${RUN_SHA}, pull request head ${live_head}; cancelling this run"
  gh api -X POST "repos/${REPO}/actions/runs/${RUN_ID}/force-cancel" >/dev/null || fail "could not cancel the stale run"
  sleep "${CANCEL_WAIT_SECONDS:-120}"
  fail "the cancel of a stale dispatch did not take effect"
fi

[ "$(jq -r '.state' <<<"${pr}")" = "open" ] || fail "pull request #${PR_NUMBER} is not open"
base_ref="$(jq -r '.base.ref' <<<"${pr}")"

# The base pin is the merge base: an ancestor of the head AND of the base branch. An older base only widens
# the diff; a base that hides changes is refused.
status() { gh api "repos/${REPO}/compare/$1...$2" --jq '.status' 2>/dev/null || echo unreadable; }
case "$(status "${BASE_SHA}" "${HEAD_SHA}")" in ahead) ;; *) fail "base_sha is not an ancestor of the head" ;; esac
case "$(status "${BASE_SHA}" "${base_ref}")" in ahead|identical) ;; *) fail "base_sha is not on the base branch ${base_ref}" ;; esac

printf '%s\n' "${pr}" > "${RUNNER_TEMP}/pr.json"   # the whole pull request, for scripts that read the payload
jq -r '.body // ""' <<<"${pr}" > "${RUNNER_TEMP}/pr-body.md"   # never an output or an expression: it is untrusted text
emit is-pr true
emit number "${PR_NUMBER}"
emit head-sha "${HEAD_SHA}"
emit base-sha "${BASE_SHA}"
emit base-ref "${base_ref}"
emit head-ref "$(jq -r '.head.ref' <<<"${pr}")"
emit head-repo "$(jq -r '.head.repo.full_name // ""' <<<"${pr}")"
emit same-repo "$(jq -r --arg r "${REPO}" '(.head.repo.full_name // "") == $r' <<<"${pr}")"
emit author "$(jq -r '.user.login' <<<"${pr}")"
emit author-type "$(jq -r '.user.type' <<<"${pr}")"
emit draft "$(jq -r '.draft == true' <<<"${pr}")"
emit labels "$(jq -c '[.labels[].name]' <<<"${pr}")"
emit admitted "$(jq -r '[.labels[].name] | index("land-next") != null' <<<"${pr}")"
emit commits "$(jq -r '.commits' <<<"${pr}")"
emit title "$(jq -r '.title' <<<"${pr}" | tr -d '\r\n')"
emit body-file "${RUNNER_TEMP}/pr-body.md"
emit pull-file "${RUNNER_TEMP}/pr.json"
