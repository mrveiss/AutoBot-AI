# AutoBot Development Instructions

> **Status updates:** [`docs/system-state.md`](docs/system-state.md)

---

## WORKFLOW REQUIREMENTS (MANDATORY)

**Every Task Must:**

1. **Link to GitHub Issue** - ALL work in https://github.com/mrveiss/AutoBot-AI (MANDATORY)
2. **Search Memory MCP** first: `mcp__memory__search_nodes`
3. **Break down into subtasks** - Add as checklist in GitHub issue
4. **Use specialized agents** for complex tasks
5. **Code review is mandatory** - use `code-reviewer` agent
6. **Update GitHub Issue** throughout work with progress comments
7. **Complete properly** - All code committed, criteria met, issue closed with summary
8. **Store in Memory MCP** at session end

**Before proceeding, verify:**

- Work tied to GitHub issue? If NO: Create/link first
- Subtasks added to issue as checklist? If NO: Add now
- Memory MCP searched? If NO: Search now
- Complex tasks delegated to agents? If NO: Delegate
- Fixing root cause (not workaround)? If NO: STOP
- Integration needs both frontend AND backend? If YES: Plan BOTH

**Before marking complete:**

- ALL code committed with issue refs?
- ALL acceptance criteria verified?
- Closing summary added to issue?
- Issue closed?

**If ANY fails then STOP and correct immediately**

---

## GENERAL WORKFLOW

**Implementation First:**

- Prefer **direct implementation** over extended brainstorming/design phases unless the user explicitly asks for a design doc
- When the user says "work on issue #X", start with a brief plan (max 10 lines) then proceed to implementation
- Do NOT invoke brainstorming skills when direct answers are needed
- Skip lengthy design documents unless specifically requested

**Front-Load Verification:**

- Before implementing anything, verify:
  1. Is the issue still open? `gh issue view <number>`
  2. Are there any existing PRs or branches? `gh pr list | grep <issue>`
  3. Is there already code that partially implements this? Quick grep/glob search
- Show brief status summary before proceeding with implementation

**Implementation Approach:**

- For large features spanning backend + frontend, complete and commit backend fully before starting frontend
- When a session is getting long, commit completed work incrementally rather than waiting until everything is done
- If implementation has 10+ tasks, commit after each logical group (e.g., every 2-3 tasks)
- Incremental commits protect progress and simplify recovery if sessions need to end

---

## GIT WORKFLOW (MANDATORY)

**Branch Strategy:**

- Always target `Dev_new_gui` branch for PRs and merges unless explicitly told otherwise
- Before merging or integrating branches, verify the target branch is `Dev_new_gui`, not `main`
- After completing work, clean up: delete remote feature branches and prune stale branches

**Pre-Flight Checks (run BEFORE making ANY code changes):**

1. Verify current branch: `git branch --show-current`
2. Check for uncommitted work: `git status`
3. Check for stashes: `git stash list` - if present, ask user how to handle
4. Verify target merge branch exists and is up to date:
   ```bash
   git fetch origin Dev_new_gui
   git log --oneline origin/Dev_new_gui -3
   ```
5. Confirm the working branch is correct for this issue

**Post-Commit Verification:**

- After EVERY commit, immediately verify it landed correctly:
  ```bash
  git log --oneline -1        # Verify commit message and branch
  git diff --staged           # Ensure nothing unexpectedly left staged
  ```

**If anything looks wrong, STOP and notify user immediately**

---

## SESSION BOUNDARIES (MANDATORY)

### One Issue Per Session Rule

**When an issue is complete:**
- ✅ Report completion with summary
- ✅ Verify issue is closed: `gh issue view <number>`
- ❌ DO NOT auto-start other existing issues
- ❌ DO NOT suggest working on related issues without asking
- ❌ DO NOT scan for more work

**Wait for explicit user instruction** before starting new work.

### Discovered Problems Policy

**If you discover a NEW problem (not in GitHub):**

1. **Create GitHub issue immediately:**
```bash
gh issue create --title "Bug: <description>" --body "## Problem
<what's wrong>

## Discovered During
Working on #<original-issue>

## Impact
<severity: critical/high/medium/low>"
```

