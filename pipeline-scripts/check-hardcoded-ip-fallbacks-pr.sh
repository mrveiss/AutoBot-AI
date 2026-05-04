#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# CI wrapper for tools/lint/check_no_hardcoded_ip_fallbacks.py.
# Issue #6783: AST-aware regression check for os.getenv("...", "172.16.168.X")
# fallback patterns that the bash-based hardcoded-values hook (#6725)
# silently allows.
#
# Inputs (env, all optional — sensible defaults derive from git):
#   BASE_SHA          explicit PR base SHA
#   HEAD_SHA          explicit head SHA (default: HEAD or GITHUB_SHA)
#   GITHUB_BASE_REF   PR target branch name (set automatically by GH Actions)
#   GITHUB_SHA        commit SHA (set automatically by GH Actions)

set -euo pipefail

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

files=$(git diff --name-only "$base" "$HEAD_SHA" -- '*.py' \
    | while read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done \
    || true)

if [ -z "$files" ]; then
    echo "No changed Python files — skipping hardcoded-IP fallback check."
    exit 0
fi

count=$(echo "$files" | wc -l)
echo "Checking $count changed .py file(s) for hardcoded-IP fallbacks..."
# shellcheck disable=SC2086
echo "$files" | xargs python3 tools/lint/check_no_hardcoded_ip_fallbacks.py
