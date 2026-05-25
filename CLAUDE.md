# AutoBot Development Instructions

> **Full rules:** [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) — read when starting a new task
> **Full workflow:** [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) — read when needed
> **Reference (IPs, playbooks):** [`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)
> **Architecture exceptions:** [`docs/developer/ARCHITECTURE_EXCEPTIONS.md`](docs/developer/ARCHITECTURE_EXCEPTIONS.md)
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

**Cache TTL overrides:** Hard-coded Redis TTLs are bugs (#6743). For tunable surfaces use a module-level constant resolved from an env var with a logged-fallback default — e.g. `AUTOBOT_CHAT_SESSION_CACHE_TTL` → `chat_history.cache._CHAT_SESSION_CACHE_TTL` (24h default). See [`autobot-backend/chat_history/cache.py`](autobot-backend/chat_history/cache.py) for the canonical resolver pattern.

**LEDGER vs EXECUTOR (Issue #7380):** Coordination tools (workflow_plan, agent_register, memory_store, swarm_init) return *records* and complete instantly—they do NOT execute deliverables. After any coordination call, IMMEDIATELY continue with actual work using your execution tools (file I/O, shell commands, code generation). Do NOT wait for the coordinator to "finish" (it already did). The rule is injected into all agent system prompts automatically via `LEDGER_VS_EXECUTOR_RULE` constant from `autobot_shared/prompt_rules.py`. This is critical for preventing agents from waiting for non-existent "executor" processes. See the constant definition for full semantics.

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
2. **Verify Bash is approved:** Main session must have Bash permission approved — sub-agents inherit from parent. If Bash requires a prompt, approve it once before spawning any agents.
3. **Create worktrees correctly:** Each issue gets `.worktrees/issue-XXXX/` with dedicated branch. NO shared branches between worktrees.
4. **Check git status:** `git status` — **if any files are dirty, commit or stash them before spawning subagents.** Uncommitted edits are silently discarded when a subagent commits and upstream Dev_new_gui is merged (#4969).
5. **Verify issue isn't resolved:** Check if issue is already closed or if `Dev_new_gui` already has the fix via `git log origin/Dev_new_gui --oneline --grep="#XXXX"`.
6. **Confirm approach:** For architectural decisions, state in 1-2 sentences and wait for confirmation.

**Critical:** If you accidentally switched to a feature branch during parallel work, immediately switch back to `Dev_new_gui`. You may have broken active worktrees.

---

## Branch Safety (MANDATORY)

**Never run these operations without explicit user confirmation:**
- `git reset --hard` — discards uncommitted work permanently
- `git push --force` / `git push -f` — rewrites remote history
- `git branch -D` / deleting remote branches — permanent unless reflog exists
- `git clean -fd` / mass file deletion — unrecoverable
- `git cherry-pick` across divergent histories — high conflict risk
- Any operation touching `main` or `master` directly

**Before any bulk git operation:**
1. Run `git status` and `git diff --stat` — confirm exactly what will be affected
2. State the operation and its scope in one sentence to the user before executing
3. For branch deletions: verify the branch content is merged (`git branch -r --merged origin/Dev_new_gui`) before deleting
4. For file deletions: `grep -r` to confirm nothing references the files first

**If something goes wrong:** Stop immediately. Do not attempt recovery with more destructive commands. Report current state to user and wait for instructions.

**Why:** In past sessions, Claude staged 5,371 files for deletion in a worktree, nearly reset `main` during a cherry-pick with 30+ conflicts, and committed fixes to wrong branches. These incidents required manual recovery.

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

## Batch Execution Default

When the user says "implement all X-labeled issues", "fix all Y bugs", or "run `/batch-implement` on Z" — **launch immediately without asking for scope clarification.** The pattern is well-established.

Default behavior:
- Batch size: 3 agents max per round (API rate limit)
- All issues get their own worktree: `.worktrees/issue-XXXX/`
- Main session stays on `Dev_new_gui` — never switches
- Agents commit locally; main session pushes and creates PRs
- After each batch: review, merge, file discovery issues, then next batch

**Do NOT ask:** "Which issues should I include?", "Should I do them in parallel?", "How many at a time?" — just run the pre-flight checklist and start.

**Only stop to ask** if: a specific issue has unresolved dependencies, an architectural decision is needed, or the pre-flight checklist finds a problem (dirty branch, unresolved PRs, etc.).

**Domain schema files (resolved #5799):** `schemas_common.py` now has only 5 cross-domain classes. Domain schemas live in `schemas_terminal.py`, `schemas_analytics.py`, `schemas_knowledge.py`, `schemas_agent.py`, `schemas_system.py`, `schemas_workflows.py`, `schemas_code.py`. New response schemas go in the matching domain file — parallel batches targeting different domain files can now run concurrently without conflicts.

---

## Code Review Agent Requirements (MANDATORY)

**Before dispatching any parallel review agents:**

Every finder and verifier agent prompt MUST contain all three of the following — refuse to dispatch if any is missing:

1. **Exact file list** from the PR diff:
   ```bash
   gh pr diff $PR_NUMBER --name-only > /tmp/review-files.txt
   cat /tmp/review-files.txt
   ```
   Pass the full output as a literal list in the agent prompt.

2. **Scope restriction:** Include verbatim: *"Use Read on these paths only. Do NOT Glob for other files in the repo."*

3. **Role description:** State the agent's specific angle (e.g., "You are a security reviewer. Focus on: authz bypasses, IDOR, injection, secrets.") AND its output format (structured JSON with file, line, severity, evidence).

**Why:** Without the file list, agents verify against stale repo files instead of PR diff. Without scope restriction, agents Glob unrelated files and produce noise. Both failures were observed in production reviews.

---

## Parallel Agents Strategy

When spawning multiple agents for batch work with `/batch-implement`:

1. **Verify main session isolation:** Main session MUST stay on `Dev_new_gui`. Never switch branches while agents work.
2. **Agents work in isolated worktrees:** Each agent works in `.worktrees/issue-XXXX/` with its own branch. No cross-contamination.
3. **Batch size: 3 agents max** to avoid API rate limiting (529 errors). Wait for completion between batches.
4. **Agents commit locally only** — they do NOT push. Main session handles all pushes (SSH credentials always available).
5. **Monitor for failures:** After each batch, `/batch-implement` auto-detects failures:
   - API 529 → wait 60s, retry
   - Merge conflicts → auto-rebase, retry
   - Already resolved → skip
   - Agent crash → retry up to 3 times
   - Only escalate unresolvable issues with manual instructions

---

## PR Review & Merge Checklist

After agents complete:

0. **Gate 0 — Squash-duplicate check:** For each PR branch, run the squash-duplicate detection command (see `docs/developer/CLAUDE_WORKFLOW.md` "Gate 0") to verify no commits are already in `Dev_new_gui`. If all commits are duplicates, close the issue without merging.
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
2. **Main session clean:** `git status --porcelain` — **if any files are dirty, commit or stash them before spawning agents.** Uncommitted edits are silently discarded when a subagent commits and upstream is merged (#4969).
3. **Issue not already resolved:** Check if `#<issue>` is already in `origin/Dev_new_gui` commits
4. **No stale worktrees:** Clean up any existing `.worktrees/issue-<number>/` directories
5. **Issue preconditions:** Verify issue dependencies are resolved before starting work

**Why:** Prevents wasted agent cycles on already-fixed issues, ensures clean isolation, catches branch violations early.

---

## Sub-Agent Permission Enforcement (CRITICAL)

Sub-agents without Bash permissions cannot complete git operations and will stall mid-batch, forcing manual intervention. This is the #1 cause of batch failures.

**Required tools for every implementation agent:** `Bash, Read, Edit, Write, Grep, Glob`

**Every agent prompt MUST include this line:**
> "You have Bash, Read, Edit, Write, Grep, and Glob permissions. If you lose Bash permissions at any point, STOP immediately and report — do not retry or work around it."

**Pre-launch check:** Before spawning any agent batch, confirm the main session has Bash approved. Sub-agents inherit from the parent session — if Bash requires approval in the main session, it will also require approval in each sub-agent, blocking all parallel work.

**Main session as fallback:** Agents commit locally only — they do NOT push. Main session handles all git push and `gh pr create` operations (SSH credentials always available in main session).

**On permission failure:** Do not retry the same agent. Report to user with: which agent failed, at which step, and what was left incomplete. Main session then completes the git operation manually.

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

0. **Squash-Duplicate Detection:** Run Gate 0 (see `docs/developer/CLAUDE_WORKFLOW.md`) to detect commits already squash-merged to `Dev_new_gui` — avoids wasted merge work on already-landed changes.
1. **Syntax + Imports:** Catches SyntaxError, ImportError
2. **Call-Site Impact:** Finds removed functions with live callers (prevents `_init_redis()` incidents)
3. **Function Signatures:** Detects signature changes with existing callers
4. **Targeted Tests:** Runs tests only for changed files (fast validation)
5. **Type Check:** Frontend TypeScript validation
6. **Linting:** Catches errors (not warnings)

**Integration:** `/batch-implement` automatically validates before creating PRs.

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
   - **Integration check (#6836 gate):** for every NEW module added by this issue, at least one production caller must import it. Run the unified wiring check:

     ```bash
     ./pipeline-scripts/check-new-module-callers.sh
     ```

     The script exits 0 if all new modules have callers, 1 if any have zero callers. **Zero callers ⇒ closure blocked**, even if tests pass — see #6836 for the orchestration audit that proved this gap (3,906 LOC of completed-but-unwired features whose trackers had been closed prematurely).
   - **Deliberate-deferral override:** if a new module is genuinely infrastructure-only (Protocol, scaffold) and has no caller *by design*, file a follow-up wire-in issue *first*, then re-run with:

     ```bash
     echo "#NNNN" >> .wiring-deferral.txt
     ./pipeline-scripts/check-new-module-callers.sh --allow-deferral .wiring-deferral.txt
     ```

     Then document in the closure comment: `### Wire-in deferred to #NNNN`.
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

### Discovery Issues (File During Every Task)

While implementing, if you notice **any** bug, inconsistency, dead code, missing test, hardcoded value, or tech debt that is NOT part of the current issue — file a GitHub issue for it immediately. Do not fix it inline, do not add a TODO comment, do not ignore it.

```bash
gh issue create --title "discovery(<area>): <what you found>" --body "..." --label "tech-debt"
```

**Before closing any issue**, confirm: did I file a GitHub issue for every gap I noticed during implementation? If not, file them now. This is mandatory — not optional.

**Why:** Gaps noticed inline and not filed are permanently lost. Discovery issues filed during implementation are the primary source of the issue backlog and prevent regressions from accumulating silently.

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
