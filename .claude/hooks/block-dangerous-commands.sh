#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Blocks dangerous shell commands before execution.
# PreToolUse hook for Bash operations.
# Exit 2 = block the action. Exit 0 = allow.
#
# AutoBot - AI-Powered Automation Platform
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
# Worktree isolation — branch-switch guards (#4113, #6512, #10126, #15296)
#
# Parallel Claude sessions share one main working tree. A session that moves
# HEAD there tramples every other session, so the thing these guards exist to
# stop is a branch switch on the MAIN WORKING TREE OF THIS REPOSITORY — and
# nothing wider than that.
#
# They used to be wider, in the direction that costs the most (#15296). A regex
# over the whole command string turned a redirection into the branch argument
# (`git switch -` was allowed, the same command with `2>&1 | tail -2` appended
# was denied), ignored `-C`'s value so an unrelated checkout was covered too,
# and matched the words inside quoted prose so a PR body that merely described
# a switch was denied. A guard that denies correct work teaches people to route
# around it, which is how a control stops being one. So all three fixes narrow
# WHEN the guard fires; none of them widens WHAT it permits on the main tree of
# this repository, which is still judged by exactly the rules below.
#
# The following git forms are SAFE and explicitly allowed even on the main tree:
#   - new-branch creation (-b/-B/-c/--create/--orphan): forks a fresh branch,
#     does not move HEAD onto a shared one
#   - file restore: `git checkout -- <path>`, `git checkout .`
#   - detached / toggle switches: `git switch -`, `git switch --detach`
#   - SHA / tag / Dev_new_gui checkouts
# ──────────────────────────────────────────────

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_INVOCATION_PARSER="$HOOK_DIR/git_invocation_parse.py"

# Ask git about a path with the inherited git environment scrubbed: a stray
# GIT_DIR or GIT_WORK_TREE would make rev-parse answer about a different
# repository than the command targets, and mis-identifying the repository is
# the one error this guard cannot afford. Same scrub as
# scripts/install-git-hooks.sh.
git_query() {
  local dir="$1" gitdir="$2"
  shift 2
  local -a opts=()
  [ -n "$dir" ] && opts+=(-C "$dir")
  [ -n "$gitdir" ] && opts+=(--git-dir "$gitdir")
  (
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    git "${opts[@]}" rev-parse "$@" 2>/dev/null
  )
}

# The repository this guard speaks for is the one the hook file itself lives in.
# Empty when the hook is not inside a checkout at all, in which case every main
# tree is treated as in scope — the conservative direction.
# `--path-format=absolute` does not resolve symlinks, so two paths that reach
# the same directory by different routes compare unequal. Every comparison below
# goes through the physical path instead; a mismatch there would silently put
# this repository out of the guard's own scope.
canon_dir() { (cd "$1" 2>/dev/null && pwd -P); }

GUARD_COMMON_DIR=$(canon_dir "$(git_query "$HOOK_DIR" "" --path-format=absolute --git-common-dir)")

# True when the invocation acts on the main working tree of THIS repository.
# A linked worktree is somebody's own tree and a different repository is none of
# this guard's business; the comment above has always said so, and now the code
# does too (#15296).
targets_this_main_tree() {
  local dir="$1" gitdir="$2" common worktree
  # A directory only the shell could have resolved (`cd $VAR`, `cd -`): the
  # parser reports `?` rather than guessing, and unknown is treated as ours.
  [ "$dir" = "?" ] && return 0
  common=$(canon_dir "$(git_query "$dir" "$gitdir" --path-format=absolute --git-common-dir)")
  [ -n "$common" ] || return 1              # not inside a git repository at all
  worktree=$(canon_dir "$(git_query "$dir" "$gitdir" --path-format=absolute --git-dir)")
  [ "$common" = "$worktree" ] || return 1   # a linked worktree, not the main tree
  [ -z "$GUARD_COMMON_DIR" ] || [ "$common" = "$GUARD_COMMON_DIR" ]
}

