#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# The ONE shell lookup for the platform's Python floor interpreter (#20932).
#
# `.python-version` is the single declaration of the interpreter every node
# venv must be built on (#13842). Deploy scripts used to run a bare
# `python3 -m venv`, which builds the venv on whatever the node ships; once
# autobot_shared refuses interpreters below the floor at import (#20903) that
# venv is unusable. Source this file -- or execute it -- instead of restating
# the version:
#
#     source "$PROJECT_ROOT/scripts/lib/python_floor.sh"
#     PY="$(python_floor_ensure "$PROJECT_ROOT")" || exit 1
#     "$PY" -m venv venv
#
#     scripts/lib/python_floor.sh ensure [ROOT]   # prints the binary name
#
# Subcommands / functions (ROOT defaults to this file's own checkout):
#   version   X.Y read from ROOT/.python-version; refuses on anything else
#   binary    pythonX.Y
#   ensure    binary, after provisioning it from deadsnakes (the same source
#             install.sh uses) when missing; refuses with a clear message if it
#             cannot. AUTOBOT_PYTHON_FLOOR_NO_PROVISION=1 turns provisioning off.
#   remote_venv_cmd ROOT DIR   one command: provision-or-refuse, then `-m venv DIR`
#   provision_cmd BINARY   the apt commands, single-quote-free so a caller can
#             run them through `ssh host "sudo bash -c '...'"`.
#
# There is deliberately no fallback version: an unreadable `.python-version`
# is a refusal, never a guess.

_python_floor_default_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

python_floor_version() {
    local root="${1:-$(_python_floor_default_root)}" text=""
    [ -r "$root/.python-version" ] && IFS= read -r text < "$root/.python-version"
    text="${text//[[:space:]]/}"
    if ! [[ "$text" =~ ^[0-9]+\.[0-9]+$ ]]; then
        echo "python_floor: $root/.python-version is missing or not X.Y (got '${text}'); refusing to guess an interpreter" >&2
        return 1
    fi
    echo "$text"
}

python_floor_binary() {
    local version
    version="$(python_floor_version "${1:-}")" || return 1
    echo "python${version}"
}

python_floor_provision_cmd() {
    local bin="$1"
    echo "apt-get install -y software-properties-common && add-apt-repository -y ppa:deadsnakes/ppa && apt-get update -qq && apt-get install -y ${bin} ${bin}-venv ${bin}-dev"
}

# One single-quote-free command that provisions BIN if missing, refuses clearly if
# it still is not there, then creates DIR as a venv on it. For a caller that runs
# it on another host (`ssh host "sudo bash -c '...'"`). Never fails locally: an
# unreadable `.python-version` yields a command that refuses on the far side, so
# nothing runs on a guessed interpreter.
python_floor_remote_venv_cmd() {
    local bin
    if ! bin="$(python_floor_binary "${1:-}" 2>/dev/null)"; then
        echo "echo .python-version is missing or not X.Y - refusing to guess an interpreter >&2; exit 1"
        return 0
    fi
    echo "command -v ${bin} >/dev/null 2>&1 || { $(python_floor_provision_cmd "$bin"); }; command -v ${bin} >/dev/null 2>&1 || { echo ${bin} is required and could not be installed >&2; exit 1; }; ${bin} -m venv ${2}"
}

_python_floor_run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        bash -c "$1"
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo bash -c "$1"
    else
        return 1
    fi
}

python_floor_ensure() {
    local bin
    bin="$(python_floor_binary "${1:-}")" || return 1
    if command -v "$bin" >/dev/null 2>&1; then
        echo "$bin"
        return 0
    fi
    if [ "${AUTOBOT_PYTHON_FLOOR_NO_PROVISION:-0}" != "1" ] && command -v apt-get >/dev/null 2>&1; then
        echo "python_floor: $bin not found; installing from deadsnakes" >&2
        _python_floor_run_privileged "$(python_floor_provision_cmd "$bin")" >&2 || true
    fi
    if command -v "$bin" >/dev/null 2>&1; then
        echo "$bin"
        return 0
    fi
    echo "python_floor: $bin is required (the .python-version floor) and is not installed; install it (deadsnakes: $(python_floor_provision_cmd "$bin")) and re-run" >&2
    return 1
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "${1:-}" in
        version) python_floor_version "${2:-}" ;;
        binary) python_floor_binary "${2:-}" ;;
        ensure) python_floor_ensure "${2:-}" ;;
        *) echo "usage: $0 {version|binary|ensure} [ROOT]" >&2; exit 2 ;;
    esac
fi
