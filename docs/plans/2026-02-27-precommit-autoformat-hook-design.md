# Design: Pre-commit Auto-formatter Claude Code Hook

**Date:** 2026-02-27
**Status:** Approved

## Problem

The pre-commit suite runs `black --line-length=88` and `isort --profile=black --line-length=88`
on staged Python files. When Claude writes/edits Python without pre-formatting, these hooks
modify files and abort the commit with "files were modified by hooks". Claude then has to
re-stage and retry — a repeated friction cycle seen across many sessions.

## Solution

Extend the existing `PreToolUse` Bash hook in `.claude/settings.json` to auto-format staged
Python files with black + isort **before** `git commit` runs. By the time pre-commit hooks
execute, the files are already correctly formatted — hooks find nothing to change.

## Design

### Hook placement

`.claude/settings.json` → `hooks.PreToolUse` → existing Bash matcher's `hooks` array.
A second entry is added alongside the existing "show staged files + branch" hook.

### Trigger

Any Bash command containing `git commit` (same detector already used by the existing hook).

### Execution order

1. Find staged Python files: `git diff --staged --name-only -- '*.py'`
2. If none → exit 0 silently (no-op for non-Python commits)
3. Run `isort --profile=black --line-length=88` on each file
4. Run `black --line-length=88` on each file (black is the canonical final formatter)
5. Re-stage all files: `git add <files>`
6. Print a one-line summary

### Black binary

Use the pre-commit managed binary first:
`/home/kali/.cache/pre-commit/repoefsi1klb/py_env-python3/bin/black`

Fall back to system `black` if the path doesn't exist. This ensures the same version and
configuration as the actual pre-commit hook.

### Error handling

- Hook exits 0 always — it is a formatter, not a gatekeeper
- If black/isort are not found, print a warning and continue (don't block the commit attempt)
- `timeout: 30` to handle large batches of files

## What stays the same

The existing `git commit` PreToolUse hook (which shows staged file list and current branch)
continues to run unchanged alongside this new hook.

## Success criteria

Pre-commit hooks no longer fail with "files were modified by hooks" on Python files that
Claude has edited. Commits complete in one attempt without manual re-staging.
