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

# Strip commit message content before pattern checking (#3041).
# Without this, git commit -m "docs: describe how we block resets"
# would be falsely blocked because the message contains "reset".
COMMAND_TO_CHECK="$COMMAND"
if [[ "$COMMAND" =~ git[[:space:]]+commit ]]; then
  # Remove -m "..." / -m '...' / -m $'...' message arguments
  COMMAND_TO_CHECK=$(echo "$COMMAND" | sed -E "s/-m[[:space:]]+['\"][^'\"]*['\"]//g" | sed -E "s/-m[[:space:]]+[^[:space:]]+//g")
  # Remove HEREDOC-style messages: -m "$(cat <<'EOF' ... EOF )"
  COMMAND_TO_CHECK=$(echo "$COMMAND_TO_CHECK" | sed -E 's/\$\(cat <<[^)]*\)//g')
fi

deny() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 2
}

# ──────────────────────────────────────────────
# Git push protections
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE '(^|[;&|()]+[[:space:]]*)git[[:space:]]+push'; then

  # Block push to main, master, or Dev_new_gui directly
  if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+push.*(origin[[:space:]]+|:)(main|master|Dev_new_gui)\b'; then
    deny "Blocked: cannot push directly to main/master/Dev_new_gui. Use a feature branch and create a PR."
  fi

  # Block bare git push when on protected branches
  if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+push[[:space:]]*($|[;&|])'; then
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
    if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ] || [ "$CURRENT_BRANCH" = "Dev_new_gui" ]; then
      deny "Blocked: you are on $CURRENT_BRANCH. Use a feature branch and create a PR."
    fi
  fi

  # Block force push (allow --force-with-lease)
  if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+push.*(-[a-zA-Z]*f|--force)([[:space:]]|$)' && ! echo "$COMMAND_TO_CHECK" | grep -q '\-\-force-with-lease'; then
    deny "Blocked: force push is not allowed. Use --force-with-lease if you need to overwrite remote."
  fi
fi

# ──────────────────────────────────────────────
# Git commit protections
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+commit.*--no-verify'; then
  deny "Blocked: --no-verify bypasses pre-commit hooks. Fix the underlying hook failure instead."
fi

# ──────────────────────────────────────────────
# Destructive git operations
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+reset[[:space:]]+--hard'; then
  deny "Blocked: git reset --hard discards uncommitted changes permanently. Use git stash or git reset --soft instead."
fi

if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+clean[[:space:]]+-[a-zA-Z]*f'; then
  deny "Blocked: git clean -f permanently deletes untracked files. Review with git clean -n first, then run manually if intended."
fi

# ──────────────────────────────────────────────
# Worktree isolation — block checkouts to protected branches (#6512)
# Parallel Claude sessions that run `git checkout main` or `git switch main`
# trample HEAD on other sessions sharing the same working tree. CLAUDE.md
# states main is read-only and the main session must stay on Dev_new_gui;
# checking out main locally has no legitimate use case here.
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE '(^|[;&|()]+[[:space:]]*)git[[:space:]]+(checkout|switch)[[:space:]]+(main|master)([[:space:]]|$)'; then
  deny "Blocked: never check out main/master locally (#4113, #6512). Main is read-only; commits flow Dev_new_gui → main via release cycle. If you need to inspect main, use git log origin/main or create a worktree: git worktree add .worktrees/inspect-main main"
fi

# Block ALL branch checkouts and branch creation from the main working tree (#6512)
# Subagents running in parallel would trample the shared HEAD for every other session.
# Any branch work must happen inside an isolated worktree.
# BUG FIX: previously -b/-B/-c flags bypassed the pattern because [^-] required a
# non-dash first char after checkout/switch. Now both cases are caught explicitly.
if echo "$COMMAND_TO_CHECK" | grep -qE '(^|[;&|()]+[[:space:]]*)git[[:space:]]+(checkout|switch)[[:space:]]'; then
  CURRENT_DIR=$(pwd)
  if [[ ! "$CURRENT_DIR" =~ \.worktrees/ ]]; then
    # Detect -b/-B/-c/--create/--orphan flags — new-branch creation always denied on main tree
    # because it still moves HEAD away from Dev_new_gui.
    HAS_NEW_BRANCH_FLAG=0
    if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+(checkout|switch)[[:space:]]+(-b|-B|-c|--create|--orphan)([[:space:]]|$)' || \
       echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+(checkout|switch)[[:space:]]+.*[[:space:]](-b|-B|-c|--create|--orphan)([[:space:]]|$)'; then
      HAS_NEW_BRANCH_FLAG=1
    fi

    BRANCH_ARG=$(echo "$COMMAND_TO_CHECK" | awk '{
      found=0
      for(i=1;i<=NF;i++) {
        if ($i=="checkout" || $i=="switch") { found=i; break }
      }
      if (found) {
        for(j=found+1;j<=NF;j++) {
          if (substr($j,1,1)!="-") { print $j; break }
        }
      }
    }')

    if [[ "$HAS_NEW_BRANCH_FLAG" -eq 1 ]]; then
      deny "Blocked: creating a branch on the main working tree moves HEAD away from Dev_new_gui and tramples parallel sessions (#6512). Use a worktree instead: git worktree add .worktrees/<name> -b <branch> Dev_new_gui && cd .worktrees/<name>"
    elif [[ "$BRANCH_ARG" != "Dev_new_gui" ]] && \
         [[ "$BRANCH_ARG" != "." ]] && \
         ! [[ "$BRANCH_ARG" =~ ^[0-9a-f]{7,40}$ ]] && \
         ! [[ "$BRANCH_ARG" =~ ^v[0-9]+\.[0-9]+ ]] && \
         ! [[ "$BRANCH_ARG" =~ ^/ ]]; then
      deny "Blocked: switching branches on the main working tree tramples HEAD for parallel sessions (#6512). Use a worktree instead: git worktree add .worktrees/<name> <branch> && cd .worktrees/<name>. Then do your work and remove with: git worktree remove .worktrees/<name>"
    fi
  fi
