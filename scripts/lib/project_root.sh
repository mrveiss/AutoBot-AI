#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Canonical project-root resolution for shell scripts (#13149).
#
# Scripts used to paste the default inline:
#
#     BASE_DIR="${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}"
#
# That expands correctly, which is what makes it dangerous: with the variable
# unset, a script run from a checkout silently operates on the *deployed
# install* instead of its own tree. That is #13092 -- `run_agent.sh` deleted the
# live install's frontend node_modules when run from a checkout. One script was
# fixed; the pattern was not, so the next one reintroduces it.
#
# Source this file -- do not execute it. Resolve it from your own location
# rather than via `git rev-parse`, which fails on a deployed install (no .git):
#
#     source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/lib/project_root.sh"
#     echo "$PROJECT_ROOT"
#
# Deliberately mirrors autobot_shared/paths.py, including the worktree
# boundary described below, so the two languages agree on the answer.

# Resolve the project root by walking up from a starting directory.
#
# Order, first match wins:
#   1. $AUTOBOT_PROJECT_ROOT -- an operator saying so outranks inference. This
#      is the same variable the Python side honours, so exporting it once
#      governs both.
#   2. The nearest ancestor holding a .env (a configured deployment) OR
#      carrying both checkout markers (.git and autobot_shared/).
#   3. $AUTOBOT_BASE_DIR, else /opt/autobot.
#
# A checkout root is a hard boundary. This repository's worktrees live at
# <main-tree>/.worktrees/<name>/ and are git-ignored, so a worktree has no .env
# of its own; checking every ancestor for .env first would climb past the
# worktree and match the MAIN tree's .env, pointing the script at another tree.
# `.git` is tested with -e rather than -d because in a worktree it is a FILE.
autobot_project_root() {
    if [ -n "${AUTOBOT_PROJECT_ROOT:-}" ]; then
        printf '%s\n' "${AUTOBOT_PROJECT_ROOT}"
        return 0
    fi

    local dir="${1:?autobot_project_root: starting directory required}"
    dir="$(cd "${dir}" 2>/dev/null && pwd)" || dir=""

    while [ -n "${dir}" ] && [ "${dir}" != "/" ]; do
        if [ -e "${dir}/.env" ] || { [ -e "${dir}/.git" ] && [ -d "${dir}/autobot_shared" ]; }; then
            printf '%s\n' "${dir}"
            return 0
        fi
        dir="$(dirname "${dir}")"
    done

    printf '%s\n' "${AUTOBOT_BASE_DIR:-/opt/autobot}"
}

# Exported on source, resolved from THIS file's location -- scripts/lib/ lives
# inside the checkout, so the walk starts in the right tree no matter where the
# sourcing script sits or what the working directory is.
PROJECT_ROOT="$(autobot_project_root "$(dirname "${BASH_SOURCE[0]}")")"
export PROJECT_ROOT
