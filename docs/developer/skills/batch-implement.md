---
name: batch-implement
description: Full implement→review→merge→close→discover loop for GitHub issues. Use this whenever the user says "implement all X-labeled issues", "fix all Y bugs", "run a batch on these issues", or gives a list of issue numbers to work on. Covers the complete workflow in one command: parallel implementation in worktrees, PR review, merge to Dev_new_gui, issue closure with proof, and discovery issue filing. Do NOT ask for scope clarification — just run the pre-flight and start.
---

# /batch-implement — Full Issue Resolution Loop

Implements a batch of GitHub issues end-to-end: parallel implementation → PR review → merge → issue closure with proof → discovery filing.

This is the complete workflow. It does not stop at PR creation — it runs through to closed issues with zero leftover branches.

## Usage

```bash
/batch-implement 4703 4704 4705          # explicit issue numbers
/batch-implement --label bug             # all open issues with label
/batch-implement --label bug --limit 9   # cap at N issues
```

When the user says "implement all X-labeled issues" or similar — launch immediately. Run the pre-flight, then start. Do not ask which issues to include or how many to run at a time.

## Core Design

**Agents commit locally. Main session always pushes.**

This architecture eliminates permission failures at the source: agents run in isolated contexts without SSH/tokens, so they commit only. The main session (which has full credentials) then pushes all changes. No more "git push permission denied" failures.

**Batch size: 3 agents max** — API rate limits (Anthropic 529 errors) cap useful concurrency at 3.

---

# Phase 0: Pre-Flight

Run all checks before touching anything:

```bash
# 1. Main session must be on Dev_new_gui
git branch --show-current   # must print: Dev_new_gui

# 2. Main session must be clean
git status --porcelain       # must be empty

# 3. Resolve issue list
if --label: gh issue list --label <label> --state open --json number -q '.[].number'
if explicit: use the numbers given

# 4. For each issue: skip if already resolved
git log origin/Dev_new_gui --oneline --grep="#<issue>" | head -1
# If found → mark SKIP "already in Dev_new_gui"

# 5. For each issue: skip if already closed on GitHub
gh issue view <issue> --json state -q '.state'
# If CLOSED → mark SKIP

# 6. Clean up any stale worktrees from prior crashed runs
for each issue: if .worktrees/issue-<n>/ exists → git worktree remove --force + git branch -D

# 7. Confirm Bash is approved in this session (sub-agents inherit)
```

If main session is NOT on Dev_new_gui: STOP. Do not proceed.

Report pre-flight summary before launching agents:
```
Pre-flight complete:
  To implement: #4703, #4704, #4705
  Skipped (resolved): #4702
  Worktrees cleaned: 1
```

---

# Phase 0c: Verification Mandate Before Push (#5142)

**Type-check is necessary but not sufficient.** Before pushing any commit that touches code covered by tests, run BOTH:

```bash
# 1. Type safety
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json
# Backend equivalent:
cd autobot-backend && python -m mypy <touched files>

# 2. Behavioral contract — run tests for affected files
npx vitest run src/composables/__tests__/<relevant>.test.ts
# Or for backend:
pytest autobot-backend/<touched module path> -xvs
```

