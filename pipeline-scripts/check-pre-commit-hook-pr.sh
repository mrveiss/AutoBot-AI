#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Generic CI wrapper for pre-commit hooks and Python validators.
# Issue #6785 (follow-up to #6725 / #6783): closes the bypass gap for
# pre-commit hooks across the board, not just hardcoded-values.
# Issue #6991: extended to also support Python validators (tools/lint/*.py)
# so the two per-hook wrappers (check-hardcoded-values-pr.sh,
# check-hardcoded-ip-fallbacks-pr.sh) can be retired in favour of this one.
#
# Each hook gets an argv mode (positional args = files to scan, no args =
# fall back to git diff --cached). This wrapper computes the changed-file
# set for the PR/push context and invokes the hook in argv mode.
#
# Usage:
#   bash pipeline-scripts/check-pre-commit-hook-pr.sh <hook-name>
#   bash pipeline-scripts/check-pre-commit-hook-pr.sh --python <validator-path> [--ext py,ts,...]
#
# Examples (in GitHub Actions steps):
#   - run: bash pipeline-scripts/check-pre-commit-hook-pr.sh pre-commit-no-print-console
#   - run: bash pipeline-scripts/check-pre-commit-hook-pr.sh --python tools/lint/check_no_hardcoded_ip_fallbacks.py
#   - run: bash pipeline-scripts/check-pre-commit-hook-pr.sh --python tools/lint/check_no_hardcoded_ip_fallbacks.py --ext py
#
# Inputs (env, all optional — defaults derived from git/GH Actions):
#   BASE_SHA          explicit PR base SHA
#   HEAD_SHA          explicit head SHA (default: HEAD or GITHUB_SHA)
#   GITHUB_BASE_REF   PR target branch (set by GH Actions)
#   GITHUB_SHA        commit SHA (set by GH Actions)
#
# Bash hook requirements:
#   1. Live at autobot-infrastructure/shared/scripts/hooks/<hook-name>
#   2. Accept positional args as a file list (override git diff --cached)
#   3. Exit 1 on violations, 0 on clean
#
# Python validator requirements:
#   1. Accept positional file paths as arguments
#   2. Exit 1 on violations, 0 on clean

set -euo pipefail

# ── Argument parsing ─────────────────────────────────────────────────────────

USE_PYTHON=false
VALIDATOR_PATH=""
HOOK_NAME=""
EXT_GLOB="*.py *.ts *.tsx *.vue *.js *.mjs"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <hook-name>" >&2
    echo "       $0 --python <validator-path> [--ext py,ts,...]" >&2
    exit 2
fi

if [ "$1" = "--python" ]; then
    USE_PYTHON=true
    if [ "$#" -lt 2 ]; then
        echo "Usage: $0 --python <validator-path> [--ext py,ts,...]" >&2
        exit 2
    fi
    VALIDATOR_PATH="$2"
    shift 2
    # Optional --ext override: comma-separated extensions without dots
    if [ "${1:-}" = "--ext" ]; then
        if [ "${2:-}" = "" ]; then
            echo "--ext requires a comma-separated list of extensions" >&2
            exit 2
        fi
        EXT_GLOB=$(echo "$2" | tr ',' '\n' | sed 's/^/\*./' | tr '\n' ' ')
        shift 2
    fi
    if [ ! -f "$VALIDATOR_PATH" ]; then
        echo "Python validator not found: $VALIDATOR_PATH" >&2
        exit 2
    fi
else
    HOOK_NAME="$1"
    HOOK_PATH="$(dirname "$0")/../autobot-infrastructure/shared/scripts/hooks/${HOOK_NAME}"
    if [ ! -f "$HOOK_PATH" ]; then
        echo "Hook script not found: $HOOK_PATH" >&2
        exit 2
    fi
fi

# ── Changed-file set ─────────────────────────────────────────────────────────

BASE_SHA="${BASE_SHA:-}"
HEAD_SHA="${HEAD_SHA:-${GITHUB_SHA:-HEAD}}"

if [ -z "$BASE_SHA" ] && [ -n "${GITHUB_BASE_REF:-}" ]; then
    BASE_SHA=$(git rev-parse "origin/${GITHUB_BASE_REF}" 2>/dev/null || true)
fi

if [ -n "$BASE_SHA" ]; then
    base="$BASE_SHA"
else
    base="${HEAD_SHA}^"
fi

# Cast a wide net (all relevant source extensions); the hook/validator itself
# applies its category-specific allowlist.
# shellcheck disable=SC2086
files=$(git diff --name-only "$base" "$HEAD_SHA" -- $EXT_GLOB \
    | while read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done \
    || true)

if [ -z "$files" ]; then
    if $USE_PYTHON; then
        echo "No changed source files — skipping ${VALIDATOR_PATH}."
    else
        echo "No changed source files — skipping ${HOOK_NAME}."
    fi
    exit 0
fi

count=$(echo "$files" | wc -l)

# ── Invocation ────────────────────────────────────────────────────────────────

if $USE_PYTHON; then
    echo "Running ${VALIDATOR_PATH} against $count changed file(s)..."
    # shellcheck disable=SC2086
    echo "$files" | xargs python3 "$VALIDATOR_PATH"
else
    echo "Running ${HOOK_NAME} against $count changed file(s)..."
    # shellcheck disable=SC2086
    bash "$HOOK_PATH" $files
fi
