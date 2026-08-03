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
# The compiler this script measures with. Resolved as a path rather than through
# `npx` — see "Why not npx" below.
TSC_BIN="${FRONTEND_DIR}/node_modules/.bin/vue-tsc"

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
#
# Why not npx (#13341). This step ran unbounded for over three hours on the
# singleton self-hosted runner while its sibling `type-check` step — the SAME
# vue-tsc invocation, reached through `npm run` — finished in about a minute in
# the same job. The difference was `npx`, and every one of its extra behaviours
# is an unbounded wait:
#
#   * it resolves the package before running it, which can reach the registry;
#   * when resolution misses it PROMPTS ("Ok to proceed?") and blocks on stdin,
#     which in a CI step is a pipe that never delivers a line and never closes;
#   * it takes locks under the shared npm cache, and on the self-hosted runner
#     $HOME is shared with every concurrently executing job rather than being a
#     fresh VM per job, so a stale lock blocks instead of being absent.
#
# `vue-tsc` is a devDependency, so it is already on disk after `npm ci`; there
# is nothing for a resolver to do. Calling the installed binary directly removes
# the network path, the prompt and the cache lock in one move. `</dev/null`
# guarantees that nothing downstream of this line can ever block on stdin.
if [[ ! -x "${TSC_BIN}" ]]; then
  echo "ERROR: vue-tsc not found at ${TSC_BIN}" >&2
  echo "Run 'npm ci' in ${FRONTEND_DIR} first." >&2
  exit 1
fi

echo "Running vue-tsc (baseline: ${BASELINE} errors)..."
TSC_OUTPUT="$(mktemp)"
trap 'rm -f "${TSC_OUTPUT}"' EXIT

TSC_STATUS=0
(
  cd "${FRONTEND_DIR}"
  "${TSC_BIN}" --noEmit -p tsconfig.app.json
) >"${TSC_OUTPUT}" 2>&1 </dev/null || TSC_STATUS=$?

CURRENT=$(grep -c "error TS" "${TSC_OUTPUT}" || true)

# A count is only a measurement if the compiler actually checked the sources.
# The old code funnelled every failure into `|| true` and counted matches, so a
# compiler that never ran reported "0 errors" and PASSED. Counting alone is not
# enough to repair that, because the count is non-zero in two failure modes too:
# a missing tsconfig emits ONE diagnostic (TS5058) having checked NOTHING, and a
# crash part-way through emits however many diagnostics it reached before dying.
# Both then read as a comfortable pass. The exit status is the discriminator.
#
# vue-tsc returns TypeScript's ExitStatus: 0 clean, 1 a configuration/command
# diagnostic, 2 the normal "type errors were found", 3 and 4 invalid project.
# So anything above 2 never completed a check, and a non-zero status with no
# diagnostics at all is the crash case.
if (( TSC_STATUS > 2 )) || { (( TSC_STATUS != 0 )) && (( CURRENT == 0 )); }; then
  echo "ERROR: vue-tsc exited ${TSC_STATUS} without completing a check." >&2
  echo "The error delta is unknown, so this is a failure, not a pass. Output:" >&2
  cat "${TSC_OUTPUT}" >&2
  exit 1
fi

# TS5xxx/TS6xxx are configuration and command-line diagnostics — a missing or
# unreadable tsconfig, an unknown option. They are reported INSTEAD of checking
# the sources, so the count above measures nothing. Type errors occupy the other
# code ranges, so this cannot swallow a genuine regression.
if grep -qE "error TS[56][0-9]{3}" "${TSC_OUTPUT}"; then
  echo "ERROR: vue-tsc reported a configuration error; nothing was type-checked." >&2
  cat "${TSC_OUTPUT}" >&2
  exit 1
fi

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
