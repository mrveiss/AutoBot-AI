# GitHub Issue Enforcement — Two-Layer Design

**Date:** 2026-02-28
**Goal:** Ensure ALL work in Claude Code sessions is linked to a GitHub issue. No code gets written without an issue. No session ends with orphaned work.

---

## Problem

Claude Code sessions sometimes produce work (edits, commits) that isn't tied to a GitHub issue. When a session dies or context is exhausted, that work is effectively lost — no one knows it happened, what was done, or what remains. The CLAUDE.md Rule 1 ("ALL work must link to GitHub Issue") is aspirational but not mechanically enforced.

## Solution: Two-Layer Enforcement

### Layer 1: PreToolUse Prompt Hook (Prevention)

A prompt-based hook on `Edit|Write` that injects a reminder into Claude before any code edit. Claude must confirm an active GitHub issue number before proceeding. If no issue exists, Claude must create one first.

**Hook config** (in `.claude/settings.json`):

```json
{
  "matcher": "Edit|Write",
  "hooks": [{
    "type": "prompt",
    "prompt": "GITHUB ISSUE CHECK: Is this edit linked to a GitHub issue? If you have not yet confirmed an active issue for this session's work, you MUST: 1) Search for an existing issue with `gh issue list`, or 2) Create one with `gh issue create`. State the issue number (e.g. 'Working on #1234') before proceeding. Do NOT write code without a linked issue."
  }]
}
```

**Behavior:**
- Fires on every `Edit` and `Write` tool call
- Claude internalizes after first check — subsequent edits just state the issue number
- No shell execution, no blocking — relies on Claude's compliance
- Zero overhead for sessions that already start with an issue

### Layer 2: Stop Hook Shell Script (Safety Net)

A command-based `Stop` hook that runs a shell script. Detects orphaned work (commits without issue refs, uncommitted changes) and auto-creates a GitHub issue to capture it.

**Hook config** (in `.claude/settings.json`):

```json
{
  "matcher": "",
  "hooks": [{
    "type": "command",
    "command": "/home/kali/Desktop/AutoBot/scripts/hooks/session-stop-orphan-check.sh",
    "statusMessage": "Checking for orphaned work...",
    "timeout": 15
  }]
}
```

**Script logic** (`scripts/hooks/session-stop-orphan-check.sh`):

1. Get all commits from the current session (last 8 hours on current branch) that lack `#NNN` issue references
2. Filter out whitelisted prefixes: `docs:`, `chore:`, `style:`, `ci:` (these may legitimately skip issue refs)
3. Check `git status` for uncommitted/untracked changes in tracked directories
4. If orphaned work found:
   - Build a description from commit messages, changed files, branch name
   - Run `gh issue create` with title, body, and `orphaned-work` label
   - Output the new issue URL
5. If no orphaned work: output nothing (clean exit)

### Coverage Matrix

| Scenario                                  | Layer 1 (PreToolUse) | Layer 2 (Stop)       |
|-------------------------------------------|----------------------|----------------------|
| Claude starts editing without issue       | Catches — forces issue creation | N/A          |
| Claude commits without `#NNN`             | N/A                  | Detects, creates issue |
| Session dies with uncommitted changes     | N/A                  | Detects, creates issue |
| Quick fix on Dev_new_gui without branch   | Catches              | Catches commits      |
| docs/chore commits (no issue needed)      | N/A                  | Whitelisted, skipped |
| Pre-commit reformatting (Black/isort)     | Not triggered        | Not triggered        |

### Edge Cases

- **Whitelisted commit types:** `docs:`, `chore:`, `style:`, `ci:` prefixes are excluded from orphan detection to avoid spurious issues for non-functional changes.
- **Multiple issues per session:** Layer 1 just asks Claude to confirm — Claude naturally tracks which issue is active. Layer 2 checks all commits individually.
- **Session with no code changes:** Neither layer fires (no Edit/Write calls, no orphan commits). Clean exit.
- **Existing PreToolUse hooks:** The new prompt hook is additive — it doesn't conflict with the existing `Bash(git commit*)` command hook.

### File Locations

- Hook config: `.claude/settings.json` (project-level, travels with repo)
- Stop script: `scripts/hooks/session-stop-orphan-check.sh` (executable, committed to repo)

## Non-Goals

- This does NOT enforce branch naming conventions
- This does NOT prevent commits — it catches them after the fact
- This does NOT replace the CLAUDE.md Rule 1 — it mechanically enforces it
