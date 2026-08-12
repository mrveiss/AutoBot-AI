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

echo
echo "=== $pass passed, $fail failed ==="
[ "$fail" -eq 0 ]
