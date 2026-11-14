#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# The base a pull request into the release branch is judged from (#19466). Contract and the
# reason for it live in action.yml next to this file; repo_tests/release_promotion_base_19466_test.py
# runs this script against a fake `gh`.
#
# Inputs (env): EVENT_NAME, BASE_REF, HEAD_SHA, REPO, RELEASE_BRANCH, INTEGRATION_BRANCH,
# FETCH ("true" fetches the merge base when the clone lacks it), GITHUB_OUTPUT.
set -euo pipefail

if [ "${EVENT_NAME}" != "pull_request" ] || [ "${BASE_REF}" != "${RELEASE_BRANCH}" ]; then
  echo "not a pull request into ${RELEASE_BRANCH}: the gates judge the PR's own range as before"
  {
    echo "base-sha="
    echo "new-commits="
  } >> "${GITHUB_OUTPUT}"
  exit 0
fi

# Fail closed: a compare that cannot be read must never become "nothing new to judge".
if ! compared="$(gh api "repos/${REPO}/compare/${INTEGRATION_BRANCH}...${HEAD_SHA}" \
  --jq '[.merge_base_commit.sha, .ahead_by] | map(tostring) | join(" ")')"; then
  echo "::error::could not compare ${INTEGRATION_BRANCH}...${HEAD_SHA}; refusing to judge this release PR without its base (#19466)"
  exit 1
fi
read -r base_sha new_commits _ <<< "${compared}"
if ! [[ "${base_sha:-}" =~ ^[0-9a-f]{40}$ ]] || ! [[ "${new_commits:-}" =~ ^[0-9]+$ ]]; then
  echo "::error::the compare of ${INTEGRATION_BRANCH}...${HEAD_SHA} returned '${compared}', not a merge base and a count; refusing (#19466)"
  exit 1
fi

echo "${new_commits} commit(s) not already on ${INTEGRATION_BRANCH}; judging from their merge base ${base_sha}"
if [ "${FETCH}" = "true" ] && ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
  git fetch --no-tags --depth=1 origin "${base_sha}"
fi
{
  echo "base-sha=${base_sha}"
  echo "new-commits=${new_commits}"
} >> "${GITHUB_OUTPUT}"
