#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# install_skills.sh — symlink each docs/developer/skills/*.md into the
# Claude Code skill directory at ~/.claude/skills/<name>/SKILL.md
#
# Idempotent: safe to re-run. Existing symlinks pointing at this repo are
# silently refreshed; existing regular files (a previous in-place install)
# are backed up to *.bak before the symlink is created.
#
# Issue #5094.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

echo ""
echo "Installed: $INSTALLED  Refreshed: $SKIPPED  Backed up: $BACKED_UP"
