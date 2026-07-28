#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# install_hooks.sh — deprecated shim.
#
# This script used to SYMLINK each tools/git-hooks/<name> into .git/hooks/.
# Those symlinks pointed at worktree paths and dangled the moment a worktree
# was removed, silently disabling hook enforcement (Issue #11598). It now
# delegates to the canonical copy-based installer, which installs real files.
#
# Issue #5142 (original), #11598 (copy-based rewrite).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -z "$REPO_ROOT" ]; then
    echo "ERROR: not inside a git repository" >&2
    exit 1
fi

echo "[install_hooks] delegating to scripts/install-git-hooks.sh (copy-based, real files)" >&2
exec bash "$REPO_ROOT/scripts/install-git-hooks.sh" "$@"
