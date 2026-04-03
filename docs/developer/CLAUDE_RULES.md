# AutoBot Core Rules (Detail Reference)

> This file contains the full text of the 6 core rules. CLAUDE.md summarizes them;
> agents and sessions should read this file only when they need the complete policy.

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

> Violation: Writing a utility that already exists in `autobot_shared/`, or starting implementation without checking for an existing PR.

---

## Rule 2: Reuse Existing Code

**Always prefer existing code over new code:**

- Import and call existing utilities, helpers, and services
- Extend existing classes/functions rather than duplicating logic
- Use `autobot_shared/` utilities before writing custom implementations
- If similar code exists elsewhere, refactor to share it — never copy-paste

**Redis Client — always use canonical utility:**

```python
from autobot_shared.redis_client import get_redis_client
redis_client = get_redis_client(async_client=False, database="main")
# NEVER: redis.Redis(host="<database-ip>", ...)
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

Pre-commit hook enforces this. Guide: [`HARDCODING_PREVENTION.md`](HARDCODING_PREVENTION.md)

**Network Configuration — never hardcode IPs:**

Always check existing config files for correct network ranges. Use environment variables or SSOT config.

> Violation: Writing a new Redis helper when `autobot_shared.redis_client.get_redis_client` already exists, or hardcoding `<database-ip>`.

---

## Rule 3: Standardize for Reuse

**Write code that others can reuse:**

- Place shared logic in `autobot_shared/` or the appropriate shared module
- Match existing naming, signatures, and patterns in the codebase
- Generalize implementations when the cost is low (no over-engineering)

**Function Length:**

| Lines | Action |
|-------|--------|
| ≤30 | Ideal |
| 31–50 | Consider refactoring |
| 51–65 | Must refactor before merge |
| >65 | Immediate refactoring required |

Use **Extract Method** pattern: create `_helper_function()` with docstring referencing parent issue.

**File Naming — FORBIDDEN suffixes:** `_fix`, `_v2`, `_optimized`, `_new`, `_temp`, `_backup`, `_old`, date suffixes.

**Code Ownership:** `mrveiss` is the SOLE OWNER and AUTHOR of ALL AutoBot code.

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

**UTF-8 Encoding:** Always use `encoding='utf-8'` explicitly.

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

**Simplicity First — always prefer the simplest approach:**

- When the user asks to remove/fix something, do NOT add extra validation or defensive code unless requested
- If the scope is unclear, ASK rather than assuming a more complex approach
- Solve the stated problem — don't over-engineer for hypothetical edge cases

**Architecture Confirmation — before implementing any ambiguous task, state:**
1. **Approach:** What method/pattern you'll use
2. **Assumptions:** What you're assuming about architecture, startup, deployment
3. **Scope:** What will change and what will stay the same

Wait for user confirmation before writing code.

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
7. Worktree removed (if one was created)
8. Feature branch deleted (local + remote)

**Pre-commit & Linting:**

- Maximum line length: 120 characters (enforced by flake8/ruff)
- After ANY commit attempt, verify changes were actually committed
- Never mix unrelated staged files — stage and commit in focused batches
- Bulk operations: commit in batches of 10–15 files max
- **NEVER** use `git commit --no-verify`

**Bulk File Changes:**

- Apply changes in batches of **10–20 files at a time**
- Test on **2–3 representative files first** before bulk operations across 50+ files
- If a bulk fix script produces syntax errors: stop, fix the script, re-test

**Pre-commit Stash Bypass (Issue #2512, #1503):**

The pre-commit wrapper (`scripts/hooks/pre-commit-branch-guard-wrapper`) runs `pre-commit run --files <staged>` instead of calling the framework hook directly, eliminating stash push/pop issues.

**Deployment Verification Checklist — after deploying to ANY remote server:**

1. No .env override conflicts
2. Correct Python interpreter (Python 3.12 deadsnakes PPA venv)
3. Database migrations current
4. Service actually restarted
5. Endpoints responding
6. No errors in recent logs

> Violation: Saying "the bug is fixed" after editing a file without running the code.

---

## Rule 6: Report Every Discovered Problem

**"It was already there" is never a reason to ignore a problem.**

Every bug, inconsistency, security issue, hardcoded value, or tech debt found must be reported:

- Create a GitHub issue immediately with description, severity, and location
- Report to the user and ask for direction: fix now, fix after current task, or defer

**Classification:**

Fix immediately WITHOUT asking:
- Security vulnerability in code you're modifying
- Data corruption risk, syntax error breaking tests, import error blocking changes

Create issue + ASK before fixing:
- Performance problem, code smell, missing documentation, refactoring opportunity

Create issue + DEFER (don't ask):
- Minor style issues, optimization opportunities, unrelated bugs

**One Issue Per Session Rule:**
When an issue is complete, wait for explicit user instruction before starting new work.

> Violation: Noticing a broken error handler and not creating a GitHub issue because "it's not my task."
