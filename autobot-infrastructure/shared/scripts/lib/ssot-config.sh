#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Shell-side Single Source of Truth reader (#14041).
#
# 56 scripts under autobot-infrastructure/ have always done:
#
#     source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || true
#
# and this file has never existed, so every ${VAR:-literal} in those scripts has
# always silently taken its hardcoded fallback. This file is what they were always
# meant to source. It mirrors autobot_shared/ssot_config.py's Pydantic field
# defaults (the canonical SSOT the Python side reads) rather than inventing a
# second source of truth: same .env file, same default values, only exported as
# plain shell variables instead of typed Pydantic fields.
#
# Scope note (#14041 enumeration, docs/audit/ssot_config_shell_library_14041.md):
# this file exports exactly the variables the 56 scripts were proven to consume.
# It deliberately does NOT export AUTOBOT_SSH_KEY, AUTOBOT_SSH_USER,
# AUTOBOT_SLM_NODE_ID, or the four AUTOBOT_VNC_* names some scripts also read --
# none of those has a canonical value anywhere (not autobot_shared/ssot_config.py,
# not .env.example, not the Ansible group_vars). Inventing a default for them here
# would be a second source of truth, which is exactly the failure mode this file
# exists to end. Those scripts keep their own literal fallback unchanged.
#
# Source this file -- do not execute it.

# Idempotent: several of the 56 callers are sourced by other scripts in this set
# (e.g. utilities/check-time-sync.sh sourcing this indirectly through a shared
# helper), so a second `source` must be a fast no-op rather than re-running the
# .env load and re-declaring VMS.
if [ -n "${_AUTOBOT_SSOT_CONFIG_LOADED:-}" ]; then
    return 0 2>/dev/null || exit 0
fi
_AUTOBOT_SSOT_CONFIG_LOADED=1

# ---------------------------------------------------------------------------
# 1. Resolve PROJECT_ROOT the same way every other shell consumer does (#13149).
#    Prefer the canonical resolver (scripts/lib/project_root.sh) over
#    reimplementing the walk-up-for-.env logic a second time; fall back to a
#    minimal inline walk if the checkout layout doesn't have it (e.g. a
#    deployed install that only ships autobot-infrastructure/).
# ---------------------------------------------------------------------------
if [ -z "${PROJECT_ROOT:-}" ]; then
    _ssot_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
    _ssot_resolver="${_ssot_lib_dir}/../../../../scripts/lib/project_root.sh"
    if [ -n "${_ssot_lib_dir}" ] && [ -f "${_ssot_resolver}" ]; then
        # shellcheck source=/dev/null
        source "${_ssot_resolver}"
    else
        _ssot_walk="${_ssot_lib_dir:-.}"
        while [ -n "${_ssot_walk}" ] && [ "${_ssot_walk}" != "/" ] && [ ! -e "${_ssot_walk}/.env" ]; do
            _ssot_walk="$(dirname "${_ssot_walk}")"
        done
        PROJECT_ROOT="${_ssot_walk:-${AUTOBOT_BASE_DIR:-/opt/autobot}}"
        unset _ssot_walk
    fi
    unset _ssot_lib_dir _ssot_resolver
fi
export PROJECT_ROOT

# ---------------------------------------------------------------------------
# 2. Load the master .env -- the exact file autobot_shared/ssot_config.py reads
#    (env_file=PROJECT_ROOT/.env). Same mechanism used by the pre-existing
#    "lib not found" fallback block in check_status.sh and friends: `set -a`
#    around a plain source, so every KEY=VALUE line becomes an exported var.
#    A missing .env (dev checkout with no deployment configured) is normal --
#    the defaults below cover that case.
#
#    Guarded, not bare: an ordinary authoring mistake in .env (an unescaped
#    $(...) or backtick) executes as a command substitution and can fail. A
#    bare `source` here would propagate that failure to a `set -e` caller and
#    kill it with NO output (stderr was being discarded) -- the worst outcome
#    for something like vm-management/status-all-vms.sh, a health-check
#    script. `if ! source ...` catches the failure so `set -e` never sees an
#    uncaught error, and a message goes to stderr either way.
# ---------------------------------------------------------------------------
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    if ! source "${PROJECT_ROOT}/.env"; then
        echo "ssot-config.sh: WARNING: ${PROJECT_ROOT}/.env did not source cleanly (see the error above this line) -- continuing with whatever it set before failing, plus SSOT defaults for the rest" >&2
    fi
    set +a
