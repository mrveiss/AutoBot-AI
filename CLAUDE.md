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
- **Worktrees:** No nesting. Manual creation for PRs (not `isolation: "worktree"`). Clean up after issue closure.
- **Agents:** Prefer direct implementation. Reserve subagents for research/exploration. Subagents can't acquire Bash permission.
- **Deployment:** All via Ansible playbooks on SLM Manager (.19). Never manual SSH changes.
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
