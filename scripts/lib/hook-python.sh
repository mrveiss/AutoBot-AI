# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# The ONE interpreter resolver for every git hook (#21163; witnesses #16510,
# #17945, #18029).
#
# A hook that runs a bare `python3` gets whichever interpreter is first on PATH
# (3.10 on Ubuntu 22.04), and `autobot_shared` refuses to import below the
# `.python-version` floor. Every hook wrapper and hook script that runs Python
# resolves it here instead; repo_tests/hook_interpreter_resolver_21163_test.py
# fails on any that does not.
#
# Sourced via:
#   source "<repo>/scripts/lib/hook-python.sh"
#
# Provides:
# - resolve_repo_python [--root DIR] [--require MODULE]...
#     prints the interpreter on stdout. Order:
#       1. $VIRTUAL_ENV, then the checkout's venv/ and .venv/ (and the main
#          checkout's, from a worktree)
#       2. python<.python-version> on PATH
#       3. python3 / python, but ONLY when it verifiably meets the floor
#     Every candidate must meet the floor and import each --require module.
#     With none, prints a message naming the required version to stderr and
#     returns 1 -- it never hands back an older interpreter to fail later.
#     --root defaults to the checkout this file lives in.

if [ -n "${_AUTOBOT_HOOK_PYTHON_LOADED:-}" ]; then
    return 0
fi
_AUTOBOT_HOOK_PYTHON_LOADED=1

_AUTOBOT_PYTHON_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prints "<major> <minor>" from <root>/.python-version; returns 1 when unreadable.
_hook_python_floor() {
    local text="" major minor
    [ -r "$1/.python-version" ] && IFS= read -r text < "$1/.python-version"
    case "$text" in
        ([0-9]*.[0-9]*) [ -z "${text//[0-9.]/}" ] || return 1 ;;
        (*) return 1 ;;
    esac
    IFS=. read -r major minor _ <<< "$text"
    printf '%s %s' "$major" "$minor"
}

# 0 when "$1" is executable, meets the floor ($2 $3) and imports every module in $4...
_hook_python_qualifies() {
    local candidate="$1" major="$2" minor="$3" module
    shift 3
    { command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; } || return 1
    "$candidate" -c "import sys; sys.exit(sys.version_info[:2] < ($major, $minor))" 2>/dev/null || return 1
    for module in "$@"; do
        "$candidate" -c "import $module" 2>/dev/null || return 1
    done
}

resolve_repo_python() {
    local root="$_AUTOBOT_PYTHON_LIB_DIR/../.." modules=() floor major minor
    while [ $# -gt 0 ]; do
        case "$1" in
            (--root) root="$2"; shift 2 ;;
            (--require) modules+=("$2"); shift 2 ;;
            (*) echo "resolve_repo_python: unknown argument '$1'" >&2; return 2 ;;
        esac
    done
    root="$(cd "$root" 2>/dev/null && pwd)" || { echo "resolve_repo_python: cannot enter the repo root" >&2; return 1; }
    if ! floor="$(_hook_python_floor "$root")"; then
        echo "resolve_repo_python: cannot read the required Python version from $root/.python-version" >&2
        return 1
    fi
    read -r major minor <<< "$floor"
    # A worktree has no venv of its own; it lives in the main checkout, the
    # parent of the common git dir.
    local main_root candidate
    main_root="$(cd "$root" && cd "$(dirname "$(git rev-parse --git-common-dir 2>/dev/null || echo .)")" 2>/dev/null && pwd)" || main_root="$root"
    for candidate in ${VIRTUAL_ENV:+"$VIRTUAL_ENV/bin/python"} \
                     "$root/venv/bin/python" "$root/.venv/bin/python" \
                     "$main_root/venv/bin/python" "$main_root/.venv/bin/python" \
                     "python${major}.${minor}" python3 python; do
        if _hook_python_qualifies "$candidate" "$major" "$minor" "${modules[@]}"; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    echo "ERROR: no Python ${major}.${minor}+ interpreter found${modules[*]:+ with: ${modules[*]}}." >&2
    echo "  .python-version requires ${major}.${minor}; autobot_shared refuses anything older at import." >&2
    echo "  Install python${major}.${minor}, or create the repo venv (venv/ or .venv/) and re-run." >&2
    echo "  (A system python3 below ${major}.${minor} is deliberately not used.)" >&2
    return 1
}
