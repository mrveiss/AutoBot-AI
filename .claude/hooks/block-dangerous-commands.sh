#!/bin/bash
# Blocks dangerous shell commands before execution.
# PreToolUse hook for Bash operations.
# Exit 2 = block the action. Exit 0 = allow.
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# Issue: #3021

if ! command -v jq >/dev/null 2>&1; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"jq is required for command protection hooks but is not installed."}}'
  exit 2
fi

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

deny() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 2
}

# ──────────────────────────────────────────────
# Git push protections
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qE '(^|[;&|()]+[[:space:]]*)git[[:space:]]+push'; then

  # Block push to main, master, or Dev_new_gui directly
  if echo "$COMMAND" | grep -qE 'git[[:space:]]+push.*(origin[[:space:]]+|:)(main|master|Dev_new_gui)\b'; then
    deny "Blocked: cannot push directly to main/master/Dev_new_gui. Use a feature branch and create a PR."
  fi

  # Block bare git push when on protected branches
  if echo "$COMMAND" | grep -qE 'git[[:space:]]+push[[:space:]]*($|[;&|])'; then
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
    if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ] || [ "$CURRENT_BRANCH" = "Dev_new_gui" ]; then
      deny "Blocked: you are on $CURRENT_BRANCH. Use a feature branch and create a PR."
    fi
  fi

  # Block force push (allow --force-with-lease)
  if echo "$COMMAND" | grep -qE 'git[[:space:]]+push.*(-[a-zA-Z]*f|--force)([[:space:]]|$)' && ! echo "$COMMAND" | grep -q '\-\-force-with-lease'; then
    deny "Blocked: force push is not allowed. Use --force-with-lease if you need to overwrite remote."
  fi
fi

# ──────────────────────────────────────────────
# Git commit protections
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qE 'git[[:space:]]+commit.*--no-verify'; then
  deny "Blocked: --no-verify bypasses pre-commit hooks. Fix the underlying hook failure instead."
fi

# ──────────────────────────────────────────────
# Destructive git operations
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qE 'git[[:space:]]+reset[[:space:]]+--hard'; then
  deny "Blocked: git reset --hard discards uncommitted changes permanently. Use git stash or git reset --soft instead."
fi

if echo "$COMMAND" | grep -qE 'git[[:space:]]+clean[[:space:]]+-[a-zA-Z]*f'; then
  deny "Blocked: git clean -f permanently deletes untracked files. Review with git clean -n first, then run manually if intended."
fi

# ──────────────────────────────────────────────
# Destructive filesystem operations
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*r[a-zA-Z]*f[[:space:]]+(\/|~|\$HOME|\.\.\/\.\.)'; then
  deny "Blocked: recursive force-delete on root/home/parent paths. Specify a safe target directory."
fi

if echo "$COMMAND" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*r.*[[:space:]]+(\/[[:space:]]|\/\*|\/$|~\/?\*?[[:space:]]|~\/?\*?$)'; then
  deny "Blocked: recursive delete targeting root or home directory."
fi

# ──────────────────────────────────────────────
# Dangerous database operations
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qiE 'DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)[[:space:]]'; then
  deny "Blocked: DROP TABLE/DATABASE/SCHEMA detected. This is destructive and irreversible. Run manually if intended."
fi

if echo "$COMMAND" | grep -qiE 'DELETE[[:space:]]+FROM[[:space:]]+[a-zA-Z_]+[[:space:]]*($|;)' && ! echo "$COMMAND" | grep -qiE 'WHERE'; then
  deny "Blocked: DELETE FROM without WHERE clause would delete all rows. Add a WHERE clause."
fi

if echo "$COMMAND" | grep -qiE 'TRUNCATE[[:space:]]+TABLE'; then
  deny "Blocked: TRUNCATE TABLE detected. This is destructive and irreversible. Run manually if intended."
fi

# ──────────────────────────────────────────────
# Dangerous system commands
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qE 'chmod[[:space:]]+777'; then
  deny "Blocked: chmod 777 gives everyone read/write/execute. Use more restrictive permissions (e.g., 755 or 644)."
fi

if echo "$COMMAND" | grep -qE '(curl|wget)[[:space:]].*\|[[:space:]]*(bash|sh|zsh|sudo)'; then
  deny "Blocked: piping downloaded content directly to a shell is dangerous. Download first, inspect, then execute."
fi

if echo "$COMMAND" | grep -qE '(mkfs|dd[[:space:]]+if=|>[[:space:]]*/dev/)'; then
  deny "Blocked: destructive disk operation detected. This can cause irreversible data loss."
fi

# ──────────────────────────────────────────────
# Accidental package publishing
# ──────────────────────────────────────────────

if echo "$COMMAND" | grep -qE '(npm|yarn|pnpm|bun)[[:space:]]+publish'; then
  deny "Blocked: publishing npm packages should be done manually or via CI, not through Claude Code."
fi

if echo "$COMMAND" | grep -qE 'twine[[:space:]]+upload'; then
  deny "Blocked: publishing Python packages should be done manually or via CI, not through Claude Code."
fi

exit 0
