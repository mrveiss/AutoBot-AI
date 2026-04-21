---
name: team-implement
description: Parallel implementation of multiple GitHub issues with self-healing retry logic and automatic failure recovery
---

# /team-implement - Parallel Multi-Issue Implementation with Self-Healing

Implements multiple GitHub issues in parallel using isolated agent teams. Each agent works independently in its own worktree. Built-in self-healing automatically handles permission failures, API overload, merge conflicts, and escalates only truly unresolvable issues.

## Core Design

**Agents commit locally. Main session always pushes.**

This architecture eliminates permission failures at the source: agents run in isolated contexts without SSH/tokens, so they commit only. The main session (which has full credentials) then pushes all changes. No more "git push permission denied" failures.

## Usage

```bash
/team-implement <issue1> <issue2> <issue3> [<issue4> ...]
# Example: /team-implement 3405 3406 3407 3408
```

---

# Workflow

## Phase 0: Pre-Flight Verification + Already-Resolved Check

**For EACH issue before creating any worktrees:**

```bash
# Check 1: Does the issue exist?
gh issue view <issue> --json state -q '.state'
# If 404/error: STOP, ask user if issue number is correct

# Check 2: Is the issue already closed on GitHub?
ISSUE_STATE=$(gh issue view <issue> --json state -q '.state')
if [ "$ISSUE_STATE" == "CLOSED" ]; then
  mark issue as SKIP with note: "Already closed"
  continue to next issue
fi

# Check 3: Is the fix already on Dev_new_gui?
if git log origin/Dev_new_gui --oneline | grep -qE "#<issue>\b"; then
  mark issue as SKIP with note: "Fix already merged to Dev_new_gui"
  gh issue close <issue> --comment "✅ Already fixed in Dev_new_gui"
  continue to next issue
fi
```

**Result:** Collect all non-skipped issues into the WORK_QUEUE. Create retry state table:

```
| Issue | Attempts | Last Failure Type | Status  |
|-------|----------|-------------------|---------|
| #3405 | 0        | —                 | PENDING |
| #3406 | 0        | —                 | PENDING |
| #3407 | 0        | —                 | PENDING |
(skip closed/already-fixed issues — don't show in table)
```

---

## Phase 0b: Pre-Implementation Validation (NEW)

**Before creating any worktrees, verify preconditions for EACH issue:**

```bash
for issue in <WORK_QUEUE>; do
  
  # Check 1: Branch state in main session
  CURRENT_BRANCH=$(git branch --show-current)
  if [ "$CURRENT_BRANCH" != "Dev_new_gui" ]; then
    echo "❌ STOP: Main session on $CURRENT_BRANCH, not Dev_new_gui"
    exit 1
  fi
  
  # Check 2: Main session is clean
  if ! git status --porcelain | grep -q ""; then
    echo "⚠️ Main session has uncommitted changes. Stash first."
    git stash
  fi
  
  # Check 3: Verify issue branch doesn't already exist on Dev_new_gui
  if git log origin/Dev_new_gui --oneline | grep -qE "#$issue\b"; then
    echo "⏭️ #$issue: Fix already in Dev_new_gui (closed by prior batch)"
    mark issue as SKIPPED
    continue
  fi
  
  # Check 4: Verify no stale worktree exists
  WORKTREE_PATH="/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-$issue"
  if [ -d "$WORKTREE_PATH" ]; then
    echo "🧹 Cleaning up stale worktree for #$issue"
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null
    git branch -D "issue-$issue" 2>/dev/null
  fi
done

# Result: WORK_QUEUE is now verified clean, ready for agent dispatch
```

**Key validations:**
- ✅ Main session on Dev_new_gui (prevents branch isolation violation)
- ✅ Main session is clean (no uncommitted changes)
- ✅ Issue fix not already in Dev_new_gui (prevents redundant work)
- ✅ No stale worktrees (prevents conflicts)

---

## Phase 0c: Verification Mandate Before Push (NEW — #5142)

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

### Pre-push duplicate check (NEW — #5143)

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

