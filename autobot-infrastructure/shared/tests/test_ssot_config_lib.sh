#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Self-contained bash test for autobot-infrastructure/shared/scripts/lib/ssot-config.sh
# (#14041). No pytest, no install -- run directly with bash:
#
#     bash autobot-infrastructure/shared/tests/test_ssot_config_lib.sh
#
# Covers the acceptance tests from the #14041 issue:
#   - the library sources cleanly under each source-line shape found in the
#     56-script enumeration (docs/audit/ssot_config_shell_library_14041.md)
#   - a literal that matches the SSOT keeps its value; a literal that diverges
#     (AUTOBOT_BROWSER_SERVICE_PORT: 3000 vs 9001) gets the SSOT value
#   - a missing/unreadable library still degrades via `|| true`

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LIB="${REPO_ROOT}/autobot-infrastructure/shared/scripts/lib/ssot-config.sh"

pass=0
fail=0

check() {
    local desc="$1" actual="$2" expected="$3"
    if [ "$actual" = "$expected" ]; then
        echo "PASS: $desc"
        pass=$((pass + 1))
    else
        echo "FAIL: $desc -- expected [$expected], got [$actual]"
        fail=$((fail + 1))
    fi
}

if [ ! -f "$LIB" ]; then
    echo "FATAL: $LIB does not exist" >&2
    exit 1
fi

# --- Shape A: direct source, defaults match the SSOT ------------------------
out=$(bash -c "source '$LIB'; echo \"\$AUTOBOT_BACKEND_PORT\"")
check "shape A: AUTOBOT_BACKEND_PORT default" "$out" "8001"

# --- literal matches SSOT: value unchanged ----------------------------------
out=$(bash -c "source '$LIB' 2>/dev/null || true; echo \"\${AUTOBOT_BACKEND_PORT:-8001}\"")
check "matching literal (AUTOBOT_BACKEND_PORT 8001)" "$out" "8001"

# --- literal diverges from SSOT: script now gets the SSOT value -------------
out=$(bash -c "source '$LIB' 2>/dev/null || true; echo \"\${AUTOBOT_BROWSER_SERVICE_PORT:-3000}\"")
check "diverging literal (AUTOBOT_BROWSER_SERVICE_PORT 3000 -> SSOT 9001)" "$out" "9001"

# --- missing library: || true degrades to the literal, unchanged -----------
out=$(bash -c "source /nonexistent/lib/ssot-config.sh 2>/dev/null || true; echo \"\${AUTOBOT_BROWSER_SERVICE_PORT:-3000}\"")
check "missing library degrades to literal" "$out" "3000"

