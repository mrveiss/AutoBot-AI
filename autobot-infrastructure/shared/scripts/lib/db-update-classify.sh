#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Pure classification of a `psql -c "UPDATE ..."` result (#14459).
#
# Before this file existed, sync-to-slm.sh checked only `$?` after the ssh
# command that runs the UPDATE: nonzero was logged as a non-critical warning,
# and zero was always logged as "Database updated" -- even when the UPDATE's
# WHERE clause matched no row. `psql` exits 0 for a no-op UPDATE (that is not
# a SQL error), so a renamed node (#9956 made node_id overridable) or any
# other id mismatch produced a "Database updated" log line while the row
# stayed exactly as stale as it was before the deploy. That is worse than a
# command failure, because the failure path at least warned.
#
# `psql`'s command-completion tag ("UPDATE <n>") is the only place the
# affected row count is reported for a plain `-c` invocation, and it is
# printed on its own line -- not necessarily the only line, since ssh may
# prepend a host-key warning to the combined stdout+stderr capture callers
# pass in here. classify_db_update_result treats that tag as authoritative
# and checks it per-line (grep, not a whole-string anchor) for exactly that
# reason.
#
# No side effects: this file defines one function and does not call ssh,
# psql, or rsync. Source it -- do not execute it.

# classify_db_update_result <exit_code> <captured_output>
#
# Echoes exactly one of:
#   updated   -- the UPDATE affected one or more rows
#   no_match  -- the command succeeded but the WHERE clause matched no row
#   failed    -- the ssh/psql command itself returned a nonzero exit code
classify_db_update_result() {
    local exit_code="$1"
    local output="$2"

    if [ "${exit_code}" -ne 0 ]; then
        echo "failed"
        return 0
    fi

    if printf '%s\n' "${output}" | grep -qE '^UPDATE 0[[:space:]]*$'; then
        echo "no_match"
        return 0
    fi

    echo "updated"
}