## Phase 0d: Behavioral Grep Audit (NEW — #5372, extraction PRs only)

**Applies only to "extract a primitive / composable" issues** — PRs that pull a duplicated pattern from N sites into a shared utility + migrate those sites.

**The problem this prevents:** The original issue body enumerates sites by grepping for a **symbol** (e.g. `handleKeydown`). Between filing and implementation, the set of sites that share the *behavior* (e.g. `key === 'Tab' && shiftKey && ...`) drifts from that enumeration:

- **Over-counted** (some listed sites already migrated via sibling PRs)
- **Under-counted** (other sites have the same behavior under a different symbol name, or were added to the codebase after the issue was filed)

**This is not hypothetical.** Four instances this session:

| Issue | Listed sites | Real sites | Gap type |
|---|---|---|---|
| #5247 | 5 | 2 | Over-count (3 already migrated) |
| #5283 | 4 (explicit defer of BaseTable) | 5 | BaseTable was late-added |
| #5371 | 8 | 10 (#5410 added 2) | Under-count — grep missed two different-symbol dialogs |
| #5411 | 11 | 13 (#5410 doubled up) | Under-count — grep used symbol not behavior |

Miss rate: **50% of extraction PRs this session shipped an incomplete migration.** Every miss required a follow-up PR.

### The rule

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

### What to write in the PR

A standard "Behavioral grep audit" block, as shown above, immediately after the "Summary" section. This is a merge gate — a missing audit section blocks review.

