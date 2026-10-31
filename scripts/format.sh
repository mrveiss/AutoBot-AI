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

# Pick the best-available Python *that has black installed*. The project runs
# 3.14 and black's safety check parses the AST with whatever interpreter we're
# on — running with py3.10 produces a "cannot parse code formatted for Python
# 3.12" warning AND emits subtly different output, which is the whole reason
# this wrapper exists. We prefer the highest Python version that can actually
# run black (i.e. has it installed); a lower one still runs, with a warning,
# because a formatter that refuses to start is worse than one that warns.
#
# Note the two versions are different things: black *runs* under 3.14, while
# `target-version` in pyproject.toml controls the syntax it *emits* and stays
# at py312 until #13747 has host evidence that the NPU worker is actually
# running 3.14, not merely configured for it (see pyproject.toml).
#
# The CI-parity venv is searched FIRST and by absolute path (#13842 F4). It is
# built by scripts/setup-ci-parity-env.sh at $HOME/.venv-python-suite with the
# same 3.14 CI uses, and it is deliberately NOT on PATH -- so without this the
# search skipped a perfectly good 3.14 sitting on the box and fell through to
# whatever older interpreter happened to have black, which is the drift F4
# describes. Honour CI_PARITY_VENV so the location stays overridable, exactly
# as the setup script does.
#
# The parity venv must BE 3.14 to be worth preferring. CI_PARITY_VENV is
# overridable, so it can point at an older environment that happens to have
# black; selecting that over an available python3.14 would reintroduce the very
# drift this block exists to remove, and the version `case` further down only
# prints a note -- it never revises the choice (CodeRabbit, #13916).
PYTHON_BIN=""
PARITY_PY="${CI_PARITY_VENV:-$HOME/.venv-python-suite}/bin/python"
if [ -x "$PARITY_PY" ] && "$PARITY_PY" -m black --version >/dev/null 2>&1; then
    parity_ver=$("$PARITY_PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
    if [ "$parity_ver" = "3.14" ]; then
        PYTHON_BIN="$PARITY_PY"
    else
        echo "format.sh: NOTE — the parity venv is Python ${parity_ver:-unknown}, not 3.14; searching PATH instead." >&2
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -m black --version >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "format.sh: no python3 on PATH has 'black' installed (try: pip install black)" >&2
    exit 1
fi

actual_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
case "$actual_ver" in
    3.14) ;;  # What CI runs — clean run, output matches the check
    3.12 | 3.13)
        echo "format.sh: NOTE — using Python $actual_ver; CI formats with 3.14." >&2
        echo "  Parses cleanly, but if CI's format check disagrees with a local" >&2
        echo "  clean run, this gap is the first thing to rule out." >&2
        echo "" >&2
        ;;
    *)
        echo "format.sh: WARNING — using Python $actual_ver but the project runs 3.14." >&2
        echo "  Black's output can differ from CI's at this version, so a clean" >&2
        echo "  local run may still fail the CI format check." >&2
        echo "  Fixing this needs a Python 3.14 interpreter on the box first:" >&2
        echo "  setup-ci-parity-env.sh builds the VENV, not the interpreter, and" >&2
        echo "  exits if it cannot find 3.14 (install it via your OS package" >&2
        echo "  manager, or point CI_PARITY_PYTHON at one). With 3.14 present:" >&2
        echo "    bash scripts/setup-ci-parity-env.sh" >&2
        echo "  builds CI's env at \$HOME/.venv-python-suite without sudo and" >&2
        echo "  installs nothing outside it; format.sh then finds it itself." >&2
        echo "" >&2
        ;;
esac

echo "==> $PYTHON_BIN -m black ${EXISTING_PATHS[*]}" >&2
"$PYTHON_BIN" -m black "${BLACK_ARGS[@]}" "${EXISTING_PATHS[@]}"

echo "==> $PYTHON_BIN -m isort ${EXISTING_PATHS[*]}" >&2
"$PYTHON_BIN" -m isort "${ISORT_ARGS[@]}" "${EXISTING_PATHS[@]}"
