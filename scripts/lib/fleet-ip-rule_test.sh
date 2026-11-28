#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Tests for scripts/lib/fleet-ip-rule.sh (#19233). The range is built at runtime from parts,
# never written as one literal, for the same reason the rule exists.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/fleet-ip-rule.sh
source "${HERE}/fleet-ip-rule.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
check() { if [ "$2" = "$3" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "  FAIL: $1 -- expected [$3], got [$2]"; fi; }

a=10; b=77; c=4
printf 'FLEET = re.compile(r"^%s\\.%s\\.%s\\.")\n' "$a" "$b" "$c" > "$TMP/rule.py"
re=$(fleet_ip_regex "$TMP/rule.py"); check "derives the range" "$?" "0"
printf 'host %s.%s.%s.9\n' "$a" "$b" "$c" | grep -qE "$re"; check "matches a fleet address" "$?" "0"
printf 'host %s.%s.%s.9\n' "$a" "$b" "$((c + 1))" | grep -qE "$re"; check "does not match a neighbour" "$?" "1"

fleet_ip_regex "$TMP/missing.py" >/dev/null 2>"$TMP/err"; check "unreadable rule returns 2" "$?" "2"
grep -q "unreadable" "$TMP/err"; check "and says why" "$?" "0"
printf 'nothing here\n' > "$TMP/empty.py"
out=$(fleet_ip_regex "$TMP/empty.py" 2>/dev/null); check "a rule with no range returns 2" "$?" "2"
check "and prints no pattern" "$out" ""

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
