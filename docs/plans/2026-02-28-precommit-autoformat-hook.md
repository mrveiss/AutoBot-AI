# Pre-commit Auto-formatter Claude Hook Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a PreToolUse hook to `.claude/settings.json` that auto-formats staged Python files with isort + black before any `git commit` runs, eliminating the "files were modified by hooks" failure cycle.

**Architecture:** Extend the existing `PreToolUse` Bash hook's `hooks` array with a second entry. The hook detects `git commit` in the command, collects staged `*.py` files, runs isort then black on them, re-stages, and exits 0. Pre-commit hooks then find nothing to change.

**Tech Stack:** `.claude/settings.json` hook system, isort 5.13.2, black 23.12.1 (via pre-commit managed binary), bash.

---

### Task 1: Add the auto-formatter hook to `.claude/settings.json`

**Files:**
- Modify: `.claude/settings.json` (the `hooks.PreToolUse[0].hooks` array — add a second entry)

**Step 1: Read the current file to confirm the exact insertion point**

Read `.claude/settings.json`. The `PreToolUse` section looks like:
```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "if [[ \"$TOOL_ARGS\" == *\"git commit\"* ]]; then ... fi",
        "statusMessage": "Verifying git state...",
        "timeout": 3
      }
      // <-- INSERT NEW HOOK OBJECT HERE
    ]
  }
]
```

**Step 2: Insert the new hook entry after the existing one**

Add this object after the existing hook entry (inside the same `hooks` array):

```json
{
  "type": "command",
  "command": "if [[ \"$TOOL_ARGS\" == *\"git commit\"* ]]; then cd $(git rev-parse --show-toplevel 2>/dev/null || pwd) && PY_FILES=$(git diff --staged --name-only -- '*.py' 2>/dev/null) && if [[ -n \"$PY_FILES\" ]]; then echo \"🎨 Auto-formatting staged Python files...\" && BLACK_BIN=/home/kali/.cache/pre-commit/repoefsi1klb/py_env-python3/bin/black && if [[ ! -x \"$BLACK_BIN\" ]]; then BLACK_BIN=black; fi && echo \"$PY_FILES\" | xargs isort --profile=black --line-length=88 --quiet && echo \"$PY_FILES\" | xargs $BLACK_BIN --line-length=88 --quiet && echo \"$PY_FILES\" | xargs git add && echo \"✅ Formatted and re-staged: $(echo \"$PY_FILES\" | wc -l | tr -d ' ') file(s)\"; fi; fi",
  "statusMessage": "Auto-formatting Python files...",
  "timeout": 30
}
```

**Step 3: Verify the JSON is valid after editing**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('JSON valid')"
```
Expected output: `JSON valid`

If invalid: fix the JSON (common issue — unbalanced quotes or missing commas between hook objects).

**Step 4: Smoke-test the hook manually**

Create a deliberately un-formatted Python file, stage it, then attempt a commit:

```bash
# Create a badly formatted file
cat > /tmp/test_format.py << 'EOF'
import os
import sys
x=1
y =  2
z= x+y
EOF
cp /tmp/test_format.py /tmp/test_autoformat_hook.py
git add /tmp/test_autoformat_hook.py 2>/dev/null || true

# Verify isort+black work on staged files
STAGED=$(git diff --staged --name-only -- '*.py' | head -5)
echo "Staged Python files: $STAGED"
```

Then make a real edit to an existing tracked Python file (e.g., add a blank line to any `.py` file), stage it, and observe the "Auto-formatting" message appear in the Claude Code status bar when you next ask Claude to commit.

**Step 5: Commit the settings change**

```bash
git add .claude/settings.json
git commit -m "chore(hooks): auto-format staged Python files before git commit"
```

Expected: pre-commit passes in one shot (no Python files staged in this commit, so black/isort are skipped by pre-commit too).

---

### Task 2: Verify end-to-end behaviour

**No files to create or modify — this is a manual verification task.**

**Step 1: Stage a Python file with formatting issues**

Pick any Python file Claude recently edited. Add deliberate formatting drift:

```bash
# Add a trailing space and bad import order to trigger black+isort
FILE=$(git ls-files '*.py' | head -1)
echo "" >> $FILE        # extra blank line — black will remove it
git add $FILE
```

**Step 2: Ask Claude to commit**

In a Claude Code session, say: `commit the staged changes`. Watch the status bar — you should see:
- "Verifying git state..." (existing hook)
- "Auto-formatting Python files..." (new hook)

Then the commit should complete without "files were modified by hooks".

**Step 3: Confirm pre-commit doesn't re-modify files**

If the pre-commit output shows `black....Passed` and `isort....Passed` (not `Failed` or `modified`), the hook is working correctly.

---

## Notes for the Implementer

- **Black binary path:** The pre-commit managed binary is at `/home/kali/.cache/pre-commit/repoefsi1klb/py_env-python3/bin/black`. The hook falls back to system `black` if that path doesn't exist. Do NOT hardcode a different path without confirming it exists.
- **isort must run before black.** isort can output code that black then re-formats. Running black last guarantees the result matches what pre-commit's black hook expects.
- **The hook exits 0 always.** It is a formatter, not a validator. Never add `set -e` or let failures propagate — a missing binary should warn, not block the commit.
- **JSON escaping:** Every `"` inside the command string must be `\"`. Every `$` that should be a literal shell variable (not JSON interpolation) must remain `$` — JSON doesn't interpolate variables, so this is fine as-is.
- **Worktree note:** Hooks in `.claude/settings.json` apply to the project root only, not worktrees using a different `.claude/` directory.