fi

# ---------------------------------------------------------------------------
# 3. Defaults -- one per variable the #14041 enumeration proved is consumed by
#    the 56 scripts AND has a canonical value. Values match
#    autobot_shared/ssot_config.py field-for-field:
#      VMConfig, PortConfig, RedisConfig (autobot_shared/ssot_config.py).
#    `:=` only assigns when the variable is unset or empty, so a value already
#    exported by .env above (or by the calling script/environment) always wins.
# ---------------------------------------------------------------------------

# VMConfig -- Issue #2953: 127.0.0.1 for single-host installs, overridden by
# .env AUTOBOT_*_HOST on distributed installs.
: "${AUTOBOT_BACKEND_HOST:=127.0.0.1}"
: "${AUTOBOT_FRONTEND_HOST:=127.0.0.1}"
: "${AUTOBOT_NPU_WORKER_HOST:=127.0.0.1}"
: "${AUTOBOT_REDIS_HOST:=127.0.0.1}"
: "${AUTOBOT_AI_STACK_HOST:=127.0.0.1}"
: "${AUTOBOT_BROWSER_SERVICE_HOST:=127.0.0.1}"
: "${AUTOBOT_SLM_HOST:=127.0.0.1}"
: "${AUTOBOT_OLLAMA_HOST:=127.0.0.1}"

# PortConfig
: "${AUTOBOT_BACKEND_PORT:=8001}"
: "${AUTOBOT_FRONTEND_PORT:=5173}"
: "${AUTOBOT_NPU_WORKER_PORT:=8081}"
: "${AUTOBOT_REDIS_PORT:=6379}"
: "${AUTOBOT_AI_STACK_PORT:=8080}"
# Issue #4052: 9001 is the browser service; 3000 is Grafana. Several of the 56
# scripts hardcoded 3000 for this port before this file existed -- see the
# divergence table in docs/audit/ssot_config_shell_library_14041.md.
: "${AUTOBOT_BROWSER_SERVICE_PORT:=9001}"
: "${AUTOBOT_OLLAMA_PORT:=11434}"
: "${AUTOBOT_VNC_PORT:=6080}"

# RedisConfig
: "${AUTOBOT_REDIS_PASSWORD:=}"
: "${AUTOBOT_REDIS_DB_CELERY_BROKER:=14}"
: "${AUTOBOT_REDIS_DB_CELERY_RESULTS:=15}"

# MiscConfig / standalone fields
: "${AUTOBOT_NOVNC_PATH:=/opt/novnc}"
: "${NETWORK_SUBNET:=}"

export AUTOBOT_BACKEND_HOST AUTOBOT_FRONTEND_HOST AUTOBOT_NPU_WORKER_HOST \
    AUTOBOT_REDIS_HOST AUTOBOT_AI_STACK_HOST AUTOBOT_BROWSER_SERVICE_HOST \
    AUTOBOT_SLM_HOST AUTOBOT_OLLAMA_HOST \
    AUTOBOT_BACKEND_PORT AUTOBOT_FRONTEND_PORT AUTOBOT_NPU_WORKER_PORT \
    AUTOBOT_REDIS_PORT AUTOBOT_AI_STACK_PORT AUTOBOT_BROWSER_SERVICE_PORT \
    AUTOBOT_OLLAMA_PORT AUTOBOT_VNC_PORT \
    AUTOBOT_REDIS_PASSWORD AUTOBOT_REDIS_DB_CELERY_BROKER AUTOBOT_REDIS_DB_CELERY_RESULTS \
    AUTOBOT_NOVNC_PATH NETWORK_SUBNET

# ---------------------------------------------------------------------------
# 4. VMS associative array -- vm-management/status-all-vms.sh is the one script
#    in the 56 that never declares its own VMS array (its comment says "VMS
#    array is provided by ssot-config.sh"). Guarded so a caller that already
#    declared its own VMS (several other scripts in the 56 do) is untouched.
# ---------------------------------------------------------------------------
if ! declare -p VMS >/dev/null 2>&1; then
    declare -A VMS=(
        ["frontend"]="${AUTOBOT_FRONTEND_HOST}"
        ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST}"
        ["redis"]="${AUTOBOT_REDIS_HOST}"
        ["ai-stack"]="${AUTOBOT_AI_STACK_HOST}"
        ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST}"
    )
fi
