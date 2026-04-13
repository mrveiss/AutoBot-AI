# AutoBot Development Instructions

> **Full rules:** [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) — read when starting a new task
> **Full workflow:** [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) — read when needed
> **Reference (IPs, playbooks):** [`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)
> **Worktrees:** Use `.worktrees/` (project-local, gitignored) for all parallel/isolated work

---

## Engineering Standard

You are the world's best AI developer working on AutoBot. Every decision must optimize for **correctness, speed, and maintainability** — in that order. No wasted motion. No speculative work. No half-measures.

**Efficiency rules:**

- **Parallelize everything possible** — run independent tool calls, file reads, and agent tasks concurrently
- **Minimal surface area** — write the least code that fully solves the problem; every extra line is future maintenance debt
- **Async-first** — all I/O must be non-blocking; never add sync calls to async paths
- **Algorithm awareness** — O(n²) loops on large datasets, N+1 Redis calls, and blocking waits are bugs, not style issues
- **Lean commits** — one logical change per commit, no dead code, no commented-out experiments

**Decision speed:** Form a hypothesis in ≤3 exploration commands, then act. If stuck after 3 attempts, escalate to user with findings — don't loop.

---

## Quick Reference

**Every task must:** link to GitHub issue, search Memory MCP first, break into subtasks, use code-reviewer agent, update issue throughout, verify before closing.

**Before proceeding:** Work tied to issue? Subtasks added? Memory searched? Root cause (not workaround)? If ANY fails: STOP.

---

## Core Rules (Summary)

1. **Check Before Writing** — search for existing code/docs/PRs before creating anything new
2. **Reuse Existing Code** — import from `autobot_shared/`, never duplicate or hardcode
3. **Standardize for Reuse** — shared modules, ≤30-line functions, no `_v2`/`_fix` suffixes
4. **Clarify Requirements** — ask all questions up front, confirm architecture before coding
5. **Verify Before Complete** — show evidence (test output, curl, build) before claiming done
6. **Report Every Problem** — file GitHub issues for all discovered bugs, even if not your task

> Full details with examples and violation cases: [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md)

---

## Essential Patterns

**Redis:** `from autobot_shared.redis_client import get_redis_client` (databases: main, knowledge, prompts, analytics)

**Config:** `from autobot_shared.ssot_config import config` / `import { getBackendUrl } from '@/config/ssot-config'`

**Logging:** `logging.getLogger(__name__)` (backend) / `createLogger('Name')` (frontend). No `print()` or `console.*`.

**Encoding:** Always `encoding='utf-8'` explicitly.

**Copyright:** `mrveiss` is sole owner/author of all AutoBot code.

---

## Key Workflow Rules

- **Branch target:** `Dev_new_gui` for all PRs unless told otherwise
- **Commit format:** `<type>(scope): <description> (#issue-number)`
- **Pre-commit:** Never `--no-verify`. PostToolUse hook auto-formats `.py` files.
- **Branching discipline:** Direct commits on `main`/`master` are blocked by pre-commit hook (Issue #4113). All development flows through `Dev_new_gui` first.
- **Worktrees:** No nesting. Manual creation for PRs (not `isolation: "worktree"`). Clean up after issue closure.
- **Agents:** Prefer direct implementation. Reserve subagents for research/exploration. Subagents can't acquire Bash permission.
- **Codebase is source of truth:** Changes only in this git repo directory. Never edit `/opt/autobot/`, `/var/log/autobot/`, or other deployment folders. Ansible syncs code from GitHub each playbook run.
- **Deployment:** All via Ansible playbooks. Never manual SSH changes.
- **No temporary fixes:** Zero tolerance for workarounds, TODO comments, try/catch hiding errors.
- **One issue per session:** Don't auto-start other issues after completing one.
- **Edit strategy:** `Edit` for files >50 lines, `Write` for new/small files.

> Full workflow details: [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md)

---

## Parallel Work: Worktree Isolation Rules (CRITICAL)

**NO `git checkout` or `git switch` on shared branches during parallel work sessions.**

- **Each parallel task MUST have its own worktree:** `.worktrees/issue-XXXX/` with dedicated branch `issue-XXXX`
- **Main session stays on `Dev_new_gui`** — never check out feature branches. All feature work happens in worktrees.
- **Worktree branches are independent** — changes in one worktree cannot affect another worktree's branch or main session
- **Why:** Switching branches in main session breaks all active worktrees that depend on that branch. Creates merge conflicts, stale branch pointers, corrupted git history.

**Worktree Creation:**
```bash
git worktree add .worktrees/issue-XXXX -b issue-XXXX origin/Dev_new_gui
cd .worktrees/issue-XXXX && git branch --unset-upstream
# Work here, commit, push to issue-XXXX branch
# Do NOT switch branches; do NOT touch other worktrees
```

See memory for [Worktree Isolation (CRITICAL)](https://github.com/mrveiss/AutoBot-AI/blob/Dev_new_gui/docs/developer/CLAUDE.md#parallel-work-worktree-isolation-rules-critical) — detailed scenario of what breaks if you switch branches.

---

## Pre-Flight Checklist (Before Parallel Work)

Before spawning agents or starting worktree work:

1. **Verify branch isolation:** `git branch --show-current` in main session. Should be `Dev_new_gui`. If on a feature branch, STOP — you'll break parallel worktrees.
2. **Create worktrees correctly:** Each issue gets `.worktrees/issue-XXXX/` with dedicated branch. NO shared branches between worktrees.
3. **Check git status:** `git status` — main session must be clean (no uncommitted changes).
4. **Verify issue isn't resolved:** Check if issue is already closed or if `Dev_new_gui` already has the fix.
5. **Confirm approach:** For architectural decisions, state in 1-2 sentences and wait for confirmation.

**Critical:** If you accidentally switched to a feature branch during parallel work, immediately switch back to `Dev_new_gui`. You may have broken active worktrees.

---

## Branching Discipline (Issue #4113)

**PROTECTED BRANCHES:** Direct commits are blocked by pre-commit hook.
- `main` — Release branch (stable, read-only via hook)
- `master` — Alias for main (legacy, also protected)

**ALLOWED BRANCHES:** You can commit on these:
- `Dev_new_gui` — Active development (default target for all PRs)
- `issue-*` — Feature branches (must flow through Dev_new_gui to main)
- `hotfix-*` — Hotfix branches (reviewed before merging)
- Any worktree branch matching above patterns

**WORKFLOW:**
1. Create feature branch: `git checkout -b issue-XXXX origin/Dev_new_gui`
2. Make changes and commit on your feature branch
3. Push: `git push -u origin issue-XXXX`
4. Open PR: `issue-XXXX` → `Dev_new_gui` (NOT directly to main)
5. After review, merge to `Dev_new_gui`
6. Later, `Dev_new_gui` is merged to `main` (release cycle)

**WHY:** Issue #4113 found commits went to `main` instead of `Dev_new_gui`, reversing branching discipline. The pre-commit hook prevents this.

**IF YOU SEE "COMMIT BLOCKED":**
The pre-commit hook rejected your commit on `main` or `master`. This is correct — switch to a feature branch and re-apply your changes:
```bash
git checkout issue-XXXX  # or create new: git checkout -b issue-XXXX origin/Dev_new_gui
# Re-apply your changes
git add -A && git commit -m "..."
```

---

## Parallel Agents Strategy

When spawning multiple agents for batch work with `/team-implement`:

1. **Verify main session isolation:** Main session MUST stay on `Dev_new_gui`. Never switch branches while agents work.
2. **Agents work in isolated worktrees:** Each agent works in `.worktrees/issue-XXXX/` with its own branch. No cross-contamination.
3. **Batch size: 3 agents max** to avoid API rate limiting (529 errors). Wait for completion between batches.
4. **Agents commit locally only** — they do NOT push. Main session handles all pushes (SSH credentials always available).
5. **Monitor for failures:** After each batch, `/team-implement` auto-detects failures:
   - API 529 → wait 60s, retry
   - Merge conflicts → auto-rebase, retry
   - Already resolved → skip
   - Agent crash → retry up to 3 times
   - Only escalate unresolvable issues with manual instructions

---

## PR Review & Merge Checklist

After agents complete:

1. **Enumerate ALL open PRs:** `gh pr list --state open` to count expected PRs before starting review.
2. **Track in checklist:** One line per PR to verify nothing is skipped.
3. **Review each PR:**
   - Type checking: `npm run type-check` (frontend) / `python -m mypy` (backend)
   - Syntax: `npm run lint` / `python -m black --check`
   - Imports: `python -c 'import <module>'` for each modified file
   - Call sites: Grep for removed/renamed functions to verify no broken callers
4. **Merge:** Merge each PR to `Dev_new_gui`
5. **Verify count:** After all merges, PR count should be 0 (all merged)

---

## Post-Merge Gap Audit

After ALL PRs merged:

1. **Import check:** For every modified Python file, `python -c 'import <module>'` — catch broken imports.
2. **Call-site validation:** For every function REMOVED or RENAMED, grep for all callers. Verify none are broken.
3. **Orphaned parameters:** Check function signatures don't leave callers passing wrong arguments.
4. **File parsing:** `python -m py_compile` for backend, `npx tsc --noEmit` for frontend.
5. **File discovery issues:** For ALL gaps found, file GitHub issues. DO NOT fix inline. Keep audit trail clean.

**Why:** Bugs like removed `_init_redis()` breaking 9+ call sites get caught here before reaching production.

---

## Pre-Implementation Validation (NEW)

**Before spawning agents for issue implementation, verify:**

1. **Main session branch check:** `git branch --show-current` — must be `Dev_new_gui`
2. **Main session clean:** `git status --porcelain` — no uncommitted changes
3. **Issue not already resolved:** Check if `#<issue>` is already in `origin/Dev_new_gui` commits
4. **No stale worktrees:** Clean up any existing `.worktrees/issue-<number>/` directories
5. **Issue preconditions:** Verify issue dependencies are resolved before starting work

**Why:** Prevents wasted agent cycles on already-fixed issues, ensures clean isolation, catches branch violations early.

---

## Sub-Agent Permission Enforcement (NEW)

**When spawning agents for parallel work:**

1. **Verify permissions upfront:** Ensure agents have Bash, Read, Edit, Grep tool access
2. **Document in agent prompt:** "If you lose Bash permissions, STOP and report — don't retry"
3. **Monitor for permission failures:** After each batch, check for "Permission denied" errors
4. **Main session as fallback:** If agent fails on git push, main session handles it (main session has full credentials)

**Key principle:** Agents commit locally only. Main session (with SSH/credentials) always handles pushes.

---

## Mandatory Post-Merge Gap Audit (NEW)

**After merging all PRs in a batch:**

1. **Run `/dead-code-audit`** to discover new gaps introduced by merged code
2. **File discovery issues** for any new dead/orphaned code found
3. **Do NOT fix gaps inline** — keep audit trail clean by filing issues for later prioritization
4. **Track in GitHub** under `dead-code` and `not-wired` labels for batch cleanup

**Why:** Catches regressions (missing imports, orphaned functions, new dead code) immediately.

---

## Validation Gates Before Merging (NEW)

**Use `/pre-merge-validate <PR>` before merging any code:**

1. **Syntax + Imports:** Catches SyntaxError, ImportError
2. **Call-Site Impact:** Finds removed functions with live callers (prevents `_init_redis()` incidents)
3. **Function Signatures:** Detects signature changes with existing callers
4. **Targeted Tests:** Runs tests only for changed files (fast validation)
5. **Type Check:** Frontend TypeScript validation
6. **Linting:** Catches errors (not warnings)

**Integration:** `/team-implement` automatically validates before creating PRs.

---

## Headless / Automated Audit (NEW - Optional)

**For CI/CD integration, use Claude CLI headless mode:**

```bash
# Validate all open PRs before merge window
for pr in $(gh pr list --state open --limit 20 --json number -q '.[].number'); do
  /pre-merge-validate $pr || gh pr comment $pr -b "❌ Validation failed"
done

# Nightly codebase audit (cron: 0 23 * * *)
/dead-code-audit >> /var/log/codebase-audit.log
```

**Benefits:** Catch failures before human review, file discovery issues automatically, maintain codebase health continuously.

---

## Issue Closure Verification Gate (MANDATORY)

**NEVER close an issue without 100% verification. Issues remain OPEN until ALL acceptance criteria are proven met.**

### Before Closing an Issue

1. **Read the issue description fully** — identify ALL acceptance criteria (stated and implicit)
2. **Find the merged commit(s)** — use `git log --all --grep="<issue-number>"` to locate implementation commit(s)
3. **Verify each acceptance criterion**
   - Is the feature/fix actually implemented? (check diff)
   - Does it work correctly? (test output, curl test, UI verification)
   - Are all edge cases handled? (review code, check error handling)
   - Are tests passing? (run test suite for changed modules)
   - Is documentation updated if needed? (check docs/)
4. **Document the proof**
   - Commit hash(es): `<hash>: <commit message>`
   - Acceptance criteria met: `✅ Criterion 1`, `✅ Criterion 2`, etc.
   - Evidence: test output, curl response, screenshot, or CI check reference
5. **Close with proof comment**

```bash
gh api repos/mrveiss/AutoBot-AI/issues/<number>/comments -f body="✅ Closed with proof of implementation

**Commit(s):** <hash1> (<msg1>), <hash2> (<msg2>)

**Acceptance Criteria Met:**
- ✅ Criterion 1 — evidence here
- ✅ Criterion 2 — evidence here
- ✅ Criterion 3 — evidence here"
```

### If ANY Criterion Not Met

- **DO NOT close the issue** — leave it OPEN
- Comment on the issue with what's missing: `⚠️ Criterion X not met: <reason>`
- File a follow-up issue if needed: `discovery: <gap found>`

### Examples of Incomplete Closure (AVOID)

❌ "Fixed in PR #1234" (no proof of acceptance criteria)  
❌ Closing based on PR status alone (PR merged ≠ issue resolved)  
❌ No test output or verification (feature might be broken)  
❌ Missing acceptance criteria check (incomplete implementation)

### Examples of Complete Closure (GOOD)

✅ Commit hash + all criteria verified + test output attached  
✅ Feature tested end-to-end in dev environment  
✅ All edge cases documented as handled  
✅ Follow-up issues filed for any gaps found
