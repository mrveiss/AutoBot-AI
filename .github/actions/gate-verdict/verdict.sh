#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Verdict of one required-context gate (#18208). Read from the environment so the
# composite action and the test drive the same code. The ORDER is the contract:
#
#   1. detection did not succeed        -> FAIL  (cannot tell whether the gate applies)
#   2. draft pull request               -> FAIL  "draft: mark ready for review" (D4)
#   3. the gate does not apply          -> PASS  "not affected"
#   4. the work finished and passed     -> PASS
#   5. anything else                    -> FAIL  (failed, cancelled, skipped, timed out)
#
# A cancelled upstream normally never reaches (5): each gate runs
# .github/actions/cancel-run-on-cancelled-upstream first, which ends the run
# `cancelled` (#17764). (5) still fails it, as the backstop if that step is skipped.
#
# A gate that applies but whose work is `skipped` fails (5): a skipped suite is no
# evidence a suite ran (#18106). Only (3) may pass without work, and it names the
# reason so a reader of the log can tell "nothing to verify" from "verified".
set -euo pipefail

: "${GATE_CONTEXT:?GATE_CONTEXT is required}"
: "${GATE_CHANGES_RESULT:?GATE_CHANGES_RESULT is required}"
: "${GATE_APPLIES:?GATE_APPLIES is required}"
: "${GATE_WORK_OK:?GATE_WORK_OK is required}"
: "${GATE_EVENT:?GATE_EVENT is required}"
GATE_DRAFT="${GATE_DRAFT:-false}"
GATE_DRAFT_GATED="${GATE_DRAFT_GATED:-true}"
GATE_WORK_DETAIL="${GATE_WORK_DETAIL:-}"

echo "context=${GATE_CONTEXT} changes=${GATE_CHANGES_RESULT} applies=${GATE_APPLIES} work_ok=${GATE_WORK_OK} event=${GATE_EVENT} draft=${GATE_DRAFT}"

if [ "${GATE_CHANGES_RESULT}" != "success" ]; then
  echo "::error title=${GATE_CONTEXT}::path detection ${GATE_CHANGES_RESULT} -- cannot tell whether this gate applies, so it cannot pass"
  exit 1
fi

if [ "${GATE_DRAFT_GATED}" = "true" ] && [ "${GATE_EVENT}" = "pull_request" ] && [ "${GATE_DRAFT}" = "true" ]; then
  echo "::error title=${GATE_CONTEXT}::draft: mark ready for review"
  echo "This pull request is a draft, so the work behind '${GATE_CONTEXT}' was not run."
  echo "Marking it ready for review starts a new run. Re-running THIS run replays the draft"
  echo "payload and fails here again (#18106): start the run for the current state instead."
  exit 1
fi

if [ "${GATE_APPLIES}" != "true" ]; then
  echo "not affected: no path behind '${GATE_CONTEXT}' changed, so there is nothing to verify"
  exit 0
fi

if [ "${GATE_WORK_OK}" = "true" ]; then
  echo "'${GATE_CONTEXT}' verified: ${GATE_WORK_DETAIL:-work passed}"
  exit 0
fi

echo "::error title=${GATE_CONTEXT}::the work behind this context did not pass (${GATE_WORK_DETAIL:-no result recorded})"
exit 1
