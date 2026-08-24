---
name: pr
description: Create a pull request with pre-flight branch checks, targeting Dev_new_gui by default
---

# /pr - Create Pull Request

Target: `Dev_new_gui` (never `main`). PR_LIMIT=10.

## Step 0 — PR Queue Gate (MANDATORY)

```bash
OPEN_COUNT=$(gh pr list --repo mrveiss/AutoBot-AI --state open --json number | jq length)
```

- If `$OPEN_COUNT < PR_LIMIT`: skip to Step 1.
- If at limit: audit CI state, merge GREEN PRs, fix straightforward FAILING PRs, re-check.

```bash
# Audit CI state
gh pr list --repo mrveiss/AutoBot-AI --state open --json number,title,statusCheckRollup \
  | jq '.[] | {number, title, ci: ([.statusCheckRollup[]?.state] | if all(. == "SUCCESS" or . == "NEUTRAL" or . == "SKIPPED") then "GREEN" elif any(. == "FAILURE" or . == "ERROR") then "FAILING" else "PENDING" end)}'
# Merge green PRs
gh pr merge <number> --squash --delete-branch
```

- All open PRs have unfixable failures → post Paperclip comment listing blockers, set issue `blocked`, stop.

## Step 1 — Pre-Flight Checks

```bash
git branch --show-current          # must NOT be Dev_new_gui or main
git status && git diff             # must be clean; if not, run /commit first
git log --oneline origin/Dev_new_gui..HEAD
```

## Step 1.5 — Pre-Push Quality Check (MANDATORY)

```bash
# Catch violations before they fail CI
grep -rn 'print(' autobot-backend/ autobot_shared/ --include='*.py' | grep -v '#' | grep -v 'test_'
grep -rn 'console\.\(log\|error\|warn\)' autobot-frontend/src/ --include='*.ts' --include='*.vue'
# Auto-format Python
black autobot-backend/ autobot_shared/ autobot-slm-backend/ 2>/dev/null || true
isort autobot-backend/ autobot_shared/ autobot-slm-backend/ 2>/dev/null || true
ruff check --fix autobot-backend/ autobot_shared/ 2>/dev/null || true
# Commit formatting changes if any
git add -u && git diff --cached --quiet || git commit -m "style: auto-format code (black/isort/ruff)"
```

- `print()` → `logging.getLogger(__name__)`; `console.*` → `createLogger()` from `@/utils/debugUtils`
- Fix all violations before proceeding.

## Step 2 — Push Branch

```bash
git push -u origin <current-branch>
# Rejected? git pull --rebase origin Dev_new_gui && git push
```

## Step 3 — Create PR

PR body must include these four headings: **Thinking Path · What Changed · Verification · Model Used**

```bash
gh pr create --base Dev_new_gui \
  --title "<type>(scope): <description> (#issue-number)" \
  --body "$(cat <<'EOF'
## Thinking Path
- <key decision>
## What Changed
- <change>
## Verification
- [ ] <test step>
## Model Used
Claude Sonnet 4.6

Closes #<issue-number>
EOF
)"
```

## Step 4 — Wait for CI (MANDATORY — do not exit until green)

```bash
PR=$(gh pr view --json number -q .number)
until [ "$(gh pr checks $PR --json state | jq '[.[]|select(.state=="PENDING" or .state=="QUEUED")]|length')" -eq 0 ]; do
  echo "Waiting..."; sleep 30; done
gh pr checks $PR
```

- CI failing: push a fix commit; loop re-runs automatically.

## Step 5 — Close Issue After Merge

`Closes #NNN` does NOT auto-close when targeting `Dev_new_gui`. Close manually after merge:

```bash
gh pr merge <pr-number> --squash --delete-branch
gh issue close <number> --comment "Closed via PR #<pr-number> merged into Dev_new_gui."
```

## Step 6: Worktree Cleanup (After Merge)

After the PR merges, immediately clean up both local worktree and branch:

```bash
git worktree remove .worktrees/<name>
git branch -d <branch-name>
# remote branch deleted automatically by --delete-branch; if not:
git push origin --delete <branch-name>
```

Do not leave merged worktrees on disk. Stale worktrees waste disk and confuse `git worktree list`.

## Red Flags (STOP)

- Branch is `Dev_new_gui` or `main`
- Uncommitted changes present
- No issue reference in title or body
- Skipped pre-push quality checks (Step 1.5)
- Exiting before CI is green
