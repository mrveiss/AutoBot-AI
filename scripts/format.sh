#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Format Python code with the project's pinned Black + isort settings (#7249).
#
# Why this exists:
#   The project pins ``target-version = ["py312"]`` in pyproject.toml. When
#   contributors run plain ``black <file>`` from a host with Python < 3.12,
#   Black silently drops to py3.10 syntax and produces 100+-line spurious
#   diffs against already-formatted code. This wrapper hard-codes the
#   target-version + line-length flags so host Python doesn't matter.
#
# Usage:
#   scripts/format.sh              # format all .py under autobot-{backend,slm-backend}/ + autobot_shared/
#   scripts/format.sh path/to/x    # format specific files/directories
#   scripts/format.sh --check      # CI mode: exit non-zero if anything would be reformatted
#
# Equivalent to ``make format`` / ``make format-check``.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGET_VERSION="py312"
LINE_LENGTH="120"
DEFAULT_PATHS=(autobot-backend autobot-slm-backend autobot_shared)

CHECK_MODE=false
PATHS=()
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_MODE=true ;;
        -h|--help)
            sed -n '/^# Usage:/,/^$/p' "$0"
            exit 0 ;;
        *) PATHS+=("$arg") ;;
    esac
done

if [ "${#PATHS[@]}" -eq 0 ]; then
    PATHS=("${DEFAULT_PATHS[@]}")
fi

# Filter out paths that don't exist (e.g. when running from a worktree
# that hasn't materialised every directory yet).
EXISTING_PATHS=()
for p in "${PATHS[@]}"; do
    [ -e "$p" ] && EXISTING_PATHS+=("$p")
done
if [ "${#EXISTING_PATHS[@]}" -eq 0 ]; then
    echo "format.sh: no input paths exist; nothing to do" >&2
    exit 0
fi

BLACK_ARGS=(--target-version "$TARGET_VERSION" --line-length "$LINE_LENGTH")
ISORT_ARGS=(--profile=black --line-length="$LINE_LENGTH")

if [ "$CHECK_MODE" = true ]; then
    BLACK_ARGS+=(--check)
    ISORT_ARGS+=(--check-only)
fi

# Pick the best-available Python *that has black installed*. The project
# pins py3.12 and Black's safety check parses the AST with whatever
# interpreter we're on — running with py3.10 produces a "cannot parse
# code formatted for Python 3.12" warning AND emits subtly different
# output, which is the whole reason this wrapper exists. We prefer the
# highest Python version that can actually run black (i.e. has it
# installed); if only py3.10 has it, we fall back with a clear warning.
PYTHON_BIN=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -m black --version >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "format.sh: no python3 on PATH has 'black' installed (try: pip install black)" >&2
    exit 1
fi

actual_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
case "$actual_ver" in
    3.12|3.13|3.14) ;;  # Project target — clean run, no parse warnings
    *)
        echo "format.sh: WARNING — using Python $actual_ver but project targets py3.12+." >&2
        echo "  Black will emit a 'cannot parse code formatted for Python 3.12'" >&2
        echo "  warning. Install black on python3.12 to silence:" >&2
        echo "    python3.12 -m pip install black==26.3.1 isort==8.0.1" >&2
        echo "" >&2
        ;;
esac

echo "==> $PYTHON_BIN -m black ${EXISTING_PATHS[*]}" >&2
"$PYTHON_BIN" -m black "${BLACK_ARGS[@]}" "${EXISTING_PATHS[@]}"

echo "==> $PYTHON_BIN -m isort ${EXISTING_PATHS[*]}" >&2
"$PYTHON_BIN" -m isort "${ISORT_ARGS[@]}" "${EXISTING_PATHS[@]}"
