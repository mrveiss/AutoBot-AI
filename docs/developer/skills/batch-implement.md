---
name: batch-implement
description: Full implement→review→merge→close→discover loop for GitHub issues. Use this whenever the user says "implement all X-labeled issues", "fix all Y bugs", "run a batch on these issues", or gives a list of issue numbers to work on. Do NOT ask for scope clarification — just run the pre-flight and start.
---

# /batch-implement — Full Issue Resolution Loop

```bash
/batch-implement 4703 4704 4705          # explicit issue numbers
/batch-implement --label bug             # all open issues with label
/batch-implement --label bug --limit 9   # cap at N
```

**Core rule:** Agents commit locally. Main session always pushes.
**Batch size:** 3 agents max.

---

## Step 0: Umbrella Issue

- Ensure a GitHub umbrella issue exists with a task checklist (one checkbox per batch item).
- As each item lands (PR merged + issue closed), check it off on the umbrella issue.
- Create the umbrella if missing: `gh issue create --title "Batch: <label/description>" --body "- [ ] #N ..."`

---

## Step 1: Pre-Flight

1. `git branch --show-current` — must be `Dev_new_gui`. STOP if not.
2. `git status --porcelain` — must be empty. STOP if not.
3. Resolve issue list: `gh issue list --label <label> --state open --json number -q '.[].number'`
4. Skip if already in Dev_new_gui: `git log origin/Dev_new_gui --oneline --grep="#<n>" | head -1`
5. Skip if already closed: `gh issue view <n> --json state -q '.state'`
6. Clean stale worktrees: `git worktree remove .worktrees/issue-<n> --force && git branch -D issue-<n>`

Print summary before proceeding:
```
Pre-flight: To implement: #N, #M | Skipped: #K | Cleaned: N worktrees
```

---

## Step 2: Worktree Setup (per issue)

```bash
git worktree add .worktrees/issue-<n> -b issue-<n> origin/Dev_new_gui
cd .worktrees/issue-<n> && git branch --unset-upstream
```

- Agents MUST work inside the worktree — NEVER `git checkout` on the main tree.
- Each issue gets its own branch `issue-<n>`.

---

## Step 3: Dispatch Agents (batches of 3)

Track state per issue: `PENDING | IN_FLIGHT | SUCCESS | SUCCESS_TESTS_FAILING | RETRY_QUEUED | ESCALATED | SKIPPED`

Each agent must:
1. `gh issue view <n>` — read the issue.
2. Implement the fix inside the worktree.
3. `git commit -m "<type>(<scope>): <desc> (#<n>)"` — commit only, no push.
4. Report: `RESULT: SUCCESS|FAILURE | COMMIT_SHA: <sha> | TESTS: PASS|FAIL | ERROR: <if any>`

Agent prompt must include worktree isolation instructions (NEVER `git checkout` on main tree).

Self-healing failure table:

| Failure type | Auto-heal |
|---|---|
| API 529 overload | Wait 60s, retry (max 3×) |
| Merge conflict at push | Rebase onto latest Dev_new_gui, retry |
| Already resolved | Mark SKIPPED, close worktree |
| Agent crash / timeout | Retry (max 3×) |
| Tests failing | Mark SUCCESS_TESTS_FAILING — manual review |
| Unresolvable after 3× | ESCALATE — preserve worktree, print manual steps |

Repeat batches until all issues are `SUCCESS`, `SKIPPED`, or `ESCALATED`.

---

## Step 4: Pre-Push Verification (every PR before push)

```bash
# Re-fetch and abort if issue already closed during session
git fetch origin Dev_new_gui -q
gh issue view <n> --json state -q '.state'   # CLOSED → abort

# Type-check (frontend)
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json

# Tests for affected files
npx vitest run src/.../__tests__/<relevant>.test.ts
# or: pytest autobot-backend/<path> -xvs

# Extraction PRs only — behavioral grep audit (before/after; after-count must be 0)
grep -rnE "<behavior-pattern>" autobot-frontend/src --include="*.vue"
```

Push only after all checks pass: `git push -u origin issue-<n>`

---

## Step 5: Create & Review PR

```bash
gh pr create --base Dev_new_gui --head issue-<n> --title "..." --body "..."
```

- Syntax/imports: `python -m py_compile <file>` for Python; `vue-tsc` for TS/Vue.
- Call-site impact: grep that nothing removed is still called elsewhere.
- Wiring check: any new public module must have ≥1 production caller — HARD BLOCK if 0.
- Linting: `python -m black --check <files>`

Fix inline and re-push if validation fails. Never merge a failing PR.

---

## Step 6: Merge

```bash
gh pr merge <pr> --squash --delete-branch
git fetch origin && git log origin/Dev_new_gui --oneline --grep="#<n>" | head -1  # confirm
```

Merge one at a time. Verify before moving to next.

---

## Step 7: Close with Proof

```bash
gh issue close <n>
gh issue comment <n> --body "Closed — merged to Dev_new_gui. Commit: <sha>. Criteria met: <evidence>. Discoveries: <#N or none>"
```

Check off the item on the umbrella issue.

---

## Step 8: Discovery Issues

```bash
gh issue create --title "discovery(<area>): <gap found>" --body "<file:line, what's missing>" --label "tech-debt"
```

File before cleanup. Include in closure comment.

---

## Step 9: Cleanup & Summary

```bash
git worktree remove .worktrees/issue-<n> --force  # SUCCESS issues only; preserve ESCALATED
gh pr list --state open   # should be 0 for this batch
git worktree list          # should show only main
```

Print final table:
```
| Issue | PR    | Status    | Discoveries |
| #4703 | #4720 | MERGED    | #4725       |
| #4706 | —     | ESCALATED | —           |
```

Escalated: preserve worktree, print manual rebase steps for the user.

---

## Invariants

- Main session stays on `Dev_new_gui` — never switches branches.
- Agents commit only — main session pushes.
- Never merge without review; never close without proof (commit hash + criteria).
- Never leave PRs open overnight; never leave discoveries untracked.
- Escalated worktrees are preserved — never auto-delete.
- Anti-polling: if session must exit before all PRs merged, set issue to `in_review`, post one comment listing open PRs, schedule one wake-up — do not spin.
