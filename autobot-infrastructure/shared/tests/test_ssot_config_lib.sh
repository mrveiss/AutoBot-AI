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

    # The four probes read one resolved local, `$svc_port`, rather than the array
    # directly -- the review found that an unset key expands to EMPTY under this
    # script's `set -e` (no `set -u`), which would make `pgrep -f 'python.*'`
    # match every python process and report the service UP. So the guard checks
    # both that the probes are derived AND that the empty-key path is defended.
    _derived="$(grep -cE "pgrep -f '[^']*\\\$\\{svc_port\\}" "$_status_script" || true)"
    if [ "$_derived" -ge 4 ]; then
        echo "PASS: process probes derive their port from the resolved svc_port ($_derived sites)"
        pass=$((pass + 1))
    else
        echo "FAIL: expected >=4 svc_port-derived probes, found $_derived"
        fail=$((fail + 1))
    fi

    # BEHAVIOURAL, not a grep. The review defeated the previous text-presence
    # version with `if false && [ -z "$svc_port" ]` -- dead code that keeps both
    # substrings, so the guard passed while the wildcard vulnerability was live.
    # A guard for a fail-closed path has to actually run the path.
    #
    # The function is extracted and executed with `ssh` stubbed to echo its
    # command, so nothing reaches a network. An unknown service must produce
    # exactly "0" and must NOT produce a pgrep pattern at all.
    _probe_out="$(
        {
            sed -n '/^get_service_processes() {/,/^}/p' "$_status_script"
            cat <<'STUB'
# NOTE: "browser" is deliberately ABSENT while the probe is called WITH it.
# A name that matches no `case` branch would return "0" via fall-through, so a
# dead guard would look identical to a live one -- the review defeated the
# previous version exactly that way.
declare -A SERVICE_PORTS=( ["frontend"]="5173" )
SSH_KEY="$(mktemp)"; SSH_USER=nobody
ssh() { echo "SSH_WOULD_RUN: $*"; }
timeout() { shift; "$@"; }
get_service_processes 192.0.2.1 browser
STUB
        } | bash 2>/dev/null
    )"
    check "a case-matched service with no port entry reports exactly 0" "$_probe_out" "0"

    _wildcard_out="$(
        {
            sed -n '/^get_service_processes() {/,/^}/p' "$_status_script"
            cat <<'STUB'
# NOTE: "browser" is deliberately ABSENT while the probe is called WITH it.
# A name that matches no `case` branch would return "0" via fall-through, so a
# dead guard would look identical to a live one -- the review defeated the
# previous version exactly that way.
declare -A SERVICE_PORTS=( ["frontend"]="5173" )
SSH_KEY="$(mktemp)"; SSH_USER=nobody
ssh() { echo "SSH_WOULD_RUN: $*"; }
timeout() { shift; "$@"; }
get_service_processes 192.0.2.1 browser
STUB
        } | bash 2>&1 | grep -c "pgrep -f 'python\.\*'" || true
    )"
    check "a missing port never builds a bare 'python.*' pattern" "$_wildcard_out" "0"

    # Quote-agnostic literal check: the earlier single-quote-only regex was
    # defeated by writing the same literal in double quotes.
    _dq_literals="$(grep -cE "pgrep -f \"[^\"]*[0-9]{4}" "$_status_script" || true)"
    check "no double-quoted literal port in a process probe" "$_dq_literals" "0"

else
    echo "FAIL: status-all-vms.sh not found -- refusing to report clean on a missing target"
    fail=$((fail + 1))
fi

# --- #14173: the four var families #14041 deliberately left unexported now
#     have real SSOT fields (autobot_shared/ssot_config.py) and the library
#     exports them. ------------------------------------------------------

