# AutoBot Development Instructions

> **Status updates:** [`docs/system-state.md`](docs/system-state.md)

---

## ⚡ WORKFLOW REQUIREMENTS (MANDATORY)

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
- ✓ Work tied to GitHub issue? → If NO: Create/link first
- ✓ Subtasks added to issue as checklist? → If NO: Add now
- ✓ Memory MCP searched? → If NO: Search now
- ✓ Complex tasks delegated to agents? → If NO: Delegate
- ✓ Fixing root cause (not workaround)? → If NO: STOP
- ✓ Integration needs both frontend AND backend? → If YES: Plan BOTH

**Before marking complete:**
- ✓ ALL code committed with issue refs?
- ✓ ALL acceptance criteria verified?
- ✓ Closing summary added to issue?
- ✓ Issue closed?

**If ANY fails → STOP and correct immediately**

---

## 👤 CODE OWNERSHIP (MANDATORY - UNBREAKABLE)

**mrveiss** is the **SOLE OWNER and AUTHOR** of ALL AutoBot code. No exceptions.

```python
# File header template
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

---

## 🚨 CRITICAL POLICIES

### No Temporary Fixes (ZERO TOLERANCE)
- ❌ Quick fixes, workarounds, disabling functionality
- ❌ Hardcoding to bypass issues, try/catch hiding errors
- ❌ "TODO: fix later" comments
- ✅ Identify root problem → Fix underlying issue → Verify → Remove workarounds

### Function Length (≤50 lines)
| Lines | Action |
|-------|--------|
| ≤30 | ✅ Ideal |
| 31-50 | ⚠️ Consider refactoring |
| 51-65 | 🔴 Must refactor before merge |
| >65 | ❌ Immediate refactoring required |

Use **Extract Method** pattern: Create `_helper_function()` with docstring referencing parent issue.

### File Naming
❌ **FORBIDDEN**: `_fix`, `_v2`, `_optimized`, `_new`, `_temp`, `_backup`, `_old`, date suffixes
✅ Use permanent, descriptive names. Version control handles versions.

### Consolidation Rules
When merging duplicate code: **Preserve ALL features** + **Choose BEST implementation**. Never drop features for convenience.

---

## 🔗 GITHUB ISSUE TRACKING

**Repository:** https://github.com/mrveiss/AutoBot-AI

**Commit format:** `<type>(scope): <description> (#issue-number)`

**Issue is complete ONLY when:**
1. All code committed with issue refs
2. All acceptance criteria verified
3. Tests passing
4. Code reviewed
5. Closing summary added
6. Issue status = closed

---

## 🚫 TECHNICAL STANDARDS

### Hardcoding Prevention
```python
# ✅ Use SSOT config
from src.config.ssot_config import config
redis_host = config.redis.host
```
```typescript
// ✅ Use SSOT config
import { getBackendUrl } from '@/config/ssot-config'
```
Pre-commit hook enforces this. Guide: [`docs/developer/HARDCODING_PREVENTION.md`](docs/developer/HARDCODING_PREVENTION.md)

### Redis Client
```python
# ✅ ALWAYS use canonical utility
from src.utils.redis_client import get_redis_client
redis_client = get_redis_client(async_client=False, database="main")
# ❌ NEVER: redis.Redis(host="172.16.168.23", ...)
```
Databases: `main`, `knowledge`, `prompts`, `analytics`

### UTF-8 Encoding
Always use `encoding='utf-8'` explicitly. Guide: [`docs/developer/UTF8_ENFORCEMENT.md`](docs/developer/UTF8_ENFORCEMENT.md)

### Logging
```python
# ✅ Backend
import logging
logger = logging.getLogger(__name__)
logger.info("Message: %s", data)
```
```typescript
// ✅ Frontend
import { createLogger } from '@/utils/debugUtils'
const logger = createLogger('ComponentName')
```
❌ No `console.*` or `print()` - pre-commit blocks these.

---

## 🖥️ INFRASTRUCTURE

### Service Layout
| Service | IP:Port | Purpose |
|---------|---------|---------|
| Main (WSL) | 172.16.168.20:8001 | Backend API + VNC (6080) |
| VM1 Frontend | 172.16.168.21:5173 | Web interface (ONLY frontend server) |
| VM2 NPU | 172.16.168.22:8081 | Hardware AI acceleration |
| VM3 Redis | 172.16.168.23:6379 | Data layer |
| VM4 AI Stack | 172.16.168.24:8080 | AI processing |
| VM5 Browser | 172.16.168.25:3000 | Playwright automation |
| SLM Server | 172.16.168.19:8000 | System Lifecycle Manager |

### Component Architecture (CRITICAL - Don't Mix Up!)

| Directory | Deploys To | Description |
|-----------|------------|-------------|
| `src/` | 172.16.168.20 (Main) | Core AutoBot backend - AI agents, chat, tools |
| `autobot-vue/` | 172.16.168.20 (Main) | Main AutoBot chat interface |
| `slm-server/` | 172.16.168.19 (SLM) | **SLM backend** - Fleet management, code sync |
| `slm-admin/` | 172.16.168.21 (Frontend VM) | **SLM admin dashboard** - Vue 3 UI for fleet |

**Before editing, verify:**
- `src/` or `autobot-vue/` → Main AutoBot functionality
- `slm-server/` or `slm-admin/` → SLM fleet management (different system!)

**Sync commands:**
```bash
# SLM Admin frontend → VM1
./scripts/utilities/sync-to-vm.sh frontend slm-admin/src/ /home/autobot/AutoBot/slm-admin/src/

# SLM Server backend → SLM machine
./scripts/utilities/sync-to-vm.sh slm slm-server/ /home/autobot/slm-server/
```

### Single Frontend Server (CRITICAL)
- **ONLY** `172.16.168.21:5173` runs frontend
- ❌ **FORBIDDEN**: `npm run dev` on main machine, any local frontend server
- ✅ Edit locally → Sync with `./sync-frontend.sh`

### Local-Only Development (ZERO TOLERANCE)
**NEVER edit on remote VMs** - No version control, no backup, VMs are ephemeral.
1. Edit in `/home/kali/Desktop/AutoBot/`
2. Sync immediately: `./scripts/utilities/sync-to-vm.sh <vm> <path>`

---

## 🤖 AGENT DELEGATION

### R→P→I Workflow (ONLY for these agents)
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

## 📋 QUICK COMMANDS

```bash
# Startup
bash run_autobot.sh --dev

# Health checks
curl http://localhost:8001/api/health
redis-cli -h 172.16.168.23 ping

# Sync to VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/ /home/autobot/autobot-vue/src/

# Memory MCP
mcp__memory__search_nodes --query "keywords"
mcp__memory__create_entities --entities '[{"name": "...", "entityType": "...", "observations": [...]}]'
```

---

## 📚 DOCUMENTATION

**Key docs:** [`docs/developer/PHASE_5_DEVELOPER_SETUP.md`](docs/developer/PHASE_5_DEVELOPER_SETUP.md) | [`docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`](docs/api/COMPREHENSIVE_API_DOCUMENTATION.md) | [`docs/system-state.md`](docs/system-state.md)

**Guides:** `docs/developer/` - HARDCODING_PREVENTION, REDIS_CLIENT_USAGE, UTF8_ENFORCEMENT, INFRASTRUCTURE_DEPLOYMENT, SSOT_CONFIG_GUIDE
