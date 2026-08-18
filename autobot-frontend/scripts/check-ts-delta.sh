#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# check-ts-delta.sh — Fail if TypeScript errors exceed the baseline.
#
# Usage: bash autobot-frontend/scripts/check-ts-delta.sh
#
# Reads baseline from docs/developer/audits/typescript-baseline.md (Total: N line).
# Exits 1 if current error count exceeds baseline; exits 0 otherwise.
#
# #14481: a caller that already compiled this exact project (same command,
# same tsconfig) can hand this script that output instead of paying for a
# second compile. Set BOTH TSC_OUTPUT_FILE (raw vue-tsc stdout+stderr) and
# TSC_STATUS_FILE (its exit code, one line) and this script reads them
# instead of invoking the compiler again. Either unset, or either file
# missing, and this script compiles fresh exactly as it always has — so
# `bash scripts/check-ts-delta.sh` with no environment still works standalone
# for local development.

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

# --- Run TypeScript check, or reuse a caller's prior run (#14481) ---
if [[ -n "${TSC_OUTPUT_FILE:-}" && -n "${TSC_STATUS_FILE:-}" \
      && -f "${TSC_OUTPUT_FILE}" && -f "${TSC_STATUS_FILE}" ]]; then
  echo "Reusing vue-tsc output captured by the type-check step (baseline: ${BASELINE} errors)..."
  TSC_OUTPUT="${TSC_OUTPUT_FILE}"
  TSC_STATUS="$(<"${TSC_STATUS_FILE}")"

  # A status file is only a valid handoff if it holds exactly what the type-check
  # step wrote: a single small non-negative integer (0-255, the POSIX exit status
  # range). Anything else — empty (the file exists but the write raced or failed),
  # whitespace, multiple lines, or non-numeric content — is a discriminator failure
  # in its own right, not a status of 0. Trusting it as 0 is exactly the bug this
  # block exists to prevent: a compiler that never produced a real status would
  # silently read as a clean exit. Route this through the script's own error
  # handling rather than letting `set -u`/arithmetic surface bash's raw message.
  if [[ ! "${TSC_STATUS}" =~ ^[0-9]+$ ]] || (( TSC_STATUS > 255 )); then
    echo "ERROR: ${TSC_STATUS_FILE} does not hold a valid exit status." >&2
    echo "Expected a single integer 0-255; got: '${TSC_STATUS}'" >&2
    echo "Refusing to treat this as a clean compile — the compiler's actual exit status is unknown." >&2
    exit 1
  fi
else
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
fi

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
# diagnostics at all is the crash case. This holds whether TSC_STATUS came from
# a compile just above or from a reused TSC_STATUS_FILE — a caller that reused
# a crash gets caught here exactly like a caller that hit one directly.
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