**Why:** Type-check verifies the code compiles; it does NOT catch:
- Behavior changes that still match the type signature (returning `null` from `Promise<X>` when the function used to throw — TS sees the null as assignable through a generic's inference)
- Test contract violations (tests mocking impossible scenarios that the deleted code happened to make reachable)
- Runtime semantic drift (renamed identifiers, changed defaults, swallowed errors)

**Concrete incident (#5142):** PR #5141 deleted dead `if (!response) throw` blocks in `useKnowledgeBase.ts`. Type-check passed (0 errors). Then 3 tests failed at vitest run because they mocked `apiClient.get` to return null — the deleted check was the only path that threw. PR was closed as broken. ~30 minutes wasted.

**Rule of thumb:** Any PR that deletes or renames code in a file under `__tests__/` coverage MUST run that test file before push. Claiming "behave identically" without running the tests is a process failure.

## Pre-push duplicate check (#5143)

Before every `gh pr create` (or first `git push -u`), re-fetch and check whether the target issue was already closed by a merged PR during your working session. Long sessions (30+ min) are especially vulnerable — the repo moves underneath you:

```bash
git fetch origin Dev_new_gui -q

ISSUE_STATE=$(gh issue view <issue> --json state --jq '.state')
if [ "$ISSUE_STATE" = "CLOSED" ]; then
  echo "⚠️ Issue #<issue> is already closed — check if merged work supersedes yours"
  gh issue view <issue> --comments --limit 3
  # Likely cancel push; diff against origin/Dev_new_gui to see if anything remains to contribute
fi

# Does Dev_new_gui already contain a commit citing this issue?
if git log origin/Dev_new_gui --oneline -20 | grep -qE "#<issue>\b"; then
  echo "⚠️ Dev_new_gui has a commit citing #<issue> — verify it's not your work"
fi
```

If the issue is closed AND the merged commit supersedes your work: close your local branch, delete the remote if pushed, move on. A wasted 30 minutes beats a confusing duplicate PR in the reviewer's queue.

**Concrete incident (#5143):** PR #5141 was created for #5092 from a 30-min-stale `origin/Dev_new_gui`. Meanwhile PR #5128 had merged the same cleanup. Re-fetching before push would have caught it before any reviewer wasted time on the duplicate.

---

# Phase 0d: Behavioral Grep Audit (#5372, extraction PRs only)

**Applies only to "extract a primitive / composable" issues** — PRs that pull a duplicated pattern from N sites into a shared utility + migrate those sites.

**The problem this prevents:** The original issue body enumerates sites by grepping for a **symbol** (e.g. `handleKeydown`). Between filing and implementation, the set of sites that share the *behavior* (e.g. `key === 'Tab' && shiftKey && ...`) drifts from that enumeration:

- **Over-counted** (some listed sites already migrated via sibling PRs)
- **Under-counted** (other sites have the same behavior under a different symbol name, or were added to the codebase after the issue was filed)

**This is not hypothetical.** Session 150 had four instances:

| Issue | Listed sites | Real sites | Gap type |
|---|---|---|---|
| #5247 | 5 | 2 | Over-count (3 already migrated) |
| #5283 | 4 (explicit defer of BaseTable) | 5 | BaseTable was late-added |
| #5371 | 8 | 10 (#5410 added 2) | Under-count — grep missed two different-symbol dialogs |
| #5411 | 11 | 13 (#5410 doubled up) | Under-count — grep used symbol not behavior |

Miss rate: **50% of extraction PRs shipped an incomplete migration.** Every miss required a follow-up PR.

## The rule

For extraction PRs, the PR description **must** include a **"Behavioral grep audit"** section with before / after hit counts:

```markdown
## Behavioral grep audit

Before:
\`\`\`bash
$ grep -rnE "key\s*[=!]==\s*['\"]Tab|shiftKey\s*&&.*focus" autobot-frontend/src --include="*.vue"
# 3 hits — BaseModal, HostSelectionDialog, EntityDetail
\`\`\`

After:
\`\`\`bash
$ <same grep>
# 0 hits — all sites migrated to useFocusTrap
\`\`\`
```

**Three rules for the regex:**
1. **Match the behavior, not the symbol.** `handleKeydown` can be renamed; `key === 'Tab'` cannot.
2. **Cast wider than the issue's enumeration.** If the issue listed 3 sites, grep for the pattern across *the whole relevant tree* to surface sites the filer missed.
3. **The after-count must be 0** (or explicitly documented non-zero with a follow-up issue filed). Non-zero with no follow-up blocks merge.

**When in doubt, grep two ways:**
- A loose regex covering the pattern's core behavior
- A tight regex for a unique fingerprint (e.g. a specific CSS selector string, an unusual attribute combination)

If the two return different counts, investigate the delta — it's often the miss.

## What to write in the PR

A standard "Behavioral grep audit" block, as shown above, immediately after the "Summary" section. This is a merge gate — a missing audit section blocks review.

**Concrete examples from merged PRs:**
- [PR #5343](https://github.com/mrveiss/AutoBot-AI/pull/5343) — useFocusTrap extraction; amended post-merge to include the audit
- [PR #5390](https://github.com/mrveiss/AutoBot-AI/pull/5390) — 8-dialog a11y sweep
- [PR #5417](https://github.com/mrveiss/AutoBot-AI/pull/5417) — useInitialFocus + full kit for 2 missed dialogs
- [PR #5433](https://github.com/mrveiss/AutoBot-AI/pull/5433) — useBodyScrollLock + immediate: true fix

---

# Phase 1: Implement (Batches of 3, with Self-Healing)

## 1a. Create Isolated Worktrees

**CRITICAL (#6512): Parallel agents MUST use worktrees. This prevents commits landing on wrong branches.**

**For each issue in WORK_QUEUE:**

```bash
WORKTREE_PATH="/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-<number>"

# Clean up stale worktree from prior crashed run (idempotent)
if git worktree list | grep -q "issue-<number>"; then
  git worktree remove "$WORKTREE_PATH" --force 2>/dev/null
  git branch -D "issue-<number>" 2>/dev/null
fi

# Create fresh worktree — AGENTS MUST RUN INSIDE THIS
git worktree add "$WORKTREE_PATH" -b "issue-<number>" origin/Dev_new_gui
cd "$WORKTREE_PATH"
git branch --unset-upstream

# Verify isolated from main session
echo "Agent will work in: $(pwd)"
echo "Branch is: $(git branch --show-current)"  # should print: issue-<number>
echo "Main session remains on Dev_new_gui — checked separately"
```

**Key rules (non-negotiable):**
- Absolute paths: `/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-XXXX`
- Each issue gets dedicated branch `issue-XXXX`
- All worktrees isolated — no shared directories
- **Agents MUST cd into the worktree BEFORE making any git commits**
- **Agents MUST NEVER call `git checkout` on the main tree**

## 1b. Initialize Retry State Table

Create a markdown table in your context to track retry state across batches:

```
| Issue | Attempts | Last Failure Type | Status | Details |
|-------|----------|-------------------|--------|---------|
| #3405 | 0        | —                 | PENDING | waiting for agent |
| #3406 | 0        | —                 | PENDING | waiting for agent |
| #3407 | 0        | —                 | PENDING | waiting for agent |
```

**Status values:** `PENDING`, `IN_FLIGHT`, `SUCCESS`, `SUCCESS_TESTS_FAILING`, `RETRY_QUEUED`, `ESCALATED`, `SKIPPED`

Update this table after each batch completes. It becomes the source of truth for what needs retrying.

## 1c. Batched Dispatch Loop with Self-Healing

Agents run in batches of 3 max, each batch includes failure detection and automatic healing.

**Build work queue from retry table:**
```
QUEUE = all issues with status PENDING or RETRY_QUEUED
```

Take up to 3 from the queue. Spawn in parallel — each agent:

1. Reads the issue: `gh issue view <n>`
2. Implements the fix in the worktree
3. Commits (does NOT push): `git commit -m "<type>(<scope>): <desc> (#<n>)"`
4. Reports: `RESULT: SUCCESS|FAILURE`, `COMMIT_SHA: <sha>`, `TESTS: PASS|FAIL`, `ERROR: <if any>`

**Agent prompt must include:**
> "You have Bash, Read, Edit, Write, Grep, Glob permissions. Commit only — do NOT push. If you lose Bash permissions, STOP and report. Required tools: Bash, Read, Edit, Write, Grep, Glob.
>
> **CRITICAL — Worktree Isolation (Issue #6512):**
> - NEVER call `git checkout` on the main working tree
> - BEFORE making any changes, create an isolated worktree:
>   ```bash
>   ISSUE_NUM=<issue-number>
>   git worktree add .worktrees/issue-$ISSUE_NUM -b issue-$ISSUE_NUM origin/Dev_new_gui
>   cd .worktrees/issue-$ISSUE_NUM
>   git branch --unset-upstream
>   ```
> - Make all edits, commits, and git operations INSIDE that worktree directory
> - Your commit will land on the correct branch automatically
> - Do NOT switch branches or checkout anywhere else"

**Main session then pushes each successful branch and creates PR.**

## 1d. Self-Healing Failure Categorization

After each batch, categorize failures and apply automatic healing:

| Failure type | Detection | Auto-heal |
|---|---|---|
| API 529 overload | Agent reports rate limit | Wait 60s, retry (max 3×) |
| Merge conflict at push | `git push` rejected | Rebase onto latest Dev_new_gui, retry |
| Already resolved | `git log origin/Dev_new_gui --grep="#N"` hits | Mark SKIPPED, close worktree |
| Agent crash / timeout | No RESULT reported after N min | Retry (max 3×) |
| Tests failing but code committed | TESTS: FAIL | Mark SUCCESS_TESTS_FAILING — manual review needed |
| Permission denied (Bash/git) | Subagent can't run commands | STOP that agent — main session handles the git op |
| Unresolvable after 3× retries | Status RETRY_QUEUED with attempts=3 | ESCALATE — preserve worktree, print manual steps |

**Escalation format** (printed to user):
```
🚨 ESCALATED: #4706
  Reason: merge conflict in migrations/ that auto-rebase can't resolve
  Worktree preserved at: /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-4706
  Last attempt SHA: abc123
  Manual steps:
    cd .worktrees/issue-4706
    git rebase origin/Dev_new_gui
    # resolve conflicts manually
    git rebase --continue
    git push -u origin issue-4706
    gh pr create --base Dev_new_gui
```

Repeat batches until all issues are SUCCESS, SKIPPED, or ESCALATED.

---

# Phase 2: Review Each PR

For each PR created in Phase 1, run validation before merging. Do NOT merge without review.

```bash
# Get all open PRs for this batch
gh pr list --state open --json number,headRefName,title

# For each PR:
PR_BRANCH=$(gh pr view <pr> --json headRefName -q '.headRefName')
WORKTREE=".worktrees/$PR_BRANCH"

# 2a. Syntax + imports (Python)
for file in $(git diff origin/Dev_new_gui...$PR_BRANCH --name-only | grep "\.py$"); do
  python -m py_compile "$file" && python -c "import $(echo $file | sed 's|/|.|g;s|\.py||')" 2>&1
done

# 2b. Type check (frontend)
if git diff origin/Dev_new_gui...$PR_BRANCH --name-only | grep -qE "\.(ts|vue)$"; then
  cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1
fi

# 2c. Call-site impact — check nothing removed is still called
for removed in $(git diff origin/Dev_new_gui...$PR_BRANCH --diff-filter=D --name-only); do
  grep -r "$(basename $removed .py)" autobot-backend/ --include="*.py" | grep -v "_test.py" | grep -v "$removed"
done

# 2d. Wiring check — hard-block if any new module has 0 production callers
cd $(git rev-parse --show-toplevel) && pipeline-scripts/check-new-module-callers.sh

# 2e. Linting
python -m black --check $(git diff origin/Dev_new_gui...$PR_BRANCH --name-only | grep "\.py$") 2>&1
```

**If validation fails:** Fix inline in the worktree, push update to the branch, re-validate. Do not merge a failing PR.

**If wiring check exits 1 (unwired modules):** **HARD BLOCK** — do not merge and do not close the issue. Either wire the module in, or file a follow-up wire-in issue and re-run with `pipeline-scripts/check-new-module-callers.sh --allow-deferral .wiring-deferral.txt`. Document the deferral in the closure comment under `### Wire-in deferred to #NNNN`.

---

# Phase 2.5: Anti-Polling Rule (PR Wait)

**batch-implement is a self-contained session**: you review and merge your own PRs in the same run. Do **not** create PRs and then exit, leaving the batch issue `in_progress` for the next heartbeat to re-check.

If the batch session must exit before all PRs are merged (e.g. budget limit, rate limit after 3× retries):
- Update the batch issue to `in_review`, not `in_progress`.
- Post ONE comment listing which PRs are open: "Batch paused — PRs #N, #M await merge."
- Use `ScheduleWakeup` with `delaySeconds: 900` for a single deferred re-check.
- Do **not** spin with repeated identical "PRs still open" comments on every heartbeat.

This avoids the polling anti-pattern: an agent re-running every 2–5 min posting "PR open, awaiting merge" 11 times in 1h (GH#7623 / MVA-315).

---

# Phase 3: Merge Each PR

Merge immediately after review passes. Do not let PRs sit overnight.

```bash
# Merge to Dev_new_gui
gh pr merge <pr> --squash --delete-branch

# Confirm merge landed
git fetch origin
git log origin/Dev_new_gui --oneline --grep="#<issue>" | head -1
# Must show a commit — if empty, merge failed silently
```

Merge one PR at a time. After each merge, verify before moving to next.

---

# Phase 4: Close Issue with Proof

After the PR is confirmed merged, close the issue with a proof comment. **Never close before merge is confirmed.**

```bash
# Get the merge commit
MERGE_COMMIT=$(git log origin/Dev_new_gui --oneline --grep="#<issue>" | head -1 | awk '{print $1}')

# Close with proof
gh issue close <issue>
gh issue comment <issue> --body "$(cat <<'EOF'
✅ Closed — implementation merged to Dev_new_gui.

**Merge commit:** <MERGE_COMMIT>

**Acceptance criteria met:**
- ✅ <criterion 1> — <evidence>
- ✅ <criterion 2> — <evidence>

**Wiring verified:** <new code has caller at file:line> OR <N/A — no new public symbols>

**Discovery issues filed:** <#XXXX, #YYYY> OR <none found>
EOF
)"
```

Fill in acceptance criteria from the issue description. Evidence can be: test output, the diff itself, curl response. Be specific — "code exists" is not evidence.

---

# Phase 5: File Discovery Issues

During implementation and review, note any gaps found that are NOT part of the current issue. File them now before cleanup.

For each gap noticed:
```bash
gh issue create \
  --title "discovery(<area>): <what you found>" \
  --body "<description of the gap, file:line, what's missing>" \
  --label "tech-debt"
```

Common things to watch for:
- New dead code introduced (function defined, never called)
- Related bug in adjacent code noticed during review
- Missing test coverage for modified paths
- Hardcoded values that should use config
- Duplicate logic that could be consolidated

Include the list of discovery issues in the issue closure comment.

---

# Phase 6: Cleanup

```bash
# Remove worktrees for merged issues
for issue in <all SUCCESS issues>:
  git worktree remove .worktrees/issue-<n> --force 2>/dev/null
  # Branch already deleted by --delete-branch in gh pr merge

# Preserve ESCALATED worktrees — user needs them for manual resolution

# Final verification
gh pr list --state open    # should be 0 open PRs for this batch
git worktree list           # should show only main worktree
```

---

# Phase 7: Session Summary

Print a complete summary after all issues are processed:

```
# Batch Complete

| Issue | PR | Merged | Closed | Discoveries |
|-------|----|--------|--------|-------------|
| #4703 | #4720 | ✅ | ✅ | #4725 |
| #4704 | #4721 | ✅ | ✅ | none |
| #4705 | #4722 | ✅ | ✅ | #4726, #4727 |
| #4702 | — | SKIPPED | — | — |
| #4706 | — | ESCALATED | — | — |

✅ Resolved: 3 issues, 3 PRs merged
⏭️ Skipped: 1 (already in Dev_new_gui)
🚨 Escalated: 1 (see manual steps below)
📋 Discoveries filed: #4725, #4726, #4727

Open PRs remaining: 0
Stale worktrees remaining: 1 (issue-4706, preserved for manual resolution)
```

For each ESCALATED issue, print the exact manual resolution commands (see Phase 1d escalation format).

---

# Invariants (Never Violate)

- Main session stays on Dev_new_gui throughout — never switches branches
- Every issue gets its own worktree — no shared branches
- Agents commit only — main session always pushes
- Never merge without review — even "trivial" PRs
- Never close without proof — commit hash + criteria + evidence
- Never leave PRs open overnight — merge immediately after review passes
- Never leave discoveries untracked — file issues before cleanup
- Escalated worktrees are preserved — never auto-delete them
- Phase 0c verification (type-check + tests) runs before every push
- Phase 0d behavioral grep runs on every extraction PR
