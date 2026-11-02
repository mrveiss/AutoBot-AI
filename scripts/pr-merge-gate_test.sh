#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Unit tests for scripts/pr-merge-gate.sh — the caller that #15995's gate did
# not have. Run: bash scripts/pr-merge-gate_test.sh
#
# The gate itself is tested in scripts/pr_required_gate_test.py. What is tested
# HERE is the wiring, because "the caller runs it" and "the caller OBEYS it"
# are different claims and only the second is a gate: a script that invokes the
# gate and discards its exit status is the "produced and consumed by nothing"
# shape (#15953) and looks identical in the output.
#
# No case makes a network call. `gh` and the gate are both stubbed — a unit
# suite that needs a live PR is a suite people switch off, which is the state
# the gate was already in.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${HERE}/pr-merge-gate.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pass=0
fail=0

STUB_BIN="${TMP}/bin"
mkdir -p "${STUB_BIN}"

GATE_STUB="${TMP}/gate_stub.py"

# PYTHON, not sh: the script runs the gate as `"$PY" "$GATE_SCRIPT"`, so a
# shell stub would be handed to the interpreter and die on a SyntaxError —
# which looks exactly like the gate blocking.
write_gate_stub() {
    printf 'import sys\nprint(f"#{sys.argv[1]} %s")\nsys.exit(%s)\n' "$1" "$2" > "${GATE_STUB}"
}

run_gate() {
    PATH="${STUB_BIN}:${PATH}" PR_MERGE_GATE_SCRIPT="${GATE_STUB}" \
        bash "${SCRIPT}" "$@" 2>&1
}

expect() {
    local name="$1" want_rc="$2" pattern="$3"; shift 3
    local out rc
    out=$("$@" 2>&1); rc=$?
    if [ "$rc" != "$want_rc" ]; then
        fail=$((fail + 1))
        echo "  FAIL: ${name} -- expected exit ${want_rc}, got ${rc}"
        printf '%s\n' "$out" | sed 's/^/         /'
    elif printf '%s' "$out" | grep -q "$pattern"; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "  FAIL: ${name} -- expected output matching [${pattern}]"
        printf '%s\n' "$out" | sed 's/^/         /'
    fi
}

echo "== the gate's verdict is obeyed =="

write_gate_stub "CONTEXTS-GREEN" 0
expect "a green gate exits 0 and names the PR" 0 "PR #777 — every required context" \
    run_gate --pr 777
expect "the PR number reaches the gate" 0 "#777 CONTEXTS-GREEN" \
    run_gate --pr 777

write_gate_stub "BLOCKED" 1
expect "a blocked gate exits 1" 1 "PR #777 is NOT clear to merge" \
    run_gate --pr 777
# PENDING is a non-zero the gate issues for "not knowable yet". It must not be
# read as "go": the whole point of the distinction is that waiting and acting
# are different, and both are non-green.
write_gate_stub "PENDING" 1
expect "a pending gate is not a pass" 1 "NOT clear to merge" \
    run_gate --pr 777

echo "== branch resolution keeps its two failures apart =="

write_gate_stub "CONTEXTS-GREEN" 0

printf '#!/bin/sh\nexit 0\n' > "${STUB_BIN}/gh"
chmod +x "${STUB_BIN}/gh"
expect "no open PR is reported as nothing to judge" 2 "no OPEN pull request" \
    run_gate --branch some-branch

printf '#!/bin/sh\nexit 7\n' > "${STUB_BIN}/gh"
chmod +x "${STUB_BIN}/gh"
expect "a gh failure is UNKNOWN, never green" 2 "gh could not be queried" \
    run_gate --branch some-branch

printf '#!/bin/sh\necho 4242\n' > "${STUB_BIN}/gh"
chmod +x "${STUB_BIN}/gh"
expect "a resolved branch judges that PR" 0 "#4242 CONTEXTS-GREEN" \
    run_gate --branch some-branch

rm -f "${STUB_BIN}/gh"

echo "== a missing gate is fatal, not a pass =="
expect "an absent gate script refuses to report" 2 "required-contexts gate not found" \
    env PR_MERGE_GATE_SCRIPT="${TMP}/no-such-gate.py" bash "${SCRIPT}" --pr 777

echo ""
echo "passed: ${pass}  failed: ${fail}"
[ "${fail}" -eq 0 ] || exit 1
