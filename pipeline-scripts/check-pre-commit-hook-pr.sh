#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
# An ARRAY, not a string (#13880). As a string it was passed unquoted to
# `git diff -- $EXT_GLOB`, so the SHELL expanded the globs against the cwd
# before git saw them. In CI the cwd is the repo root, where `*.py` matches
# only the handful of root-level Python files — so the pathspec silently
# collapsed to those, and changed files under autobot-backend/ etc. were never
# scanned. `*.ts`/`*.vue`/`*.js` had no root matches, stayed literal, and were
# handled correctly by git, which is why the gap only affected Python.
EXT_PATHSPEC=('*.py' '*.ts' '*.tsx' '*.vue' '*.js' '*.mjs')

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
        EXT_PATHSPEC=()
        # `|| [ -n "$_ext" ]` catches the final field: tr leaves no trailing
        # newline, so a plain `read` drops the last (or only) extension.
        while IFS= read -r _ext || [ -n "$_ext" ]; do
            [ -n "$_ext" ] && EXT_PATHSPEC+=("*.${_ext}")
        done < <(printf '%s' "$2" | tr ',' '\n')
        if [ "${#EXT_PATHSPEC[@]}" -eq 0 ]; then
            echo "--ext produced no usable extensions" >&2
            exit 2
        fi
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

# A guard that cannot compute its scope must FAIL, never report "nothing
# changed" (#13880). actions/checkout defaults to fetch-depth: 1, so the PR
# base commit is absent, `git diff` fatals, the old `|| true` swallowed it, and
# an empty file list printed "No changed source files — skipping" and exited 0.
# Four CI steps were green no-ops for exactly this reason.
for _ref in "$base" "$HEAD_SHA"; do
    if ! git cat-file -e "${_ref}^{commit}" 2>/dev/null; then
        echo "FATAL: '${_ref}' does not resolve in this clone." >&2
        echo "  A shallow checkout cannot diff against the base — set 'fetch-depth: 0'" >&2
        echo "  on actions/checkout. Refusing to report 'no changed files' for a" >&2
        echo "  scope that could not be computed." >&2
        exit 1
    fi
done

# Cast a wide net (all relevant source extensions); the hook/validator itself
# applies its category-specific allowlist. Quoted array expansion — git must
# receive the globs verbatim and do its own pathspec matching.
if ! raw_files=$(git diff --name-only "$base" "$HEAD_SHA" -- "${EXT_PATHSPEC[@]}"); then
    echo "FATAL: git diff failed for ${base}..${HEAD_SHA} — refusing to report clean." >&2
    exit 1
fi

# Deleted paths still appear in the diff; keep only files that exist on disk.
# The trailing `|| true` normalises the while-loop's EOF exit status (1) under
# `set -e`. It is scoped to the FILTER only — git's exit status is checked
# above, so this no longer hides a failed diff the way the original did.
files=$(printf '%s\n' "$raw_files" \
    | while read -r f; do [ -n "$f" ] && [ -f "$f" ] && printf '%s\n' "$f"; done \
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
