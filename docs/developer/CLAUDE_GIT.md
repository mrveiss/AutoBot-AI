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

## Automated Branch Pruning (#9917 / #10035)

Stale branches are pruned automatically — do not sweep by hand:

- **GitHub setting** *Automatically delete head branches* removes a PR's head branch on merge (repo owner toggles this; it is not code).
- **`branch-cleanup.yml`** (daily) deletes remote branches that are either merged-ancestor of `Dev_new_gui` and 7+ days old, or tied to a closed issue with a merged PR.
- **`scripts/cleanup-worktrees.sh`** prunes stale worktrees and local/remote branches for closed issues; also used for one-time backfills (#9911) — always `--dry-run` first.

**Safety guards (shared in `scripts/lib/branch-guards.sh`, tested by `branch-guards_test.sh`):** automated pruning must never delete a branch that is

1. **freshly pushed** — tip commit younger than `BRANCH_MIN_AGE_HOURS` (default 24h), closing the push→PR-creation gap (#10035);
2. **still open as a PR** — `gh pr list --head <branch> --state open`;
3. **mis-identified** — only `issue-NNNN` / `hotfix-NNNN` branches map to a GitHub issue. Date tokens (`...-2026-06-12`) and Paperclip `MVA-NNNN` work-items must never be read as issue numbers (use `extract_issue_number`, never a bare `\d{4,}`).

Merged-detection is **ancestor-based** (`git branch --merged`), never patch-equivalence — a rebased/squashed but unmerged branch is not treated as merged. Any new branch-deleting automation MUST source `branch-guards.sh` and apply these guards.

---

## Git Push Recovery

Before pushing, check for diverged remote:
```bash
git status && git log --oneline origin/<branch>..HEAD
```

If push rejected: fetch, rebase (`git rebase origin/<branch>`), resolve conflicts, then push. If rebase fails with conflicts you cannot resolve cleanly, stop and report — do NOT force-push and lose upstream changes.