out=$(bash -c "
export HOME='/nonexistent-home-for-ssot-test'
unset AUTOBOT_SSH_KEY AUTOBOT_SSH_USER AUTOBOT_SLM_NODE_ID AUTOBOT_VNC_WEB_PORT AUTOBOT_VNC_SERVER_PORT
source '$LIB'
echo \"\$AUTOBOT_SSH_KEY|\$AUTOBOT_SSH_USER|\$AUTOBOT_SLM_NODE_ID|\$AUTOBOT_VNC_WEB_PORT|\$AUTOBOT_VNC_SERVER_PORT\"
")
check "14173: SSH/SLM/VNC families get SSOT defaults" "$out" \
    "/nonexistent-home-for-ssot-test/.ssh/autobot_key|autobot|00-SLM-Manager|6080|5901"

# --- VNC WEB/SERVER host derive from AUTOBOT_BACKEND_HOST, not a separate
#     hardcoded literal -- proves the four-name fork actually consolidated
#     onto an existing canonical field instead of gaining its own literal. --
out=$(bash -c "
export AUTOBOT_BACKEND_HOST='10.9.8.7'
unset AUTOBOT_VNC_WEB_HOST AUTOBOT_VNC_SERVER_HOST
source '$LIB'
echo \"\$AUTOBOT_VNC_WEB_HOST|\$AUTOBOT_VNC_SERVER_HOST\"
")
check "14173: VNC_WEB_HOST/VNC_SERVER_HOST derive from AUTOBOT_BACKEND_HOST" "$out" "10.9.8.7|10.9.8.7"

# --- .env override still wins for the four new families too ---------------
tmp_root3="$(mktemp -d)"
cat > "$tmp_root3/.env" <<'ENVEOF'
AUTOBOT_SSH_USER=custom-user
AUTOBOT_SLM_NODE_ID=99-Custom-Manager
ENVEOF
out=$(bash -c "
export PROJECT_ROOT='$tmp_root3'
unset AUTOBOT_SSH_USER AUTOBOT_SLM_NODE_ID
source '$LIB'
echo \"\$AUTOBOT_SSH_USER:\$AUTOBOT_SLM_NODE_ID\"
")
rm -rf "$tmp_root3"
check "14173: .env override wins for AUTOBOT_SSH_USER/AUTOBOT_SLM_NODE_ID" "$out" "custom-user:99-Custom-Manager"

# --- DENIAL / reproduction: status-all-vms.sh's own "SSH key not found"
#     guard used to fire even when a real key existed at the conventional
#     $HOME/.ssh/autobot_key path, because the library never set
#     AUTOBOT_SSH_KEY (#14173) -- SSH_KEY="$AUTOBOT_SSH_KEY"
#     (vm-management/status-all-vms.sh, NO `:-` fallback at all) always
#     resolved to the empty string. Reproduces the exact guard line read out
#     of the live script rather than re-describing it by hand, so a future
#     edit that changes the guard shape trips this test instead of silently
#     drifting from what actually ships (same idiom as the bootstrap-slm.sh
#     capture-before-source guard test above).
_status_script="${REPO_ROOT}/autobot-infrastructure/shared/scripts/vm-management/status-all-vms.sh"
_key_line=$(grep -m1 '^SSH_KEY=' "$_status_script")
if [ -z "$_key_line" ]; then
    echo "FAIL: status-all-vms.sh no longer has the SSH_KEY=\$AUTOBOT_SSH_KEY line this test expects"
    fail=$((fail + 1))
else
    tmp_home="$(mktemp -d)"
    mkdir -p "$tmp_home/.ssh"
    printf 'not a real key, just needs to exist\n' > "$tmp_home/.ssh/autobot_key"

    # BEFORE (reproduction of the pre-#14173 bug): the library never exported
    # AUTOBOT_SSH_KEY, so the guard fires even though a real key file exists
    # at the conventional path -- a silent lie, not a loud failure.
    before_out=$(bash -c "
        export HOME='$tmp_home'
        unset AUTOBOT_SSH_KEY
        $_key_line
        if [ ! -f \"\$SSH_KEY\" ]; then echo NO_KEY_FOUND; else echo KEY_FOUND; fi
    ")
    check "DENIAL repro: pre-#14173 state reports NO_KEY_FOUND despite a real key on disk" "$before_out" "NO_KEY_FOUND"

    # AFTER (fixed): sourcing the library resolves AUTOBOT_SSH_KEY to the same
    # conventional path, so the guard now finds the real key instead of lying.
    after_out=$(bash -c "
        export HOME='$tmp_home'
        unset AUTOBOT_SSH_KEY
        source '$LIB'
        $_key_line
        if [ ! -f \"\$SSH_KEY\" ]; then echo NO_KEY_FOUND; else echo KEY_FOUND; fi
    ")
    check "14173 fix: library-resolved AUTOBOT_SSH_KEY finds the real key" "$after_out" "KEY_FOUND"

    rm -rf "$tmp_home"
fi

# --- Reach self-check: must NOT share the "autobot-infrastructure/ only"
#     blind spot that undercounted shape-D above (Step 3 note) -- scoped on
#     `git ls-files -- '*.sh'` (full tracked tree, same anchor as the
#     offenders guard above), never a subdirectory grep. Two independent
#     assertions: the file-count floor catches a probe that silently stops
#     matching anything (an empty/near-empty result reads as "clean" unless
#     presence is checked, not absence of failure); the var-count floor
#     catches a regex that stops matching a variable shape. -----------------
_all_sh_files="$(cd "$REPO_ROOT" && git ls-files -- '*.sh')"
_sh_count=$(echo "$_all_sh_files" | grep -c . || true)
if [ "$_sh_count" -lt 100 ]; then
    echo "FAIL: reach self-check scanned too few shell scripts ($_sh_count) -- probe is too narrow"
    fail=$((fail + 1))
else
    echo "PASS: reach self-check scanned $_sh_count tracked shell scripts"
    pass=$((pass + 1))
fi

_distinct_vars=$(cd "$REPO_ROOT" && git ls-files -- '*.sh' | xargs grep -ohE '\$\{?AUTOBOT_[A-Z0-9_]+' 2>/dev/null | sed -E 's/^\$\{?//' | sort -u)
_distinct_count=$(echo "$_distinct_vars" | grep -c . || true)
if [ "$_distinct_count" -lt 61 ]; then
    echo "FAIL: reach self-check found only $_distinct_count distinct AUTOBOT_ names -- expected >= 61 (#14173 baseline)"
    fail=$((fail + 1))
else
    echo "PASS: reach self-check found $_distinct_count distinct AUTOBOT_ names (>= 61 baseline)"
    pass=$((pass + 1))
fi

# The counter's own scan must independently rediscover the four #14173
# families -- not just confirm a hardcoded list matches itself.
for _fam_var in AUTOBOT_SSH_KEY AUTOBOT_SSH_USER AUTOBOT_SLM_NODE_ID \
    AUTOBOT_VNC_WEB_HOST AUTOBOT_VNC_WEB_PORT AUTOBOT_VNC_SERVER_HOST AUTOBOT_VNC_SERVER_PORT; do
    if echo "$_distinct_vars" | grep -qx "$_fam_var"; then
        echo "PASS: reach self-check's scan independently found $_fam_var"
        pass=$((pass + 1))
    else
        echo "FAIL: reach self-check's scan did not find $_fam_var -- matcher regressed"
        fail=$((fail + 1))
    fi
done

echo
echo "=== $pass passed, $fail failed ==="
[ "$fail" -eq 0 ]
