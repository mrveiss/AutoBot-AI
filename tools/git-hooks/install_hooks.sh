#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# install_hooks.sh — symlink each tools/git-hooks/<name> into .git/hooks/<name>
# so they run on the next git operation.
#
# Idempotent: safe to re-run. Existing symlinks pointing at this repo are
# refreshed; existing regular files are backed up to *.bak.<timestamp>.
#
# Issue #5142.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOKS_SRC="$REPO_ROOT/tools/git-hooks"

# Use --git-common-dir so this works inside worktrees too. In a worktree,
# `.git` is a file pointing at .git/worktrees/<name>/, but hooks live in
# the main repo's .git/hooks/ shared across all worktrees.
GIT_COMMON_DIR="$(git rev-parse --git-common-dir 2>/dev/null || echo "")"
if [ -z "$GIT_COMMON_DIR" ]; then
  echo "ERROR: not inside a git repository" >&2
  exit 1
fi

# Resolve to absolute path (--git-common-dir may return a relative path)
case "$GIT_COMMON_DIR" in
  /*) HOOKS_DEST="$GIT_COMMON_DIR/hooks" ;;
  *)  HOOKS_DEST="$(cd "$GIT_COMMON_DIR" && pwd)/hooks" ;;
esac

if [ ! -d "$HOOKS_SRC" ]; then
  echo "ERROR: hook source directory missing: $HOOKS_SRC" >&2
  exit 1
fi

mkdir -p "$HOOKS_DEST"

INSTALLED=0
SKIPPED=0
BACKED_UP=0

for src_file in "$HOOKS_SRC"/*; do
  [ -f "$src_file" ] || continue
  base="$(basename "$src_file")"

  # Skip non-hook files (README, install_hooks.sh itself)
  case "$base" in
    README*|install_hooks.sh|*.md)
      continue
      ;;
  esac

  hook_target="$HOOKS_DEST/$base"

  if [ -L "$hook_target" ]; then
    current="$(readlink "$hook_target")"
    if [ "$current" = "$src_file" ]; then
      echo "OK    $base (already symlinked to repo)"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    rm "$hook_target"
  elif [ -f "$hook_target" ]; then
    backup="$hook_target.bak.$(date +%Y%m%d-%H%M%S)"
    mv "$hook_target" "$backup"
    echo "BACKUP $base -> $(basename "$backup")"
    BACKED_UP=$((BACKED_UP + 1))
  fi

  ln -s "$src_file" "$hook_target"
  chmod +x "$src_file"  # ensure executable for git
  echo "LINK  $base -> $src_file"
  INSTALLED=$((INSTALLED + 1))
done

echo ""
echo "Installed: $INSTALLED  Refreshed: $SKIPPED  Backed up: $BACKED_UP"
echo ""
echo "Bypass an installed hook with: git push --no-verify (don't unless you must)"
