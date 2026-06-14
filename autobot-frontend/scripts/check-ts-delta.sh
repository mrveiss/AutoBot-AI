#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# check-ts-delta.sh — Fail if TypeScript errors exceed the baseline.
#
# Usage: bash autobot-frontend/scripts/check-ts-delta.sh
#
# Reads baseline from docs/developer/audits/typescript-baseline.md (Total: N line).
# Exits 1 if current error count exceeds baseline; exits 0 otherwise.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FRONTEND_DIR="${REPO_ROOT}/autobot-frontend"
BASELINE_FILE="${REPO_ROOT}/docs/developer/audits/typescript-baseline.md"

# --- Resolve baseline ---
if [[ ! -f "${BASELINE_FILE}" ]]; then
  echo "ERROR: Baseline file not found: ${BASELINE_FILE}" >&2
  exit 1
fi

BASELINE=$(grep -m1 "^\*\*Total:" "${BASELINE_FILE}" | grep -o '[0-9]*')
if [[ -z "${BASELINE}" ]]; then
  echo "ERROR: Could not parse 'Total:' from ${BASELINE_FILE}" >&2
  exit 1
fi

# --- Run TypeScript check ---
echo "Running vue-tsc (baseline: ${BASELINE} errors)..."
CURRENT=$(
  cd "${FRONTEND_DIR}"
  npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS" || true
)

echo "Current TS errors : ${CURRENT}"
echo "Baseline TS errors: ${BASELINE}"

# --- Compare ---
if (( CURRENT > BASELINE )); then
  DELTA=$(( CURRENT - BASELINE ))
  echo ""
  echo "FAIL: ${DELTA} new TypeScript error(s) introduced (${CURRENT} > ${BASELINE})."
  echo "Fix the new errors or, if intentional, update the baseline:"
  echo "  docs/developer/audits/typescript-baseline.md"
  exit 1
else
  DELTA=$(( BASELINE - CURRENT ))
  if (( DELTA > 0 )); then
    echo "PASS: ${CURRENT} errors (${DELTA} below baseline — consider updating the baseline)."
  else
    echo "PASS: ${CURRENT} errors (matches baseline exactly)."
  fi
  exit 0
fi
