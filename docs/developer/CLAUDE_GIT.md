# Git, Branching & Worktree Rules

## Parallel Work: Worktree Isolation (CRITICAL)

**NO `git checkout` or `git switch` on shared branches during parallel work sessions.**

- **Each parallel task MUST have its own worktree:** `.worktrees/issue-XXXX/` with dedicated branch `issue-XXXX`
- **Main session stays on `Dev_new_gui`** — never check out feature branches
- **Why:** Switching branches in main session breaks all active worktrees that depend on that branch

**Worktree Creation:**
```bash
git worktree add .worktrees/issue-XXXX -b issue-XXXX origin/Dev_new_gui
cd .worktrees/issue-XXXX && git branch --unset-upstream
# Commit and push from here. Do NOT switch branches.
```

---

## Pre-Flight Checklist (Before Parallel Work)

1. `git branch --show-current` — must be `Dev_new_gui`. If on a feature branch, STOP.
2. Confirm Bash is approved in main session — sub-agents inherit from parent.
3. `git status --porcelain` — if any files are dirty, commit or stash before spawning agents. Uncommitted edits are silently discarded when a subagent commits and upstream is merged (#4969).
4. Verify issue isn't already resolved: `git log origin/Dev_new_gui --oneline --grep="#XXXX"`
5. For architectural decisions, state in 1–2 sentences and wait for confirmation.

---

## Branch Safety (MANDATORY)

**Never run without explicit user confirmation:**
- `git reset --hard` — discards uncommitted work permanently
- `git push --force` / `git push -f` — rewrites remote history
- `git branch -D` — permanent unless reflog exists
- `git clean -fd` — unrecoverable
- Any operation touching `main` or `master` directly

**Before any bulk git operation:**
1. `git status` + `git diff --stat` — confirm exactly what will be affected
2. State operation and scope in one sentence before executing
3. For branch deletions: verify merged via `git branch -r --merged origin/Dev_new_gui`

**Why:** Past incidents: staged 5,371 files for deletion in a worktree, nearly reset `main` during a cherry-pick with 30+ conflicts, committed fixes to wrong branches.

---

## Branching Discipline (Issue #4113)

**Protected (blocked by pre-commit hook):** `main`, `master`

**Allowed:** `Dev_new_gui`, `issue-*`, `hotfix-*`, worktree branches matching those patterns

**Workflow:**
1. `git checkout -b issue-XXXX origin/Dev_new_gui`
2. Commit on feature branch
3. `git push -u origin issue-XXXX`
4. Open PR: `issue-XXXX` → `Dev_new_gui` (NOT directly to main)

**If you see "COMMIT BLOCKED":**
```bash
git checkout issue-XXXX  # or: git checkout -b issue-XXXX origin/Dev_new_gui
git add -A && git commit -m "..."
```

---

## Hook Scripts

Before committing any change to `.claude/hooks/block-dangerous-commands.sh`, run:
```bash
bash .claude/hooks/block-dangerous-commands_test.sh
```
Must be 27/27. Add test cases for new rules. Use `bash` (GNU grep 3.7), not interactively — the shell `grep` alias is `ugrep` (PCRE2) which has different variable-length lookbehind support. See #8262.

---

## Git Push Recovery

Before pushing, check for diverged remote:
```bash
git status && git log --oneline origin/<branch>..HEAD
```

If push rejected: fetch, rebase (`git rebase origin/<branch>`), resolve conflicts, then push. If rebase fails with conflicts you cannot resolve cleanly, stop and report — do NOT force-push and lose upstream changes.