2. **Ask user if should fix now:**
```
Created issue #<new-number> for <problem>.
Should I:
a) Fix it now (will delay current work)
b) Finish current issue first, then fix
c) Leave for later
```

3. **If critical/blocking:** Recommend fixing immediately
4. **If minor:** Recommend deferring

**If you discover a problem ALREADY in GitHub:**
- ❌ DO NOT auto-start working on it
- ✅ Note it: "FYI: Issue #<number> also affects this area"
- ✅ Link it if related: Comment on original issue mentioning the connection

**If you discover technical debt / refactoring opportunity:**
- ❌ DO NOT refactor without permission
- ✅ Create issue: "Refactor: <opportunity>" with rationale
- ✅ Note: "Created #<number> for future improvement"

### Scope Examples

**✅ GOOD (fixes discovered bug):**
```
While implementing #100, discovered critical bug:
authentication bypass in user_login().

Created issue #150 for this security issue.

Recommend fixing NOW before continuing #100
(affects the code we're modifying). Proceed?
```

**✅ GOOD (defers non-critical issue):**
```
While implementing #100, noticed suboptimal
caching in get_user(). Created issue #151.

Deferring to stay focused on #100.
```

**❌ BAD (drifts to existing issue):**
```
Completed #100. I see issue #101 is related
and I could fix it quickly...
[starts working without permission]
```

**❌ BAD (fixes non-critical without asking):**
```
While implementing #100, noticed typo in docstring.
Let me fix that real quick...
[fixes without creating issue or asking]
```

### Critical vs Non-Critical Discovered Issues

**Fix immediately WITHOUT asking if:**
- Security vulnerability in code you're modifying
- Data corruption risk
- Syntax error that breaks tests
- Import error blocking your changes

**Create issue + ASK before fixing if:**
- Performance problem (not critical)
- Code smell / tech debt
- Missing documentation
- UI/UX improvement opportunity
- Refactoring opportunity

