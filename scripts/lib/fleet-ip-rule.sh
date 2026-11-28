#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# The fleet IP range as an ERE, derived from the lint rule that defines it (#19233).
#
# The range is deliberately NOT written here -- putting it in a script is the very thing the
# rule checks for. tools/lint/check_no_hardcoded_ip_fallbacks.py is the single source of
# what "fleet IP" means; this reads its `^a\.b\.c\.` prefix and widens it to a full address.
#
# fleet_ip_regex RULE_FILE  -> prints the ERE; returns 2, with the reason on stderr, when the
# file is unreadable or yields no range. It never prints a match-nothing pattern: a caller
# checking text against an empty rule reports "no fleet IP" about everything, which is the
# silent wrong verdict #19233 traced the "got [no]" flake to.

fleet_ip_regex() {
    local rule="${1:?fleet_ip_regex: rule file required}" prefix
    [ -r "$rule" ] || { echo "fleet IP rule unreadable: ${rule} -- refusing to check against nothing (#19233)" >&2; return 2; }
    prefix=$(grep -oE '\^[0-9]{1,3}\\\.[0-9]{1,3}\\\.[0-9]{1,3}\\\.' "$rule" | head -1 | sed 's/^\^//' | sed 's/\\\././g')
    [ -n "$prefix" ] || { echo "no fleet range found in ${rule} -- refusing to check against nothing (#19233)" >&2; return 2; }
    printf '%s[0-9]{1,3}\n' "$(printf '%s' "$prefix" | sed 's/\./\\./g')"
}
