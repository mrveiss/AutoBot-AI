# Git, Branching & Worktree Rules

## Parallel Work: Worktree Isolation (CRITICAL)

**NO `git checkout` or `git switch` on shared branches during parallel work sessions.**

- **Each parallel task MUST have its own worktree:** `.worktrees/issue-XXXX/` with dedicated branch `issue-XXXX`
- **Main session stays on `Dev_new_gui`** — never check out feature branches
- **Why:** Switching branches in main session breaks all active worktrees that depend on that branch

**Preflight — REQUIRED before creating (#13964):**

`.worktrees/issue-XXXX` is derived from the issue number, so two sessions pointed
at one issue compute the **same path**. This clone is shared, so every session's
trees are visible — check before writing.

```bash
git worktree list                                   # every session's trees, not just yours
git show-ref --verify --quiet refs/heads/issue-XXXX && echo "BRANCH TAKEN"
git -C .worktrees/issue-XXXX status --short         # if it exists: any output = ACTIVE session
git -C .worktrees/issue-XXXX log --oneline -3       # commits you did not write = not yours
```

Three rules, each from a real collision:

- **Never pipe a command whose exit code gates the next step.**
  `git worktree add ... 2>&1 | tail -1` returns *tail's* status, so `&&` proceeds
  past `fatal: A branch named 'issue-N' already exists` — straight into another
  session's tree. Verified: piped `0`, unpiped `255`.
- **Uncommitted changes mean an ACTIVE session**, whatever the commit count says.
  A clean zero-commit tree is ambiguous; a dirty one is not. One collision was a
  tree that looked abandoned by every heuristic and held 83 uncommitted lines.
- **A lock reason is not proof of ownership.** A lock string can match your own
  task description because the tree *used to be* yours before another session
  took it over. Trust `git log`, not the lock.

**Backing out cleanly** if you claimed someone's tree — never `--force`:

```bash
git reset --soft HEAD~1        # drops YOUR empty claim commit, leaves their work untouched
git worktree unlock <path>     # restore the state you found
```

**Worktree Creation:**
```bash
# #15884: chained deliberately. As separate lines a FAILED fetch still lets the
# worktree be created from the previous origin/Dev_new_gui — a stale base, which
# is the exact thing this rule exists to prevent.
git fetch origin Dev_new_gui && \
  git worktree add .worktrees/issue-XXXX -b issue-XXXX origin/Dev_new_gui   # do NOT pipe this
cd .worktrees/issue-XXXX && git branch --unset-upstream
# Commit and push from here. Do NOT switch branches.
```

**Before `--force-with-lease`,** confirm the remote already contains your commit:

```bash
git merge-base --is-ancestor <your-sha> origin/issue-XXXX && echo "safe to force"
```

The `auto-update-pr-branches` workflow merges base into PR branches, so "my local
is behind my own branch" is normal. Force-pushing over it discards the bot's
merge.

---

## Pre-Flight Checklist

**Universal — before ANY code change**, including inside your own worktree:

1. `git status --porcelain` — if any files are dirty, commit them before going further.
   Uncommitted edits are silently discarded when a subagent commits and upstream is merged
   (#4969).
2. `git stash list` — if it is non-empty, **ask before proceeding**. The stash stack is shared
   across every worktree in the clone, so an entry may belong to another session.
   See [Never Stash](#never-stash-14078) below — reading the stack is safe, writing to it
   is not.
3. `git fetch origin Dev_new_gui` — do this *before* step 4, or the check below reads a stale
   ref and reports work as unlanded when it already merged.
4. Verify the issue isn't already resolved:
   `git log origin/Dev_new_gui --oneline --grep="#XXXX"`

**Additionally, before spawning agents or starting batch work:**

5. `git branch --show-current` — the **main session** must be on `Dev_new_gui`. This step is
   scoped to the dispatching session only; a worktree session is on `issue-XXXX` by mandate
   and must not "correct" itself onto the base.
6. Confirm Bash is approved in the main session — sub-agents inherit from the parent.
7. No stale worktree already claims the target path (see the preflight above).
8. For architectural decisions, state them in 1–2 sentences and wait for confirmation.

---

## Never Stash (#14078)

**`git stash` is a shared, repo-wide stack — not a per-worktree one.** Every worktree in the clone
pushes onto and pops from the same stack, and entries carry no owner, no branch and no issue link.

- **Never `git stash`.** Park work as a `wip:` commit on your own branch instead. It is owned,
  named, pushable, and cannot be consumed by anyone else.
- **Never `git stash pop`, `drop`, `clear` or `apply`.** The entry you take is very likely another
  session's, and popping it destroys their work with no recovery path.
- **Never `git restore --staged --worktree`.** Not a shared-stack hazard — a different one: it
  resets your own index and worktree from HEAD, discarding uncommitted work with no recovery.
  Back files up before reverting an experiment.

This is not hypothetical. #14078 found **113 stash entries** spanning three months, unowned and
unlinked. Rescuing them to branches and triaging them one by one took a full session; 17 of the 18
that looked stranded turned out to be work that had already landed, and the eighteenth was a
security fix nobody knew was sitting there (#15023).

**If you find a non-empty stack:** inventory it, never sweep it. Rescue an entry to a branch
(`git branch rescued/stash-<date>-<sha> <stash-sha>`) and open an issue naming the branch. Dropping
an entry is only correct once its content is demonstrably present in `Dev_new_gui`, and that is a
deliberate, evidenced act — not cleanup.

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
3. For branch deletions: verify merged via `git branch -r --merged origin/Dev_new_gui`.
   This is **ancestor-based and deliberately conservative** — under a squash merge it reports
   a landed branch as unmerged, which fails safe. It is *not* evidence that work is stranded:
   confirm that with `gh pr list --head <branch> --state all` before concluding anything was
   lost, and delete with `-D` once the PR shows MERGED.

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

**Install/refresh git hooks (one-time per clone, idempotent):** `bash scripts/install-git-hooks.sh` — copies real `pre-commit` (blocks commits to `main`/`master`) and `pre-push` files into the repo's hooks dir, normalises a bad `core.hooksPath`, and replaces any dangling symlink. Never symlinks into a worktree (#11598). Complementary to the pre-commit framework (`pre-commit install`, the preferred full quality suite): the installer is the fallback when the `pre-commit` binary isn't present and **preserves a framework-managed hook** (detected via its `generated by pre-commit` marker) instead of clobbering it.

Before committing any change to `.claude/hooks/block-dangerous-commands.sh`, run:
```bash
bash .claude/hooks/block-dangerous-commands_test.sh
```
Must be 0 failed, with at least 60 cases run — the suite asserts that floor itself, so a sandbox that failed to build cannot report clean (#15296). Add test cases for new rules. Use `bash` (GNU grep 3.7), not interactively — the shell `grep` alias is `ugrep` (PCRE2) which has different variable-length lookbehind support. See #8262.

CI runs it too, via `repo_tests/shell_lib_test.py`; before #15296 no workflow invoked it and it had been dormant since it was written. A new `*_test.sh` under `.claude/hooks/` or `scripts/lib/` must be registered in that file's `SHELL_SUITES` or it silently never runs.

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
