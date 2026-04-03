---
name: commit
description: Standardized commit workflow with pre-flight checks, auto-format, and retry logic for pre-commit hooks
---

# Commit Workflow

Self-healing commit sequence that formats, stages, commits, and verifies — retrying up to 3x on hook failures.

## Step 1 — Pre-flight state check

```bash
git branch --show-current        # Must NOT be main/Dev_new_gui directly
git status                       # Identify all modified/untracked files
git diff --staged --name-only    # What's already staged?
git stash list                   # Warn if stashes exist
```

If on `main` or `Dev_new_gui` directly: **STOP** and ask user.

## Step 2 — Auto-format Python files

For every `.py` file that will be committed:

```bash
BLACK=$HOME/.cache/pre-commit/repoefsi1klb/py_env-python3/bin/black

for FILE in $(git diff --staged --name-only | grep '\.py$'); do
    $BLACK --line-length=88 "$FILE"
    isort --profile=black --line-length=88 "$FILE"
    git add "$FILE"    # Re-stage after formatting
done
```

Skip if no `.py` files are being committed.

## Step 3 — Stage files

Stage only files relevant to the current issue. **Never** `git add .` blindly.

```bash
git add <file1> <file2> ...   # Preferred: explicit files
# OR
git add -u                     # All tracked modifications (safe if worktree is clean)

# Verify:
git diff --staged --name-only
git diff --staged --stat
```

If unrecognized files appear staged: `git restore --staged <file>`

## Step 4 — Commit with retry loop

Attempt up to **3 times**, fixing hook failures between attempts:

```bash
for ATTEMPT in 1 2 3; do
    echo "Commit attempt $ATTEMPT/3..."

    git commit -m "$(cat <<'MSG'
<type>(scope): <description> (#issue-number)
MSG
)" && echo "✅ Committed on attempt $ATTEMPT" && break

    # Hook failed — re-stage any files hooks modified
    echo "⚠️  Hook failed. Re-staging modified files..."
    git add -u
done
```

**NEVER use `--no-verify`.** Fix the underlying issue.

## Step 5 — Post-commit verification

```bash
git log -1 --stat        # Verify commit landed
git diff                 # Nothing left uncommitted
git diff --staged        # Nothing accidentally staged
```

## Step 6 — Report

State commit hash, files changed, branch, and whether more commits are needed.

## Commit Message Format

```
<type>(scope): <description> (#issue-number)
```

Types: `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `perf`

## Common Hook Failures & Fixes

| Hook | Symptom | Fix |
|------|---------|-----|
| black | "reformatted X.py" | `git add -u` and retry |
| isort | "Imports are incorrectly sorted" | `isort --profile=black <file> && git add <file>` |
| flake8 | "E501 line too long" | Shorten the line, `git add <file>` |
| autoflake | removed unused import | Accept it, `git add -u` |
| warn-untracked-files | untracked source files detected | Run `git diff --cached --name-only`, verify staged files belong on this branch |
