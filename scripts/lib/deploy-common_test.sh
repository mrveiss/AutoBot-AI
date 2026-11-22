#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/deploy-common.sh (#18557). Run: bash scripts/lib/deploy-common_test.sh
# Hermetic: stubs ansible / ansible-playbook on a throwaway PATH under mktemp.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
LOG_FILE="$D/log"; RED='<R>'; GREEN='<G>'; YELLOW='<Y>'; BLUE='<B>'; NC='<N>'
INVENTORY_FILE="$D/inv"; PLAYBOOK_FILE="$D/pb"
# shellcheck source=scripts/lib/deploy-common.sh
source "${HERE}/deploy-common.sh"
mkdir "$D/bin"
printf '#!/bin/sh\nexit 0\n' > "$D/bin/ansible-playbook"
printf '#!/bin/sh\nexit ${ANS_RC:-0}\n' > "$D/bin/ansible"
chmod +x "$D/bin/ansible" "$D/bin/ansible-playbook"

pass=0
fail=0
check() {
    if [ "$2" = "$3" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "  FAIL: $1 -- expected [$2], got [$3]"; fi
}

check "log INFO" "<B>ℹ️ hi<N>" "$(log INFO hi)"
check "log WARN" "<Y>⚠️ hi<N>" "$(log WARN hi)"
check "log ERROR" "<R>❌ hi<N>" "$(log ERROR hi)"
check "log SUCCESS" "<G>✅ hi<N>" "$(log SUCCESS hi)"
check "log DEBUG is file-only" "" "$(log DEBUG quiet)"
check "log DEBUG written" "1" "$(grep -c '\[DEBUG\] quiet' "$LOG_FILE")"
check "success is log SUCCESS" "<G>✅ ok<N>" "$(success ok)"
(error_exit boom) > /dev/null; check "error_exit exits 1" "1" "$?"
(PATH="$D/bin:$PATH"; check_prerequisites) > /dev/null; check "missing inventory fails" "1" "$?"
touch "$INVENTORY_FILE"
(PATH="$D/bin:$PATH"; check_prerequisites) > /dev/null; check "missing playbook fails" "1" "$?"
touch "$PLAYBOOK_FILE"
(PATH="$D/bin:$PATH"; check_prerequisites) > /dev/null; check "all present passes" "0" "$?"
(PATH="$D/bin:$PATH"; test_connectivity) > /dev/null; check "ping ok passes" "0" "$?"
(PATH="$D/bin:$PATH"; ANS_RC=1 test_connectivity) > /dev/null; check "ping failure exits 1" "1" "$?"

echo "deploy-common: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
