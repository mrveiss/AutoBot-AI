#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# install_skills.sh — symlink each docs/developer/skills/*.md into the
# Claude Code skill directory at ~/.claude/skills/<name>/SKILL.md
#
# Idempotent: safe to re-run. Existing symlinks pointing at this repo are
# silently refreshed; existing regular files (a previous in-place install)
# are backed up to *.bak before the symlink is created.
#
# Issues #5094, #5447.
set -euo pipefail

# Resolve the canonical primary-checkout root via git-common-dir — this is
# stable across worktree creation/removal, unlike the script's physical
# location (which would capture a transient worktree path).
#
# git-common-dir returns the primary .git directory for both primary and
# worktree checkouts (e.g. /home/user/repo/.git for both cases).
# Its parent directory is the canonical repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# `git rev-parse --git-common-dir` returns a path that may be relative to
# git's invocation directory (SCRIPT_DIR here) — e.g. "../.git", ".git",
# or an absolute path depending on context. Resolve to absolute by
# `cd SCRIPT_DIR` first, so relative paths resolve against a known base.
if ! GIT_COMMON_DIR_RAW="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null)"; then
  echo "ERROR: not inside a git repository (no .git found from $SCRIPT_DIR)" >&2
  exit 1
fi
case "$GIT_COMMON_DIR_RAW" in
  /*) GIT_COMMON_DIR="$GIT_COMMON_DIR_RAW" ;;
  *)  GIT_COMMON_DIR="$(cd "$SCRIPT_DIR" && cd "$GIT_COMMON_DIR_RAW" && pwd)" ;;
esac
REPO_ROOT="$(dirname "$GIT_COMMON_DIR")"
echo "Resolved REPO_ROOT: $REPO_ROOT"
SKILLS_SRC="$REPO_ROOT/docs/developer/skills"
SKILLS_DEST="$HOME/.claude/skills"

if [ ! -d "$SKILLS_SRC" ]; then
  echo "ERROR: skill source directory missing: $SKILLS_SRC" >&2
  exit 1
fi

mkdir -p "$SKILLS_DEST"

INSTALLED=0
SKIPPED=0
BACKED_UP=0

for src_file in "$SKILLS_SRC"/*.md; do
  [ -f "$src_file" ] || continue

  base="$(basename "$src_file" .md)"
  # Skip the README — it documents the directory, it's not a skill.
  if [ "$base" = "README" ]; then
    continue
  fi

  skill_dir="$SKILLS_DEST/$base"
  skill_target="$skill_dir/SKILL.md"
  mkdir -p "$skill_dir"

  if [ -L "$skill_target" ]; then
    # Already a symlink — point it at this repo (idempotent refresh)
    current="$(readlink "$skill_target")"
    if [ "$current" = "$src_file" ]; then
      echo "OK    $base (already symlinked to repo)"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    rm "$skill_target"
  elif [ -f "$skill_target" ]; then
    # Existing regular file — back it up before replacing
    backup="$skill_target.bak.$(date +%Y%m%d-%H%M%S)"
    mv "$skill_target" "$backup"
    echo "BACKUP $base -> $(basename "$backup")"
    BACKED_UP=$((BACKED_UP + 1))
  fi

  ln -s "$src_file" "$skill_target"
  echo "LINK  $base -> $src_file"
  INSTALLED=$((INSTALLED + 1))
done

# Clean up stale symlinks for skills that no longer exist in the repo
# (e.g. after a consolidation like #5454 — team-implement removed).
# Only touch symlinks that already point to files under $SKILLS_SRC; leave
# hand-edited local skills alone.
STALE=0
for skill_dir in "$SKILLS_DEST"/*/; do
  [ -d "$skill_dir" ] || continue
  skill_target="$skill_dir/SKILL.md"
  [ -L "$skill_target" ] || continue

  current="$(readlink "$skill_target")"
  # Only prune symlinks that resolve into our skills source tree
  case "$current" in
    "$SKILLS_SRC"/*)
      if [ ! -e "$current" ]; then
        echo "PRUNE $(basename "$skill_dir")(dangling -> $current)"
        rm "$skill_target"
        rmdir "$skill_dir" 2>/dev/null || true
        STALE=$((STALE + 1))
      fi
      ;;
  esac
done

echo ""
echo "Installed: $INSTALLED  Refreshed: $SKIPPED  Backed up: $BACKED_UP  Pruned: $STALE"