fi

# Warn if committing outside a worktree when issue-specific worktree exists (#6512)
if echo "$COMMAND_TO_CHECK" | grep -qE '(^|[;&|()]+[[:space:]]*)git[[:space:]]+commit'; then
  CURRENT_DIR=$(pwd)
  IN_WORKTREE=0

  # Check if we're inside .worktrees/
  if [[ "$CURRENT_DIR" =~ \.worktrees/issue- ]]; then
    IN_WORKTREE=1
  fi

  # If NOT in a worktree, warn about parallel work isolation
  if [ "$IN_WORKTREE" -eq 0 ]; then
    # Check if any issue-specific worktrees exist
    REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ -d "$REPO_ROOT/.worktrees" ] && ls "$REPO_ROOT/.worktrees"/issue-* >/dev/null 2>&1; then
      # Worktrees exist—you should be using one
      AVAILABLE=$(ls -d "$REPO_ROOT/.worktrees"/issue-* 2>/dev/null | xargs basename -a | paste -sd "," -)
      echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"warn\",\"permissionDecisionReason\":\"Git commit outside worktree detected (#6512). Parallel work worktrees exist: $AVAILABLE. Consider: cd $REPO_ROOT/.worktrees/issue-XXXX && git commit (...) to avoid shared tree conflicts.\"}}" >&2
    fi
  fi
fi

# Block bare `git reset <ref>` on Dev_new_gui — parallel sessions doing
# `git reset origin/Dev_new_gui` from a feature branch silently move HEAD
# and lose committed work that wasn't pushed yet (#6512).
if echo "$COMMAND_TO_CHECK" | grep -qE 'git[[:space:]]+reset[[:space:]]+(--mixed[[:space:]]+|--soft[[:space:]]+)?(origin/)?(main|master|Dev_new_gui)([[:space:]]|$)'; then
  deny "Blocked: git reset onto a protected ref moves HEAD and can lose unpushed commits in parallel sessions (#6512). Use 'git fetch && git merge --ff-only' or create a fresh branch with 'git checkout -b NEW origin/Dev_new_gui'."
fi

# ──────────────────────────────────────────────
# Destructive filesystem operations
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*r[a-zA-Z]*f[[:space:]]+(\/|~|\$HOME|\.\.\/\.\.)'; then
  deny "Blocked: recursive force-delete on root/home/parent paths. Specify a safe target directory."
fi

if echo "$COMMAND_TO_CHECK" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*r.*[[:space:]]+(\/[[:space:]]|\/\*|\/$|~\/?\*?[[:space:]]|~\/?\*?$)'; then
  deny "Blocked: recursive delete targeting root or home directory."
fi

# ──────────────────────────────────────────────
# Dangerous database operations
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qiE 'DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)[[:space:]]'; then
  deny "Blocked: DROP TABLE/DATABASE/SCHEMA detected. This is destructive and irreversible. Run manually if intended."
fi

if echo "$COMMAND_TO_CHECK" | grep -qiE 'DELETE[[:space:]]+FROM[[:space:]]+[a-zA-Z_]+[[:space:]]*($|;)' && ! echo "$COMMAND_TO_CHECK" | grep -qiE 'WHERE'; then
  deny "Blocked: DELETE FROM without WHERE clause would delete all rows. Add a WHERE clause."
fi

if echo "$COMMAND_TO_CHECK" | grep -qiE 'TRUNCATE[[:space:]]+TABLE'; then
  deny "Blocked: TRUNCATE TABLE detected. This is destructive and irreversible. Run manually if intended."
fi

# ──────────────────────────────────────────────
# Dangerous system commands
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE 'chmod[[:space:]]+777'; then
  deny "Blocked: chmod 777 gives everyone read/write/execute. Use more restrictive permissions (e.g., 755 or 644)."
fi

if echo "$COMMAND_TO_CHECK" | grep -qE '(curl|wget)[[:space:]].*\|[[:space:]]*(bash|sh|zsh|sudo)'; then
  deny "Blocked: piping downloaded content directly to a shell is dangerous. Download first, inspect, then execute."
fi

if echo "$COMMAND_TO_CHECK" | grep -qE '(mkfs|dd[[:space:]]+if=|>[[:space:]]*/dev/)'; then
  deny "Blocked: destructive disk operation detected. This can cause irreversible data loss."
fi

# ──────────────────────────────────────────────
# Accidental package publishing
# ──────────────────────────────────────────────

if echo "$COMMAND_TO_CHECK" | grep -qE '(npm|yarn|pnpm|bun)[[:space:]]+publish'; then
  deny "Blocked: publishing npm packages should be done manually or via CI, not through Claude Code."
fi

if echo "$COMMAND_TO_CHECK" | grep -qE 'twine[[:space:]]+upload'; then
  deny "Blocked: publishing Python packages should be done manually or via CI, not through Claude Code."
fi

exit 0