# --- Shape B: two-path attempt (check_status.sh et al.), first path wins ----
out=$(bash -c "
SCRIPT_DIR='${REPO_ROOT}/autobot-infrastructure/shared/scripts'
source \"\$SCRIPT_DIR/lib/ssot-config.sh\" 2>/dev/null || source \"\$SCRIPT_DIR/../lib/ssot-config.sh\" 2>/dev/null || echo BOTH_FAILED
echo \"\$AUTOBOT_BACKEND_HOST\"
")
check "shape B: two-path attempt from scripts/ resolves" "$out" "127.0.0.1"

# --- Shape B: second path wins (distributed/check-health.sh depth) ---------
out=$(bash -c "
SCRIPT_DIR='${REPO_ROOT}/autobot-infrastructure/shared/scripts/distributed'
source \"\$SCRIPT_DIR/../lib/ssot-config.sh\" 2>/dev/null || source \"\$SCRIPT_DIR/lib/ssot-config.sh\" 2>/dev/null || echo BOTH_FAILED
echo \"\$AUTOBOT_OLLAMA_HOST\"
")
check "shape B: two-path attempt from distributed/ resolves" "$out" "127.0.0.1"

# --- ssh-hardening depth (../../lib) ----------------------------------------
out=$(bash -c "
SCRIPT_DIR='${REPO_ROOT}/autobot-infrastructure/shared/scripts/security/ssh-hardening'
source \"\${SCRIPT_DIR}/../../lib/ssot-config.sh\" 2>/dev/null || true
echo \"\$AUTOBOT_REDIS_HOST\"
")
check "ssh-hardening depth (../../lib) resolves" "$out" "127.0.0.1"

# --- Shape C: status-all-vms.sh -- unguarded source under set -e, VMS array -
out=$(bash -c "
set -e
SCRIPT_DIR='${REPO_ROOT}/autobot-infrastructure/shared/scripts/vm-management'
source \"\$SCRIPT_DIR/../lib/ssot-config.sh\"
echo \"ok:\${VMS[browser]}:\$AUTOBOT_BROWSER_SERVICE_PORT\"
")
check "shape C: status-all-vms.sh no longer crashes, VMS populated" "$out" "ok:127.0.0.1:9001"

# --- idempotent double-source is a no-op, does not clobber caller state ----
out=$(bash -c "
source '$LIB'
VMS[frontend]='custom-override'
source '$LIB'
echo \"\${VMS[frontend]}\"
")
check "double-source does not clobber caller-set VMS entry" "$out" "custom-override"

# --- .env overrides the default, unset vars still get the default ----------
tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT
echo "AUTOBOT_BACKEND_HOST=10.0.0.5" > "$tmp_root/.env"
out=$(bash -c "
export PROJECT_ROOT='$tmp_root'
source '$LIB'
echo \"\$AUTOBOT_BACKEND_HOST:\$AUTOBOT_REDIS_HOST\"
")
check ".env override wins; unset var keeps SSOT default" "$out" "10.0.0.5:127.0.0.1"

# --- :? guards must survive the library sourcing over them (#14041 review) -
# bootstrap-slm.sh:406 (# 2224) deliberately aborts if AUTOBOT_REDIS_HOST is
# unset, because it bakes the value into a REMOTE node's .env -- a loopback
# default there silently points a distributed Redis at the wrong host. The
# library now supplies that default at source time, so the guard must read
# from a value captured BEFORE the source, not the variable the library just
# populated. This reproduces bootstrap-slm.sh's own capture-then-guard idiom
# directly (see :17-29 and :415) rather than re-describing it, so a future
# edit that drops the capture trips this test.
# Reads the ACTUAL capture and guard lines out of bootstrap-slm.sh rather than
# reproducing the idiom by hand, so a future edit that drops the capture (or
# points the guard back at the raw, library-populated AUTOBOT_REDIS_HOST) trips
# this test instead of silently reintroducing #14041's regression.
BOOTSTRAP="${REPO_ROOT}/autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh"
capture_line=$(grep -m1 '^_OPERATOR_REDIS_HOST=' "$BOOTSTRAP")
guard_line=$(grep -m1 'REDIS_HOST=\${_OPERATOR_REDIS_HOST:?' "$BOOTSTRAP")
if [ -z "$capture_line" ] || [ -z "$guard_line" ]; then
    echo "FAIL: bootstrap-slm.sh no longer has the capture-before-source guard this test expects (capture=[$capture_line] guard=[$guard_line])"
    fail=$((fail + 1))
else
    out=$(bash -c "
unset AUTOBOT_REDIS_HOST
$capture_line
source '$LIB'
$guard_line
echo unreachable
" 2>/dev/null)
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$out" != "unreachable" ]; then
        echo "PASS: bootstrap-slm.sh's :? guard still fires when operator never set AUTOBOT_REDIS_HOST"
        pass=$((pass + 1))
    else
        echo "FAIL: bootstrap-slm.sh's :? guard did not fire -- expected non-zero exit and no output, got rc=$rc out=[$out]"
        fail=$((fail + 1))
    fi
fi

out=$(bash -c "
unset AUTOBOT_REDIS_HOST
source '$LIB'
REDIS_HOST=\${AUTOBOT_REDIS_HOST:?unset}
echo \"\$REDIS_HOST\"
" 2>/dev/null)
check "REGRESSION CHECK: guarding the RAW (post-source) var must NOT fire -- proves why capture-before-source is required" "$out" "127.0.0.1"

# --- library warns instead of killing a set -e caller on a broken .env -----
tmp_root2="$(mktemp -d)"
printf 'AUTOBOT_BACKEND_HOST=1.2.3.4\nBROKEN=$(exit 7)\n' > "$tmp_root2/.env"
stderr_file="$(mktemp)"
out=$(bash -c "
set -e
export PROJECT_ROOT='$tmp_root2'
source '$LIB'
echo \"survived:\$AUTOBOT_BACKEND_HOST:\$AUTOBOT_REDIS_HOST\"
" 2>"$stderr_file")
stderr_out=$(cat "$stderr_file" 2>/dev/null); rm -f "$stderr_file"
check "broken .env: set -e caller survives (does not die silently)" "$out" "survived:1.2.3.4:127.0.0.1"
case "$stderr_out" in
    *"WARNING"*) echo "PASS: broken .env produces a stderr warning"; pass=$((pass + 1)) ;;
    *) echo "FAIL: broken .env produced no stderr warning -- got: $stderr_out"; fail=$((fail + 1)) ;;
esac
rm -rf "$tmp_root2"

# --- Guard: no tracked file may regrow the non-`autobot-` path (#14041) ----
# 23 tracked shell scripts once sourced $_PROJECT_ROOT/infrastructure/... (a
# wrong directory segment -- this repo has no top-level infrastructure/, only
# autobot-infrastructure/). All 23 were fixed in the same PR that added this
# guard; this asserts the wrong form cannot regrow silently. Anchored on
# `git ls-files` so another session's worktree can never trip it -- ls-files
# only lists this checkout's tracked files, never another worktree's.
offenders=""
while IFS= read -r f; do
    hit=$(grep -n 'source.*infrastructure/shared/scripts/lib/ssot-config\.sh' "${REPO_ROOT}/${f}" 2>/dev/null \
        | grep -v 'autobot-infrastructure/shared/scripts/lib/ssot-config\.sh')
    if [ -n "$hit" ]; then
        offenders="${offenders}${f}: ${hit}
"
    fi
done < <(cd "$REPO_ROOT" && git ls-files -- '*.sh')

if [ -n "$offenders" ]; then
    echo "FAIL: tracked file(s) source the non-autobot- path:"
    echo "$offenders"
    fail=$((fail + 1))
else
    echo "PASS: no tracked *.sh file sources the non-autobot- infrastructure/ path"
    pass=$((pass + 1))
fi

# --- #14178: the two probes in a status script must not name different ports ---
# status-all-vms.sh checks a service two ways: an HTTP URL built from
# SERVICE_PORTS, and a `pgrep` on the port. Those were separate literals, and
# they disagreed the moment the SSOT library made the URL correct -- 3000 was
# Grafana's port, the browser service is 9001 (#4052). Either probe can be
# green while the other is red, and a process check that can never match
# reports a running service as down.
#
# Asserted as a shape, not as an instance: no process probe may carry a literal
# port at all. A specific 3000-vs-9001 assertion would pass the day someone
# introduced the same split on a different service.
_status_script="${REPO_ROOT}/autobot-infrastructure/shared/scripts/vm-management/status-all-vms.sh"
if [ -f "$_status_script" ]; then
    _literals="$(grep -cE "pgrep -f '[^']*[0-9]{4}|vite\.\*[0-9]{4}" "$_status_script" || true)"
    check "status-all-vms.sh process probes carry no literal port" "$_literals" "0"

    _derived="$(grep -c 'SERVICE_PORTS\[\$vm_name\]' "$_status_script" || true)"
    if [ "$_derived" -ge 4 ]; then
        echo "PASS: process probes derive their port from SERVICE_PORTS ($_derived sites)"
        pass=$((pass + 1))
    else
        echo "FAIL: expected >=4 SERVICE_PORTS-derived probes, found $_derived"
        fail=$((fail + 1))
    fi
else
    echo "FAIL: status-all-vms.sh not found -- refusing to report clean on a missing target"
    fail=$((fail + 1))
fi

echo
echo "=== $pass passed, $fail failed ==="
[ "$fail" -eq 0 ]