**Concrete examples from merged PRs:**
- [PR #5343](https://github.com/mrveiss/AutoBot-AI/pull/5343) — useFocusTrap extraction; amended post-merge to include the audit
- [PR #5390](https://github.com/mrveiss/AutoBot-AI/pull/5390) — 8-dialog a11y sweep
- [PR #5417](https://github.com/mrveiss/AutoBot-AI/pull/5417) — useInitialFocus + full kit for 2 missed dialogs
- [PR #5433](https://github.com/mrveiss/AutoBot-AI/pull/5433) — useBodyScrollLock + immediate: true fix

---

## Phase 1: Create Isolated Worktrees (idempotent)

**For each issue in WORK_QUEUE:**

```bash
WORKTREE_PATH="/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-<number>"

# Clean up stale worktree from prior crashed run (idempotent)
if git worktree list | grep -q "issue-<number>"; then
  git worktree remove "$WORKTREE_PATH" --force 2>/dev/null
  git branch -D "issue-<number>" 2>/dev/null
fi

# Create fresh worktree
git worktree add "$WORKTREE_PATH" -b "issue-<number>" origin/Dev_new_gui

# Verify branch is correct
cd "$WORKTREE_PATH" && git branch --show-current  # should print: issue-<number>
```

**Key rules:**
- Absolute paths: `/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-XXXX`
- Each issue gets dedicated branch `issue-XXXX`
- All worktrees isolated — no shared directories

---

## Phase 2: Initialize Retry State Table

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

---

## Phase 3: Batched Dispatch Loop with Self-Healing

This is the core workflow. Agents run in batches of 3 max, each batch includes failure detection and automatic healing.

### 3a. Build Work Queue from Retry Table

```
QUEUE = all issues with status PENDING or RETRY_QUEUED
```

### 3b. Process Batches in a Loop

```bash
WHILE QUEUE is not empty:
  
  # Take first batch (max 3 issues)
  BATCH = first min(3, len(QUEUE)) issues from QUEUE
  
  # 60-second cooldown for API 529 issues
  if any issue in BATCH has NEEDS_COOLDOWN flag:
    echo "Cooling down after API 529 error — waiting 60 seconds..."
    sleep 60
    clear NEEDS_COOLDOWN flags
  
  # Set status to IN_FLIGHT
  for each issue in BATCH:
    update retry_table: status = IN_FLIGHT
  
  # Launch agents in PARALLEL (single agent dispatch, not serial)
  # See "Agent Prompt" section below
  RESULTS = spawn_agents(BATCH)
  
  # Process results with self-healing
  for each (issue, result) in RESULTS:
    classify_and_heal(issue, result)  # See Phase 3c
  
  # Rebuild queue for next iteration
  QUEUE = all issues with status RETRY_QUEUED
  
  # Log progress
  echo "Batch complete. Next queue: $QUEUE"
```

### 3c. Classify and Heal Function

After each agent returns, classify the result and apply the right handler:

```
FUNCTION classify_and_heal(issue, agent_result):
  
  # Increment attempt counter
  retry_table[issue].Attempts += 1
  current_attempts = retry_table[issue].Attempts
  
  # ─── SUCCESS PATH ────────────────────────────────────────
  if agent_result.RESULT == "SUCCESS" and agent_result.COMMIT_SHA exists:
    
    WORKTREE_PATH = /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-$issue
    
    # Step 1: Fetch latest origin/Dev_new_gui
    cd $WORKTREE_PATH && git fetch origin
    
    # Step 2: Attempt push
    if git push origin issue-$issue -u 2>&1; then
      PUSH_SUCCESS = true
    else
      # Push failed — likely a non-fast-forward. Rebase and retry.
      if git rebase origin/Dev_new_gui 2>&1; then
        git push origin issue-$issue
        PUSH_SUCCESS = true
      else
        # Rebase has conflicts — go to merge conflict handler
        PUSH_SUCCESS = false
        push_failure_reason = "MERGE_CONFLICT"
      fi
    fi
    
    if PUSH_SUCCESS:
      # Step 3: Run pre-merge validation
      cd "$WORKTREE_PATH"
      
      VALIDATION_OUTPUT=$(/pre-merge-validate issue-$issue 2>&1)
      VALIDATION_STATUS=$?
      
      if [ $VALIDATION_STATUS -ne 0 ]; then
        # Validation failed — prevent PR from being created
        cd /home/martins/AutoBot-Ai/AutoBot-AI  # back to main
        update retry_table[issue]: status = RETRY_QUEUED, Last Failure = "VALIDATION_FAILED"
        echo "⚠️ #$issue: Pre-merge validation BLOCKED:"
        echo "$VALIDATION_OUTPUT"
        return  # Don't create PR — let agent or user fix the issues
      fi
      
      # Step 4: Create PR from main session
      cd /home/martins/AutoBot-Ai/AutoBot-AI  # back to main
      
      gh pr create \
        --base Dev_new_gui \
        --head issue-$issue \
        --title "fix: <from agent summary> (#$issue)" \
        --body "Closes #$issue\n\n## Summary\n<from agent>\n\n## Test Status\n$agent_result.TESTS"
      
      if agent_result.TESTS == "FAIL":
        # Test failures don't block — create PR anyway, flag it
        update retry_table[issue]: status = SUCCESS_TESTS_FAILING, Last Failure = "test failure"
        echo "⚠️ #$issue: PR created but tests failing"
      else:
        update retry_table[issue]: status = SUCCESS, Last Failure = "—"
        echo "✅ #$issue: SUCCESS"
      fi
      return
  
  # ─── FAILURE CLASSIFICATION & HEALING ────────────────────
  
  failure_text = agent_result.ERROR  (convert to lowercase for matching)
  
  # Handler A: API 529 Overload
  if "529" in failure_text or "overloaded" in failure_text or "rate limit" in failure_text:
    if current_attempts < 3:
      update retry_table[issue]: status = RETRY_QUEUED
      set retry_table[issue].NEEDS_COOLDOWN = true
      update retry_table[issue].Last Failure = "API_529"
      echo "⏳ #$issue: API 529 — will retry after cooldown (attempt $current_attempts/3)"
      return
    else:
      ESCALATE(issue, "API 529 persists after 3 attempts. Rate limiting may be severe.")
      return
  
  # Handler B: Merge Conflict
  if "CONFLICT" in failure_text or "conflict" in failure_text or "rebase failed" in failure_text:
    if current_attempts < 3:
      WORKTREE_PATH = /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-$issue
      cd $WORKTREE_PATH
      
      # Attempt auto-rebase
      if git rebase origin/Dev_new_gui 2>&1; then
        # Rebase succeeded — retry the agent
        update retry_table[issue]: status = RETRY_QUEUED
        update retry_table[issue].Last Failure = "MERGE_CONFLICT_HEALED"
        echo "🔄 #$issue: Merge conflict resolved via rebase — retrying agent"
        return
      else:
        # Rebase has conflicts — unresolvable
        git rebase --abort 2>/dev/null
        ESCALATE(issue, "Merge conflict with Dev_new_gui — rebase produced conflicts. Requires manual resolution.")
        return
      fi
    else:
      ESCALATE(issue, "Merge conflict — 3 rebase attempts failed. Requires manual resolution.")
      return
  
  # Handler C: Already Resolved (caught late by agent)
  if "nothing to commit" in failure_text or "no changes" in failure_text or "already fixed" in failure_text:
    update retry_table[issue]: status = SKIPPED
    update retry_table[issue].Last Failure = "ALREADY_RESOLVED_BY_AGENT"
    WORKTREE_PATH = /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-$issue
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null
    git branch -D "issue-$issue" 2>/dev/null
    echo "⏭️ #$issue: Already resolved — skipped"
    return
  
  # Handler D: Agent Timeout / Crash / No Result
  if agent_result is empty or agent_result.RESULT is missing:
    if current_attempts < 3:
      update retry_table[issue]: status = RETRY_QUEUED
      update retry_table[issue].Last Failure = "AGENT_CRASH"
      echo "💥 #$issue: Agent crashed or timed out — retrying (attempt $current_attempts/3)"
      return
    else:
      ESCALATE(issue, "Agent crashed/timed out 3 times. Check agent logs for persistent errors.")
      return
  
  # Handler E: Unknown / Uncategorized Failure
  else:
    if current_attempts < 3:
      update retry_table[issue]: status = RETRY_QUEUED
      update retry_table[issue].Last Failure = "UNKNOWN_ERROR"
      echo "❓ #$issue: Unknown error — retrying (attempt $current_attempts/3)"
      echo "   Error: $(echo $failure_text | head -c 100)..."
      return
    else:
      ESCALATE(issue, "Unknown error after 3 attempts:\n$failure_text")
      return


FUNCTION ESCALATE(issue, reason):
  update retry_table[issue]: status = ESCALATED
  update retry_table[issue].Last Failure = "ESCALATED"
  # DO NOT remove worktree — preserve for user inspection
  update retry_table[issue].Details = "Requires manual intervention: $reason"
  echo "🚨 #$issue: ESCALATED — $reason"
```

### Agent Prompt (what to instruct agents to do)

Each agent receives this instruction set. Key: agents commit only, do NOT push.

```
Working directory: /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-<number>

1. Read the GitHub issue with:
   gh issue view <number>

2. Create brief implementation plan (max 10 lines):
   - Files to modify
   - Key changes
   - Any risks

3. Implement changes directly (no sub-agents unless >8 files):
   - Read files with Read tool
   - Make changes with Edit/Write
   - Verify syntax as you go

4. Run relevant tests:
   pytest <test_path> -xvs
   # If tests fail, note the failures but continue to step 5

5. Run linting on modified files:
   flake8 --max-line-length=100 <modified_files>
   # If linting fails, fix the issues

6. Stage and commit:
   git add -A
   git commit -m "fix: <description> (#<number>)"
   
   VERIFY: git log --oneline -1  # should show your commit

7. Report back with EXACT format (critical for healing logic):
   
   RESULT: SUCCESS or FAILURE
   COMMIT_SHA: <output of: git rev-parse HEAD>
   TESTS: PASS or FAIL
   TEST_SUMMARY: <if FAIL, which tests failed>
   ERROR: <if FAILURE, the exact error message>
   
   ⚠️ DO NOT RUN git push — main session handles all pushes

8. Return this report. Main session will push and create PR.

CRITICAL RULES:
- Stay in your worktree (.worktrees/issue-<number>)
- Do NOT touch other worktrees
- Do NOT switch branches
- Do NOT attempt git push
- Target issue-<number> branch (already checked out)
- If blocked by dependencies, note in ERROR field

PERMISSION REQUIREMENTS (Verified at Dispatch):
- Bash permissions: required for git commands, pytest, linting
- Read/Edit/Grep: required for code changes
- If you lose Bash permission during git operations, STOP and report what you've done — don't retry
- Main session (with full credentials) will handle git push; you only commit
```

---

## Phase 4: Summary Report

After all batches complete and QUEUE is empty, generate a summary:

```
# Parallel Implementation Results

| Issue | PR | Status | Tests | Attempts | Failure History |
|-------|----|--------|-------|----------|-----------------|
| #3405 | [#4200](url) | SUCCESS | PASS | 1 | — |
| #3406 | [#4201](url) | SUCCESS_TESTS_FAILING | FAIL | 2 | API_529 → retry |
| #3407 | — | ESCALATED | — | 3 | MERGE_CONFLICT × 3 |
| #3408 | — | SKIPPED | — | 0 | ALREADY_RESOLVED |

✅ Successful: 1 (fully) + 1 (tests failing)  
⏭️ Skipped: 1  
🚨 Escalated: 1  

---

## Manual Resolution Required

### Issue #3407 — Merge Conflict (Escalated)

**Problem:** Rebase with Dev_new_gui produced conflicts after 3 attempts.

**Worktree:** Preserved at `/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-3407`  
**Branch:** `issue-3407`

**Manual resolution steps:**

\`\`\`bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-3407

# Check current state
git status

# If rebasing, abort and restart
git rebase --abort 2>/dev/null

# Rebase on latest Dev_new_gui
git fetch origin
git rebase origin/Dev_new_gui

# Fix conflicts (edit files, then:)
git add <resolved_files>
git rebase --continue

# Push
git push origin issue-3407

# Create PR from main session:
cd /home/martins/AutoBot-Ai/AutoBot-AI
gh pr create --base Dev_new_gui --head issue-3407 --title "fix: <description> (#3407)" --body "..."
\`\`\`
```

---

## Phase 4b: Post-Merge Gap Audit (NEW)

**After all PRs are merged to Dev_new_gui, run automated gap discovery:**

```bash
# Only run if there were SUCCESS merges (don't audit if only escalations/skips)
if [ $SUCCESS_COUNT -gt 0 ]; then
  echo "🔍 Running post-merge gap audit..."
  
  # Run dead-code-audit to discover new gaps introduced
  /dead-code-audit 2>&1 | tee gap-audit-output.txt
  
  # Extract issue numbers from output
  NEW_ISSUES=$(grep "^https://github.com/mrveiss/AutoBot-AI/issues/" gap-audit-output.txt | grep -oE "#[0-9]+" | sort -u)
  
  if [ -n "$NEW_ISSUES" ]; then
    echo "📋 New discovery issues filed:"
    echo "$NEW_ISSUES"
    echo ""
    echo "Review and prioritize in next batch."
  else
    echo "✅ No new dead/unwired code detected."
  fi
fi
```

**Why:** Detects regressions introduced by merged code (missing imports, orphaned functions, new dead code) immediately rather than waiting for next audit cycle.

**Expected output:** 0-5 new discovery issues per batch (normal)

---

## Phase 5: Cleanup (Preserve Escalated Worktrees)

```bash
# Clean up SUCCESS and SKIPPED worktrees
for issue in <all SUCCESS and SKIPPED issues>:
  WORKTREE="/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-$issue"
  git worktree remove "$WORKTREE" --force 2>/dev/null
  git branch -D "issue-$issue" 2>/dev/null

# DO NOT remove ESCALATED worktrees
# Print reminder for each escalated issue
for issue in <all ESCALATED issues>:
  echo "Preserved worktree: .worktrees/issue-$issue — needs manual resolution"
  echo "See 'Manual Resolution Required' section above for steps"
```

---

## Phase 6: Amendments and Follow-ups (NEW — #5045)

**When adding a follow-up commit to a PR already opened by a previous batch (self-review fixes, reviewer feedback, etc.):**

Do **NOT** assume the branch you pushed to earlier is still the PR's head. Between the original push and your follow-up, the user may have merged the PR — at which point pushing the amendment to the old branch is a silent no-op (the commit lands on a now-closed PR's dangling branch).

**Required check before every amendment push:**

```bash
# Query PR state before amending
PR_STATE=$(gh api repos/mrveiss/AutoBot-AI/pulls/<PR-number> --jq '.state')
PR_MERGED=$(gh api repos/mrveiss/AutoBot-AI/pulls/<PR-number> --jq '.merged')

if [ "$PR_STATE" = "closed" ] || [ "$PR_MERGED" = "true" ]; then
  echo "⚠️ PR #$PR-number is $PR_STATE (merged=$PR_MERGED) — cannot amend."
  echo "Strategy: create a new branch from current origin/Dev_new_gui,"
  echo "          cherry-pick the amendment commit, open a fresh PR"
  echo "          that references the merged PR."
  
  # Fresh-branch strategy:
  git fetch origin Dev_new_gui
  git worktree add .worktrees/issue-<new-issue> -b issue-<new-issue> origin/Dev_new_gui
  cd .worktrees/issue-<new-issue>
  git cherry-pick <amendment-sha>
  git push origin issue-<new-issue> -u
  gh pr create --base Dev_new_gui --head issue-<new-issue> \
    --title "..." \
    --body "Follow-up to #<merged-PR>. Closes #<discovery-issue>..."
else
  # Safe to amend — push to the existing open branch
  git push origin issue-<original-number>
fi
```

**Why this check matters:**

Without it, an amendment push "succeeds" at the git level but lands on an orphaned branch that no one is reviewing. The follow-up work appears lost. Past sessions have lost hours of work recovering from this — see the discussion in #5045 for a concrete incident (PRs #5008, #5009 merged mid-amendment, forcing retroactive fresh-PR recovery).

**Rule of thumb:** If more than a few minutes have passed between original PR creation and an amendment, verify state first. The cost of the check (one API call) is trivial compared to the cost of silently losing the work.

> **Note:** The new-PR-creation duplicate check (issue closed mid-session by another PR) was moved to **Phase 0c** where it logically belongs. See there.

**Stale branch cleanup:** After confirming an old PR is merged and you have created a fresh-branch amendment PR, the original branch is now orphaned on remote. Delete it to keep `gh pr list` and `git branch -r` clean:

```bash
git push origin --delete issue-<original-number>
# Local cleanup
git worktree remove .worktrees/issue-<original-number> --force 2>/dev/null
git branch -D issue-<original-number> 2>/dev/null
```

Skip this if the orphaned branch holds work that didn't make it into the merge — verify with `git log issue-<original-number> --not origin/Dev_new_gui` first.

---

# Success Criteria

- [ ] All non-skipped issues attempted (Attempts > 0)
- [ ] Each SUCCESS issue has a PR created and merged-ready
- [ ] Each ESCALATED issue has exact manual resolution commands in output
- [ ] No agents are retried beyond 3 times
- [ ] Retry table shows complete history (can trace each issue through attempts)
- [ ] No worktrees left running after cleanup (except ESCALATED — preserved)
- [ ] Summary table lists all issues with status
- [ ] Before any amendment push, PR state was checked (#5045) — never push to a merged/closed PR's branch

---

# Key Features

**Automatic Recovery:**
- Agents fail → Main session detects and heals → Automatic retry
- Permission failures → No longer happen (agents never push)
- Merge conflicts → Auto-rebased, retried
- API overload → Backoff + retry after cooldown
- Already-resolved → Skipped, not wasted

**Escalation Only When Needed:**
- Max 3 retries per issue
- Only show manual intervention for truly unresolvable issues
- Full context + exact commands for manual fixes

**Transparency:**
- Retry table in context shows attempt history
- Summary table shows what succeeded vs. what needs work
- No silent failures — everything escalated is visible
