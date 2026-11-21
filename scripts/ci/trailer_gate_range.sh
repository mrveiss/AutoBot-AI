#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# The commit range the no-commit-trailers gate scans (#22001). Tested by
# repo_tests/trailer_gate_range_22001_test.py against temp repos.
#
# Inputs (env): HEAD_SHA, BASE_SHA (the event's base), EXPECTED_COMMITS (GitHub's `commits`,
# empty for merge_group), BASE_REF (pull_request only: the base branch to take the CURRENT tip
# of), RELEASE_BASE_SHA / RELEASE_NEW_COMMITS (#19466 promotion override), GITHUB_OUTPUT,
# TRAILER_GATE_DEEPEN_START (first depth of the over-count retry, default 400).
# Output: `base-sha=` -- scan `base-sha..HEAD_SHA`.
#
# Why the range is not simply BASE_SHA..HEAD_SHA in a depth-100 clone: a head that merged
# main earlier reaches OLD main commits through its own history, while the clone is cut
# 100 commits below the base tip, so those old commits are not reachable from the base and
# count as the PR's own (#22001: 11 scanned, GitHub 7). Too FEW commits is a truncated
# scan and fails (#16207); too MANY is deepened until the base side is complete.
#
# The equality check in _check_count (scanned == GitHub's count), not the deepening, is the
# truncation guard: deepening only ever adds history, and whatever it leaves is judged by
# that check, which fails a short scan as "too shallow" and a long one as "base mismatch".
set -euo pipefail

_fail_endpoint() {
  echo "::error::$1 is not present in the checkout -- this PR is"
  echo "::error::deeper than the checkout. Raise fetch-depth in this workflow;"
  echo "::error::do NOT widen it back to 0 without re-measuring (#16207)."
  exit 1
}

_count() { git rev-list --count "${BASE_SHA}..${HEAD_SHA}"; }

# Deepen both endpoints until the count stops exceeding GitHub's, or history is complete.
_deepen_while_over() {
  local depth="${TRAILER_GATE_DEEPEN_START:-400}"
  while [ "$(_count)" -gt "${EXPECTED_COMMITS}" ] \
    && [ "$(git rev-parse --is-shallow-repository)" = "true" ]; do
    if [ "${depth}" -lt 100000 ]; then
      git fetch --no-tags --depth="${depth}" origin "${HEAD_SHA}" "${BASE_SHA}"
      depth=$((depth * 2))
    else
      git fetch --no-tags --unshallow origin
    fi
  done
}

_check_count() {
  [ -n "${EXPECTED_COMMITS}" ] || return 0
  local scanned
  scanned="$(_count)"
  if [ "${scanned}" -gt "${EXPECTED_COMMITS}" ]; then
    _deepen_while_over
    scanned="$(_count)"
  fi
  if [ "${scanned}" -lt "${EXPECTED_COMMITS}" ]; then
    echo "::error::scanned ${scanned} commits but GitHub reports ${EXPECTED_COMMITS}:"
    echo "::error::the checkout is too shallow and the oldest commits would go"
    echo "::error::unexamined. Raise fetch-depth (#16207)."
    exit 1
  elif [ "${scanned}" -gt "${EXPECTED_COMMITS}" ]; then
    echo "::error::scanned ${scanned} commits but GitHub reports ${EXPECTED_COMMITS}:"
    echo "::error::the range ${BASE_SHA}..${HEAD_SHA} holds commits that are not the"
    echo "::error::PR's own even with full history -- a base mismatch, not fetch depth (#22001)."
    exit 1
  fi
}

_choose_base() {
  if [ -n "${RELEASE_BASE_SHA:-}" ]; then
    BASE_SHA="${RELEASE_BASE_SHA}"
    EXPECTED_COMMITS="${RELEASE_NEW_COMMITS}"
    if [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
      git fetch --no-tags --depth="$((RELEASE_NEW_COMMITS + 1))" origin "${HEAD_SHA}"
    fi
  elif [ -n "${BASE_REF:-}" ]; then
    # GitHub counts the PR's commits against the CURRENT base tip, not the event's.
    # Only a shallow clone is fetched shallowly: --depth on a complete clone would cut it.
    local depth_arg=()
    if [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
      depth_arg=(--depth=1)
    fi
    git fetch --no-tags "${depth_arg[@]}" origin "refs/heads/${BASE_REF}"
    BASE_SHA="$(git rev-parse FETCH_HEAD)"
  fi
}

main() {
  _choose_base
  echo "Scanning commits ${BASE_SHA}..${HEAD_SHA}"
  local endpoint
  for endpoint in "${BASE_SHA}" "${HEAD_SHA}"; do
    git cat-file -e "${endpoint}^{commit}" 2>/dev/null || _fail_endpoint "${endpoint}"
  done
  _check_count
  echo "base-sha=${BASE_SHA}" >> "${GITHUB_OUTPUT}"
}

main
