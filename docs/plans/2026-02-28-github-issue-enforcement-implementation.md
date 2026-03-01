# GitHub Issue Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mechanically enforce that all Claude Code work is linked to a GitHub issue — prevent untracked work via prompt hook, catch orphans at session end via shell script.

**Architecture:** Two hooks in `.claude/settings.json`: a PreToolUse prompt hook on Edit|Write that forces Claude to confirm an issue number, and a Stop command hook that runs a shell script detecting orphaned commits/changes and auto-creating GitHub issues.

**Tech Stack:** Claude Code hooks (prompt + command types), bash, gh CLI

---

### Task 1: Create the Stop hook shell script

**Files:**
- Create: `scripts/hooks/session-stop-orphan-check.sh`

**Step 1: Write the script**

```bash
#!/bin/bash
# Session Stop Orphan Check
# Detects work not linked to a GitHub issue and auto-creates one.
# Called by Claude Code Stop hook.

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# Whitelisted commit prefixes that don't need issue refs
WHITELIST="^(docs|chore|style|ci|merge|Merge)"

# 1. Find commits from last 8 hours without #NNN issue references
ORPHAN_COMMITS=$(git log --oneline --since="8 hours ago" --author="$(git config user.name 2>/dev/null || echo '.')" 2>/dev/null \
  | grep -vE '#[0-9]{3,}' \
  | grep -vE "$WHITELIST" \
  || true)

# 2. Check for uncommitted changes (staged + unstaged + untracked in src dirs)
UNCOMMITTED=$(git status --porcelain 2>/dev/null \
  | grep -E '^\s*(M|A|D|R|\?\?)' \
  | grep -vE '(node_modules|__pycache__|\.pyc|dist/|\.claude/)' \
  | head -20 \
  || true)

# 3. If nothing found, clean exit
if [ -z "$ORPHAN_COMMITS" ] && [ -z "$UNCOMMITTED" ]; then
  exit 0
fi

# 4. Build issue body
BODY="## Orphaned Work Detected

This issue was auto-created by the session-stop orphan check because work was found that is not linked to any GitHub issue.

**Branch:** \`$BRANCH\`
**Detected at:** $(date -Iseconds)
"

if [ -n "$ORPHAN_COMMITS" ]; then
  BODY+="
### Commits without issue references

\`\`\`
$ORPHAN_COMMITS
\`\`\`
"
fi

if [ -n "$UNCOMMITTED" ]; then
  BODY+="
### Uncommitted changes

\`\`\`
$UNCOMMITTED
\`\`\`
"
fi

BODY+="
### Action Required

Review this work and either:
1. Link it to an existing issue by amending commit messages
2. Continue the work in a new session referencing this issue
3. Close if the work was intentional and already tracked elsewhere
"

# 5. Create the issue
TITLE="Orphaned work on $BRANCH: $(echo "$ORPHAN_COMMITS $UNCOMMITTED" | head -1 | cut -c1-60)"

ISSUE_URL=$(gh issue create \
  --title "$TITLE" \
  --body "$BODY" \
  --label "orphaned-work" \
  2>&1) || {
  # If label doesn't exist or gh fails, try without label
  ISSUE_URL=$(gh issue create \
    --title "$TITLE" \
    --body "$BODY" \
    2>&1) || {
    echo "WARNING: Could not create GitHub issue for orphaned work"
    echo "Orphan commits: $ORPHAN_COMMITS"
    echo "Uncommitted: $UNCOMMITTED"
    exit 0
  }
}

echo "ORPHANED WORK DETECTED - Created issue: $ISSUE_URL"
echo "Review and link this work before starting a new session."
```

**Step 2: Make it executable**

Run: `chmod +x scripts/hooks/session-stop-orphan-check.sh`

**Step 3: Test the script manually**

Run: `bash scripts/hooks/session-stop-orphan-check.sh`
Expected: Either clean exit (if all recent commits have issue refs) or creates an issue (if orphaned work exists). Since we have uncommitted changes from #1246, it should detect those.

**Step 4: Commit**

```bash
git add scripts/hooks/session-stop-orphan-check.sh
git commit -m "feat(hooks): add session-stop orphan work detection script"
```

---

### Task 2: Add both hooks to project settings.json

**Files:**
- Modify: `.claude/settings.json`

**Step 1: Add the PreToolUse prompt hook for Edit|Write**

Add to the existing `PreToolUse` array in `.claude/settings.json`:

```json
{
  "matcher": "Edit|Write",
  "hooks": [
    {
      "type": "prompt",
      "prompt": "GITHUB ISSUE CHECK: Is this edit linked to a GitHub issue? If you have not yet confirmed an active issue for this session's work, you MUST: 1) Search for an existing issue with `gh issue list`, or 2) Create one with `gh issue create` — include a clear title and description of the work. State the issue number (e.g. 'Working on #1234') before proceeding. Do NOT write code without a linked issue."
    }
  ]
}
```

**Step 2: Add the Stop hook**

Add a new `Stop` key to the `hooks` object:

```json
"Stop": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "/home/kali/Desktop/AutoBot/scripts/hooks/session-stop-orphan-check.sh",
        "statusMessage": "Checking for orphaned work...",
        "timeout": 15
      }
    ]
  }
]
```

**Step 3: Verify settings.json is valid JSON**

Run: `python3 -c "import json; json.load(open('.claude/settings.json')); print('Valid JSON')"`
Expected: `Valid JSON`

**Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(hooks): add GitHub issue enforcement hooks (PreToolUse prompt + Stop orphan check)"
```

---

### Task 3: Create the orphaned-work label in GitHub

**Step 1: Create the label**

Run: `gh label create "orphaned-work" --description "Auto-created for work not linked to an issue" --color "D93F0B"`

**Step 2: Verify**

Run: `gh label list | grep orphaned`
Expected: `orphaned-work` label exists

---

### Task 4: End-to-end verification

**Step 1: Verify the PreToolUse hook fires**

Start a new Claude session, attempt an Edit without mentioning an issue number. The prompt hook should inject the issue check reminder.

**Step 2: Verify the Stop hook fires**

In a test session, make a small commit without `#NNN` in the message. Exit the session. The Stop hook should detect the orphan and create an issue.

**Step 3: Verify clean sessions pass silently**

In a session where all work references an issue, the Stop hook should produce no output.