**Create issue + DEFER (don't ask) if:**
- Minor style issues
- Optimization opportunities
- "Nice to have" improvements
- Unrelated bugs in other areas

### Multi-Session Coordination

**If running parallel sessions on different issues:**
- Each session stays in its issue scope
- If Session A discovers bug in Session B's area → Create issue, let user coordinate
- Do NOT cross-contaminate: "I'll fix this while Session B works on that"

---

## MULTI-AGENT SAFETY (MANDATORY)

### Git Operations

- Do NOT create/apply/drop `git stash` entries unless explicitly requested
- Do NOT switch branches unless explicitly requested
- Do NOT modify `git worktree` checkouts unless explicitly requested
- When pushing, use `git pull --rebase` to integrate changes (never discard others' work)

### Scoped Commits

- When user says "commit", scope to YOUR changes only
- When user says "commit all", commit everything in grouped chunks
- Focus reports on your edits; avoid guard-rail disclaimers unless blocked

### File Handling

- When you see unrecognized files, keep going
- Focus on your changes and commit only those
- End with brief "other files present" note only if relevant

---

## CODE OWNERSHIP (MANDATORY - UNBREAKABLE)

**mrveiss** is the **SOLE OWNER and AUTHOR** of ALL AutoBot code. No exceptions.

```python
# File header template
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

---

## EDIT STRATEGY (MANDATORY)

**Incremental Edits Only:**

- Prefer incremental `Edit` operations over full file `Write` for files longer than 50 lines
- Never rewrite entire files when only a few sections need changes
- If an edit is interrupted/rejected, switch to smaller, targeted edits rather than retrying the same large change
- Large file rewrites are the #1 cause of user interruptions - avoid them

**When to Use Write vs Edit:**

- `Write`: New files, files under 50 lines, complete file generation
- `Edit`: Existing files over 50 lines, targeted changes, refactoring
- If unsure, default to `Edit` for existing files

---

## CRITICAL POLICIES

### No Temporary Fixes (ZERO TOLERANCE)

- No quick fixes, workarounds, disabling functionality
- No hardcoding to bypass issues, try/catch hiding errors
- No "TODO: fix later" comments
- YES: Identify root problem, fix underlying issue, verify, remove workarounds

### Function Length (50 lines or less)

| Lines | Action |
|-------|--------|
| 30 or less | Ideal |
| 31-50 | Consider refactoring |
| 51-65 | Must refactor before merge |
| More than 65 | Immediate refactoring required |

Use **Extract Method** pattern: Create `_helper_function()` with docstring referencing parent issue.

### File Naming

**FORBIDDEN**: `_fix`, `_v2`, `_optimized`, `_new`, `_temp`, `_backup`, `_old`, date suffixes

Use permanent, descriptive names. Version control handles versions.

### Consolidation Rules

When merging duplicate code: **Preserve ALL features** + **Choose BEST implementation**. Never drop features for convenience.

### Pre-commit & Linting (Critical)

**Pre-commit hooks may revert your edits:**

- Be aware that pre-commit hooks (linters, formatters) run on every commit and may revert or modify staged changes
- After ANY commit attempt, verify changes were actually committed:
  ```bash
  git log -1 --stat  # Check what was committed
  git diff           # Verify no uncommitted changes remain
  ```

- If hooks revert edits, fix the underlying issue (don't retry blindly)
- Common hook failures: line length (E501), trailing whitespace, hardcoded values
- Always run `git diff --staged` after staging to verify changes survive hook processing
- If hooks keep reverting changes, investigate the hook config before retrying - do not blindly retry commits
- Never mix unrelated staged files; stage and commit in focused batches

**Line length enforcement:**

- Maximum line length: 100 characters (enforced by flake8)
- Hook will reject commits with E501 violations
- Use the PostToolUse hook (auto-lint after edits) to catch before commit

**Bulk operations (linting, imports, refactoring):**

- Commit in small batches (10-15 files max)
- Verify each batch passes hooks before continuing
- Never attempt "fix all violations" in one commit
- Pattern: Fix → Verify → Commit → Repeat

**If pre-commit hook fails:**

```bash
# See what failed
git status

# Fix the specific issue (don't skip hooks with --no-verify)
# Re-stage and re-commit

# Verify success
git log -1 --stat
```

**Red flags (STOP if you see these):**
- Attempting `git commit --no-verify` (bypassing hooks)
- Bulk commit of 50+ files without verification
- Re-committing same files repeatedly (hook is rejecting them)
- "I'll fix the linting in a follow-up commit" (fix it NOW)

---

## GITHUB ISSUE TRACKING

**Repository:** https://github.com/mrveiss/AutoBot-AI

**Commit format:** `<type>(scope): <description> (#issue-number)`

**Issue is complete ONLY when:**

1. All code committed with issue refs
2. All acceptance criteria verified
3. Tests passing
4. Code reviewed
5. Closing summary added
6. Issue status = closed

### GitHub Workflow (MANDATORY)

**Always close the issue on GitHub after implementation is complete:**

- Do NOT mark work as done until `gh issue close <number>` has been run successfully
- Verify issue closure with `gh issue view <number>` after closing
- Add a closing comment summarizing what was done before closing

**Commit with correct issue references:**

- Always verify the issue number matches the work being done
- Before committing, double-check: "Is this commit for issue #X?"
- Example: `git commit -m "feat: Add feature (#123)"` not `(#456)`

### PR Workflow

**Review Mode** (PR link only):

- Read `gh pr view/diff`
- Do NOT switch branches
- Do NOT change code

**Landing Mode:**

1. Create integration branch from `main`
2. Bring in PR commits (prefer rebase for linear history)
3. Apply fixes, add changelog
4. Run full gate locally BEFORE committing
5. Commit with contributor attribution
6. Merge back to `main`
7. Switch to `main` (never stay on topic branch)

---

## RELEASE CHANNELS

- **stable**: Tagged releases only (e.g., `vYYYY.M.D`)
- **beta**: Prerelease tags `vYYYY.M.D-beta.N`
- **dev**: Moving head on `main` (no tag)

---

## TECHNICAL STANDARDS

### Error Handling

**Auto-retry on transient errors:**

- When encountering API 500 errors or tool interruptions, automatically retry up to 2 times before asking the user
- Do NOT stop and wait for 'continue' on transient errors
- Only escalate to user if retry attempts fail
- Log retry attempts: "Retrying (attempt 2/2)..."

### Hardcoding Prevention

```python
# Use SSOT config
from autobot_shared.ssot_config import config
redis_host = config.redis.host
```

```typescript
// Use SSOT config
import { getBackendUrl } from '@/config/ssot-config'
```

Pre-commit hook enforces this. Guide: [`docs/developer/HARDCODING_PREVENTION.md`](docs/developer/HARDCODING_PREVENTION.md)

### Network Configuration

**Never assume or hardcode IP subnets:**

- Always check existing configuration files for the correct network ranges before making changes
- Never hardcode IP addresses - use environment variables or SSOT config
- The project is actively removing hardcoded IPs in favor of environment variables and dynamic configuration
- If you see hardcoded IPs in legacy code, flag them for removal

### Redis Client

```python
# ALWAYS use canonical utility
from autobot_shared.redis_client import get_redis_client
redis_client = get_redis_client(async_client=False, database="main")
# NEVER: redis.Redis(host="172.16.168.23", ...)
```

Databases: `main`, `knowledge`, `prompts`, `analytics`

### UTF-8 Encoding

Always use `encoding='utf-8'` explicitly. Guide: [`docs/developer/UTF8_ENFORCEMENT.md`](docs/developer/UTF8_ENFORCEMENT.md)

### Logging

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

No `console.*` or `print()` - pre-commit blocks these.

---

## INFRASTRUCTURE

### Service Layout (172.16.168.19-27)

| Service | IP:Port | Component | Purpose |
|---------|---------|-----------|---------|
| SLM Server | 172.16.168.19:443 | `autobot-slm-backend/` + `autobot-slm-frontend/` | SLM backend + admin UI (nginx+SSL) |
| Main (WSL) | 172.16.168.20:8001 | `autobot-user-backend/` | Backend API + VNC (6080) |
| Frontend VM | 172.16.168.21:443 | `autobot-user-frontend/` | User frontend (nginx+SSL, production build) |
| NPU VM | 172.16.168.22:8081 | `autobot-npu-worker/` | Hardware AI acceleration |
| Redis VM | 172.16.168.23:6379 | - | Data layer (Redis Stack) |
| AI Stack VM | 172.16.168.24:8080 | - | AI processing |
| Browser VM | 172.16.168.25:3000 | `autobot-browser-worker/` | Playwright automation |
| Reserved | 172.16.168.26 | - | (Unassigned) |
| Reserved | 172.16.168.27 | - | (Unassigned) |

### Component Architecture (CRITICAL - Don't Mix Up!)

| Directory | Deploys To | Description |
|-----------|------------|-------------|
| `autobot-user-backend/` | 172.16.168.20 (Main) | Core AutoBot backend - AI agents, chat, tools |
| `autobot-user-frontend/` | 172.16.168.21 (Frontend VM) | User chat interface (Vue 3, nginx+SSL) |
| `autobot-slm-backend/` | 172.16.168.19 (SLM) | **SLM backend** - Fleet management, monitoring |
| `autobot-slm-frontend/` | 172.16.168.19 (SLM) | **SLM admin dashboard** - Vue 3 UI (nginx+SSL) |
| `autobot-npu-worker/` | 172.16.168.22 (NPU) | NPU acceleration worker |
| `autobot-browser-worker/` | 172.16.168.25 (Browser) | Playwright automation worker |
| `autobot-shared/` | All backends | Common utilities (redis, config, logging) |
| `infrastructure/` | Dev machine | Per-role infrastructure (not deployed) |

**Before editing, verify:**

- `autobot-user-*` is for Main AutoBot functionality
- `autobot-slm-*` is for SLM fleet management (different system!)
- `autobot-shared/` is for Shared code deployed with each backend

**CRITICAL Project Structure Rules:**

- The frontend is in `autobot-slm-frontend/`, NOT `autobot-vue`
- Worktrees should be created in `../worktrees/issue-<number>/` (check existing pattern first)
- Never assume directory structure - verify with `ls` before creating paths
- Ansible playbooks and roles are in `autobot-slm-backend/ansible/`, NOT `infrastructure/ansible/`
- The primary working branch is `Dev_new_gui`
- Test files are colocated next to their source files, not in a separate `tests/` directory
- Import paths use the colocated structure - never use stale `from src.` imports for migrated modules

### Infrastructure Directory Structure

The infrastructure folder uses a per-role organization:

```text
infrastructure/
├── autobot-user-backend/       # User backend: docker, tests, config, scripts, templates
├── autobot-user-frontend/      # User frontend infra
├── autobot-slm-backend/        # SLM backend infra
├── autobot-slm-frontend/       # SLM frontend infra
├── autobot-npu-worker/         # NPU worker infra
├── autobot-browser-worker/     # Browser worker infra
└── shared/                     # Shared infrastructure
    ├── scripts/                # Common utilities, sync scripts
    ├── certs/                  # Certificate management
    ├── config/                 # Shared configurations
    ├── docker/                 # Shared docker resources
    ├── mcp/                    # MCP server configs
    ├── tools/                  # Development tools
    ├── tests/                  # Shared test utilities
    └── analysis/               # Analysis tools
```

**Sync commands:**

```bash
# User backend to Main server
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/

# User frontend to Frontend VM
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-user-frontend/

# SLM backend + frontend to SLM server
./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-backend/
./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-frontend/

# NPU worker to NPU VM
./infrastructure/shared/scripts/sync-to-vm.sh npu autobot-npu-worker/

# Browser worker to Browser VM
./infrastructure/shared/scripts/sync-to-vm.sh browser autobot-browser-worker/
```

### Frontend Deployment (CRITICAL)

- `.19` serves SLM admin frontend via nginx+SSL (production build)
- `.21` serves User frontend via nginx+SSL (production build)
- **FORBIDDEN**: `npm run dev` on any VM — production builds only
- Sync user frontend: `./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-user-frontend/`
- Sync SLM frontend: `./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-frontend/`

### Local-Only Development (ZERO TOLERANCE)

**NEVER edit on remote VMs** - No version control, no backup, VMs are ephemeral.

1. Edit in `/home/kali/Desktop/AutoBot/`
2. Sync immediately: `./infrastructure/shared/scripts/sync-to-vm.sh <vm> <component>/`

---

## AGENT DELEGATION

### Task Execution Strategy

**Prefer direct implementation over subagents:**

- Reserve Task agents for true exploration/research of unfamiliar code areas
- Use direct edits for implementation work on known codebases (faster and more reliable)
- Only use subagents when explicitly asked to explore or for truly parallel independent tasks

**When using subagent tasks:**

- Keep each task **focused and time-bounded**
- If a subagent task is interrupted or rejected by the user, switch to **direct implementation immediately**
- Do NOT retry subagent dispatch after rejection
- Break large tasks into smaller subagent units (prefer 3 small tasks over 1 large task)

### R-P-I Workflow (ONLY for these agents)

- `code-skeptic` - Risk analysis
- `systems-architect` - Architecture design

### Available Agents

**Implementation:** `senior-backend-engineer`, `frontend-engineer`, `database-engineer`, `devops-engineer`, `testing-engineer`, `code-reviewer` (MANDATORY), `documentation-engineer`

**Analysis:** `code-skeptic`, `systems-architect`, `performance-engineer`, `security-auditor`, `ai-ml-engineer`

**Planning:** `project-task-planner`, `project-manager`

```bash
# Launch parallel agents
Task(subagent_type="senior-backend-engineer", description="...", prompt="...")
Task(subagent_type="code-reviewer", description="Review changes", prompt="...")
```

---

## QUICK COMMANDS

```bash
# Startup
bash run_autobot.sh --dev

# Health checks
curl http://localhost:8001/api/health
redis-cli -h 172.16.168.23 ping

# Sync to VMs (new paths)
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/
./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-backend/

# Memory MCP
mcp__memory__search_nodes --query "keywords"
mcp__memory__create_entities --entities '[{"name": "...", "entityType": "...", "observations": [...]}]'
```

---

## DOCUMENTATION

**Key docs:** [`docs/developer/PHASE_5_DEVELOPER_SETUP.md`](docs/developer/PHASE_5_DEVELOPER_SETUP.md) | [`docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`](docs/api/COMPREHENSIVE_API_DOCUMENTATION.md) | [`docs/system-state.md`](docs/system-state.md)

**Guides:** `docs/developer/` - HARDCODING_PREVENTION, REDIS_CLIENT_USAGE, UTF8_ENFORCEMENT, INFRASTRUCTURE_DEPLOYMENT, SSOT_CONFIG_GUIDE