# Cheap pre-filter so the parser only runs for commands that could contain one.
if printf '%s' "$COMMAND" | grep -qF -e checkout -e switch; then
  if ! command -v python3 >/dev/null 2>&1; then
    deny "Blocked: the branch-switch guard needs python3 to tell a real invocation from the same words quoted inside an argument (#15296), and python3 is not installed. Install python3 rather than removing the guard."
  fi

  BRANCH_INVOCATIONS=$(python3 "$GIT_INVOCATION_PARSER" "$COMMAND")
  PARSE_STATUS=$?

  # Refusing to judge, out loud, beats judging a command that was mis-parsed.
  if [ "$PARSE_STATUS" -eq 3 ]; then
    deny "Blocked: the branch-switch guard could not tokenize this command — an unbalanced quote or an unterminated heredoc (#15296). It will not guess at where one command's arguments end, so it makes no ruling. Rewrite the command with balanced quotes and run it again."
  fi
  if [ "$PARSE_STATUS" -ne 0 ]; then
    deny "Blocked: the branch-switch guard's parser exited $PARSE_STATUS, so nothing was checked (#15296). Restore .claude/hooks/git_invocation_parse.py instead of working around the guard."
  fi

  # 0x1f, not tab: tab is IFS whitespace, so `read` collapses a run of them
  # and every leading empty field vanishes -- the branch name would land in
  # WT_DIR and the guard would go looking for a directory by that name (#15296).
  while IFS=$'\x1f' read -r WT_DIR WT_GIT_DIR SWITCH_FLAGS BRANCH_ARG; do
    [ -n "$WT_DIR$WT_GIT_DIR$SWITCH_FLAGS$BRANCH_ARG" ] || continue
    targets_this_main_tree "$WT_DIR" "$WT_GIT_DIR" || continue

    # Forking a new branch, or restoring files, never moves HEAD onto a shared
    # branch. Allowed on the main tree, exactly as before.
    case ",$SWITCH_FLAGS," in *,new,* | *,restore,*) continue ;; esac

    if [ "$BRANCH_ARG" = "main" ] || [ "$BRANCH_ARG" = "master" ]; then
      deny "Blocked: never check out main/master locally (#4113, #6512). Main is read-only; commits flow Dev_new_gui → main via release cycle. If you need to inspect main, use git log origin/main or create a worktree: git worktree add .worktrees/inspect-main main"
    fi

    # Deny only when a concrete branch-name arg is present and is not one of the
    # safe targets (base branch, file restore, detached HEAD, SHA, tag, path).
    if [ -n "$BRANCH_ARG" ] &&
      [ "$BRANCH_ARG" != "Dev_new_gui" ] &&
      [ "$BRANCH_ARG" != "." ] &&
      [ "$BRANCH_ARG" != "HEAD" ] &&
      ! [[ "$BRANCH_ARG" =~ ^[0-9a-f]{7,40}$ ]] &&
      ! [[ "$BRANCH_ARG" =~ ^v[0-9]+\.[0-9]+ ]] &&
      ! [[ "$BRANCH_ARG" =~ ^/ ]]; then
      deny "Blocked: switching branches on the main working tree tramples HEAD for parallel sessions (#6512). Use a worktree instead: git worktree add .worktrees/<name> <branch> && cd .worktrees/<name>. Then do your work and remove with: git worktree remove .worktrees/<name>"
    fi
  done <<<"$BRANCH_INVOCATIONS"
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

# Redirect guard targets raw block devices only — matching all of /dev/ would
# false-positive on the ubiquitous stderr/stdout null-discard idiom (#11593).
if echo "$COMMAND_TO_CHECK" | grep -qE '(mkfs|dd[[:space:]]+if=|>[[:space:]]*/dev/(sd|hd|nvme|vd|xvd|mmcblk|loop|dm-|md))'; then
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
