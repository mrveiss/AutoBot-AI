# AutoBot Development Instructions

> **Reference material** (IPs, playbooks, commands): [`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)
> **Status updates:** [`docs/system-state.md`](docs/system-state.md)

---

## Quick Reference

**Every task must:**

1. **Link to GitHub Issue** — ALL work in https://github.com/mrveiss/AutoBot-AI (MANDATORY)
2. **Search Memory MCP** first: `mcp__memory__search_nodes`
3. **Break down into subtasks** — Add as checklist in GitHub issue
4. **Use specialized agents** for complex tasks
5. **Code review is mandatory** — use `code-reviewer` agent
6. **Update GitHub Issue** throughout work with progress comments
7. **Complete properly** — All code committed, criteria met, issue closed with summary
8. **Store in Memory MCP** at session end

**Before proceeding, verify:**

- Work tied to GitHub issue? If NO: Create/link first
- Subtasks added to issue as checklist? If NO: Add now
- Memory MCP searched? If NO: Search now
- Complex tasks delegated to agents? If NO: Delegate
- Fixing root cause (not workaround)? If NO: STOP
- Integration needs both frontend AND backend? If YES: Plan BOTH

**If ANY fails then STOP and correct immediately**

---

## CORE RULES (MANDATORY — EVERY AGENT, EVERY TOOL)

These six rules override convenience, speed, and assumptions. No exceptions.

---

## Rule 1: Check Before Writing

**Before writing a single line of code or documentation:**

- Search for existing implementations: `grep`/`glob` or `git log --oneline --grep="<topic>"`
- Check existing docs: `ls docs/`, `gh issue list`, recent commits
- Review related files in the same module/directory
- Search Memory MCP: `mcp__memory__search_nodes` for prior decisions
- Only after confirming nothing exists should you write new code or docs

**Before implementing anything, verify:**
1. Is the issue still open? `gh issue view <number>`
2. Are there any existing PRs or branches? `gh pr list | grep <issue>`
3. Any recent commits? `git log --oneline -20 --grep="<keywords>"`
4. Is there already code that partially implements this? Quick grep/glob search

If you find existing work, USE IT — don't reimplement from scratch.

> Violation: Writing a utility that already exists in `autobot-shared/`, or starting implementation without checking for an existing PR.

---

## Rule 2: Reuse Existing Code

**Always prefer existing code over new code:**

- Import and call existing utilities, helpers, and services
- Extend existing classes/functions rather than duplicating logic
- Use `autobot-shared/` utilities before writing custom implementations
- If similar code exists elsewhere, refactor to share it — never copy-paste

**Redis Client — always use canonical utility:**

```python
from autobot_shared.redis_client import get_redis_client
redis_client = get_redis_client(async_client=False, database="main")
# NEVER: redis.Redis(host="172.16.168.23", ...)
```

Databases: `main`, `knowledge`, `prompts`, `analytics`

**Hardcoding Prevention — always use SSOT config:**

```python
from autobot_shared.ssot_config import config
redis_host = config.redis.host
```

```typescript
import { getBackendUrl } from '@/config/ssot-config'
```

Pre-commit hook enforces this. Guide: [`docs/developer/HARDCODING_PREVENTION.md`](docs/developer/HARDCODING_PREVENTION.md)

**Network Configuration — never hardcode IPs:**

Always check existing config files for correct network ranges. Use environment variables or SSOT config. Flag any hardcoded IPs in legacy code for removal.

> Violation: Writing a new Redis helper when `autobot_shared.redis_client.get_redis_client` already exists, or hardcoding `172.16.168.23`.

---

## Rule 3: Standardize for Reuse

**Write code that others can reuse:**

- Place shared logic in `autobot-shared/` or the appropriate shared module
- Match existing naming, signatures, and patterns in the codebase
- Generalize implementations when the cost is low (no over-engineering)
- Avoid one-off implementations that can't be called from elsewhere

**Function Length:**

| Lines | Action |
|-------|--------|
| ≤30 | Ideal |
| 31–50 | Consider refactoring |
| 51–65 | Must refactor before merge |
| >65 | Immediate refactoring required |

Use **Extract Method** pattern: create `_helper_function()` with docstring referencing parent issue.

**File Naming — FORBIDDEN suffixes:** `_fix`, `_v2`, `_optimized`, `_new`, `_temp`, `_backup`, `_old`, date suffixes. Version control handles versions.

**Consolidation:** When merging duplicate code — preserve ALL features + choose BEST implementation. Never drop features for convenience.

**Code Ownership:** `mrveiss` is the SOLE OWNER and AUTHOR of ALL AutoBot code.

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

**UTF-8 Encoding:** Always use `encoding='utf-8'` explicitly. Guide: [`docs/developer/UTF8_ENFORCEMENT.md`](docs/developer/UTF8_ENFORCEMENT.md)

**Logging:**

```python
# Backend
import logging
logger = logging.getLogger(__name__)
logger.info("Message: %s", data)
```

```typescript
// Frontend
import { createLogger } from '@/utils/debugUtils'
const logger = createLogger('ComponentName')
```

No `console.*` or `print()` — pre-commit blocks these.

> Violation: Hardcoding a value that belongs in SSOT config, or writing a private helper that duplicates a public one.

---

## Rule 4: Clarify Requirements Before Starting

**Before touching any code, ensure requirements are complete:**

- Read the full issue/PRD and identify every gap, ambiguity, or missing edge case
- Ask all clarifying questions UP FRONT in a single pass — not mid-implementation
- Do not start until you can describe the complete expected end result in concrete terms

**Questions to ask before starting:**
- What is the exact expected input and output?
- Are there edge cases or error states that must be handled?
- Are there UI/UX, performance, or security constraints not stated?
- Does this touch other systems that need coordinating changes?

**Simplicity First — always prefer the simplest approach:**

- When the user asks to remove/fix something, do NOT add extra validation or defensive code unless requested
- If the scope is unclear, ASK rather than assuming a more complex approach
- Solve the stated problem — don't over-engineer for hypothetical edge cases

**Architecture Confirmation — before implementing any ambiguous task, state:**
1. **Approach:** What method/pattern you'll use
2. **Assumptions:** What you're assuming about architecture, startup, deployment
3. **Scope:** What will change and what will stay the same

Wait for user confirmation before writing code. Do NOT assume `systemd` vs `docker-compose`, Ansible vs manual, new mode vs extending existing.

**No Temporary Fixes (ZERO TOLERANCE):**
- No quick fixes, workarounds, or disabling functionality
- No hardcoding to bypass issues, try/catch hiding errors
- No "TODO: fix later" comments
- Identify root problem → fix underlying issue → verify → remove workarounds

> Violation: Starting implementation from a vague issue, or creating a "partition mode" when the existing mode just needs extension.

---

## Rule 5: Verify Before Reporting Complete

**Before claiming any work is done, show evidence it works:**

- Run the relevant test, lint check, curl, or build command and include the output
- Never say "done", "fixed", or "complete" without proof
- If the change touches multiple layers (backend + frontend, multiple nodes), verify each one

**Issue is complete ONLY when:**

1. All code committed with issue refs
2. All acceptance criteria verified
3. Tests passing
4. Code reviewed
5. Closing summary added to issue
6. Issue status = closed

**Pre-commit & Linting:**

- Maximum line length: 100 characters (enforced by flake8/ruff)
- After ANY commit attempt, verify changes were actually committed:
  ```bash
  git log -1 --stat
  git diff
  ```
- If hooks revert edits, fix the underlying issue (don't retry blindly)
- Never mix unrelated staged files — stage and commit in focused batches
- Bulk operations: commit in batches of 10–15 files max
- **NEVER** use `git commit --no-verify`

**Post-commit verification:**

```bash
git log --oneline -1        # Verify commit message and branch
git diff --staged           # Ensure nothing unexpectedly left staged
```

**Deployment Verification Checklist — after deploying to ANY remote server:**

1. **No .env override conflicts:** `grep -E "(HOST|PORT|PASSWORD)" /path/to/.env`
2. **Correct Python interpreter:** `which python3` — Main: Python 3.12 conda env; SLM/fleet: Python 3.10 venv `/opt/autobot/venv`
3. **Database migrations current:** `cd /opt/autobot && source venv/bin/activate && alembic current`
4. **Service actually restarted:** `sudo systemctl status autobot-backend --no-pager && journalctl -u autobot-backend -n 50 --no-pager`
5. **Endpoints responding:** `curl -s http://localhost:8001/api/health | jq`
6. **No errors in recent logs:** `journalctl -u autobot-backend --since "30 seconds ago" | grep -i error`

Only proceed to next task if ALL six checks pass.

> Violation: Saying "the bug is fixed" after editing a file without running the code.

---

## Rule 6: Report Every Discovered Problem

**"It was already there" is never a reason to ignore a problem.**

Every bug, inconsistency, security issue, hardcoded value, or tech debt found — regardless of current task — must be reported:

- Create a GitHub issue immediately with description, severity, and location
- Report to the user and ask for direction: fix now, fix after current task, or defer
- Do not assume someone else knows about it

**Discovered Problems Policy:**

If you discover a NEW problem (not in GitHub):

```bash
gh issue create --title "Bug: <description>" --body "## Problem
<what's wrong>

## Discovered During
Working on #<original-issue>

## Impact
<severity: critical/high/medium/low>"
```

Then ask:
```
Created issue #<new-number> for <problem>.
Should I: a) Fix now  b) Finish current issue first  c) Leave for later
```

If you discover a problem ALREADY in GitHub:
- ❌ DO NOT auto-start working on it
- ✅ Note it and link if related

If you discover technical debt:
- ❌ DO NOT refactor without permission
- ✅ Create issue: "Refactor: <opportunity>"
- ✅ Note: "Created #<number> for future improvement"

**Classification:**

Fix immediately WITHOUT asking:
- Security vulnerability in code you're modifying
- Data corruption risk
- Syntax error that breaks tests
- Import error blocking your changes

Create issue + ASK before fixing:
- Performance problem, code smell, missing documentation, refactoring opportunity

Create issue + DEFER (don't ask):
- Minor style issues, optimization opportunities, unrelated bugs

**One Issue Per Session Rule:**

When an issue is complete:
- ✅ Report completion with summary
- ✅ Verify issue is closed: `gh issue view <number>`
- ❌ DO NOT auto-start other existing issues
- ❌ DO NOT suggest working on related issues without asking
- ❌ DO NOT scan for more work

**Wait for explicit user instruction** before starting new work.

**Multi-Session Coordination:**

Each session stays in its issue scope. If Session A discovers a bug in Session B's area → create issue, let user coordinate.

> Violation: Noticing a broken error handler and not creating a GitHub issue because "it's not my task."

---

## Operational Standards

### General Workflow

**Implementation First:**
- Prefer direct implementation over extended brainstorming/design phases
- When the user says "work on issue #X", brief plan (max 10 lines) then implement
- Do NOT invoke brainstorming skills when direct answers are needed

**Implementation Approach:**
- For large features (backend + frontend), complete and commit backend fully first
- Commit completed work incrementally — don't wait until everything is done
- After writing each file, verify it exists on disk before moving on
- When a fix applies to a component on multiple nodes: check all nodes, fix all of them
- If approaching context limit: stop at phase boundary, commit, add GitHub comment with next steps

### Git Workflow

**Branch Strategy:**
- Always target `Dev_new_gui` for PRs and merges unless explicitly told otherwise
- After completing work: delete remote feature branches and prune stale branches

**Pre-Flight Checks (before ANY code changes):**
1. Verify current branch: `git branch --show-current`
2. Check for uncommitted work: `git status`
3. Check for stashes: `git stash list` — if present, ask user how to handle
4. Verify target branch: `git fetch origin Dev_new_gui && git log --oneline origin/Dev_new_gui -3`

### Memory Hygiene

**Rules for `~/.claude/projects/.../memory/MEMORY.md`:**
- Target <150 lines. Hard limit 200 (truncated after).
- One line per closed issue: `#NNN: phrase. Commit abc1234.`
- Archive when Recent Completed exceeds 30 items → `completed-history.md`
- CLAUDE.md owns stable patterns. MEMORY.md owns recent state only.

**End-of-session ritual:**
1. Close any issues? → Move to Recent Completed (1 line each)
2. Any gotcha resolved? → Delete it
3. Recent Completed >30? → Archive oldest batch
4. MEMORY.md >150 lines? → Trim with `/memory-cleanup`

### Multi-Agent Safety

**Git Operations:**
- Do NOT create/apply/drop `git stash` unless explicitly requested
- Do NOT switch branches unless explicitly requested
- When pushing, use `git pull --rebase` (never discard others' work)

**Scoped Commits:**
- "commit" = YOUR changes only
- "commit all" = everything in grouped chunks

**File Handling:** When you see unrecognized files, keep going. Focus on your changes.

### Edit Strategy

- Prefer incremental `Edit` over full file `Write` for files longer than 50 lines
- Never rewrite entire files when only a few sections need changes
- `Write`: new files, files under 50 lines
- `Edit`: existing files over 50 lines, targeted changes

### Agent Delegation

**Prefer direct implementation over subagents** — reserve agents for exploration/research of unfamiliar areas.

**Before spawning parallel subagents:**
1. Verify worktree: `ls -la ../worktrees/ 2>/dev/null || mkdir -p ../worktrees/`
2. Test one agent first before dispatching many
3. If agent hangs >5 minutes, fail fast
4. Fallback plan: switch to sequential branch-based implementation

**If subagent fails:** Switch to direct implementation immediately. Do NOT retry.

**Subagent success pattern:** Pre-flight → test one agent → dispatch parallel → monitor → fallback to sequential if needed.

**R-P-I Workflow** (ONLY for): `code-skeptic` (risk analysis), `systems-architect` (architecture design)

**Available Agents:**
- Implementation: `senior-backend-engineer`, `frontend-engineer`, `database-engineer`, `devops-engineer`, `testing-engineer`, `code-reviewer` (MANDATORY), `documentation-engineer`
- Analysis: `code-skeptic`, `systems-architect`, `performance-engineer`, `security-auditor`, `ai-ml-engineer`
- Planning: `project-task-planner`, `project-manager`

### GitHub Workflow

**Commit format:** `<type>(scope): <description> (#issue-number)`

**Always close the issue after implementation:**
- Run `gh issue close <number>` and verify with `gh issue view <number>`
- Add closing comment summarizing what was done

**PR Workflow — Review Mode** (PR link only): read `gh pr view/diff`, do NOT switch branches or change code.

**PR Workflow — Landing Mode:**
1. Create integration branch from `main`
2. Bring in PR commits (prefer rebase)
3. Apply fixes, add changelog
4. Run full gate locally before committing
5. Commit with contributor attribution
6. Merge back to `main`

### Debugging Discipline

Form a hypothesis before running commands:
1. State: "I think X is caused by Y because Z"
2. List 3–4 specific commands that confirm or reject it
3. Run them in order
4. Update hypothesis before running more

### Error Handling

Auto-retry on transient errors (API 500, tool interruptions) up to 2 times before asking the user. Log: "Retrying (attempt 2/2)..."

---

## Reference

Lookup tables, IPs, playbooks, sync commands, quick commands:

→ **[`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)**
