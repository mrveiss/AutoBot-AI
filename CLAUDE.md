# AutoBot Development Instructions & Project Reference

This document contains development guidelines, project setup instructions, and architectural rules for the AutoBot platform.

> **📋 For system status updates and fixes, see:** [`docs/system-state.md`](docs/system-state.md)

---

## ⚡ WORKFLOW REQUIREMENTS

### **Every Task Must:**

1. **Create TodoWrite** to track progress (MANDATORY)
2. **Search Memory MCP** for similar past work: `mcp__memory__search_nodes`
3. **Use specialized agents** for complex tasks
4. **Code review is mandatory** for ALL code changes (use `code-reviewer` agent)

### **Workflow Violation Self-Check**

**Before proceeding, verify:**

- ❓ **Did I create TodoWrite?** → If NO: Create it now
- ❓ **Am I working alone on complex tasks?** → If YES: Delegate to agents
- ❓ **Will I modify code without review?** → If YES: Plan code-reviewer agent
- ❓ **Did I search Memory MCP?** → If NO: Search now
- ❓ **Am I considering a "quick fix"?** → If YES: STOP - Fix root cause instead

**If ANY answer reveals violation → STOP and correct immediately**

---

## 🚨 CRITICAL: NO TEMPORARY FIXES POLICY

**⚠️ MANDATORY RULE: ABSOLUTELY NO TEMPORARY FIXES OR WORKAROUNDS**

### **The Problem with Temporary Fixes:**

- **Temporary fixes CAUSE cascading problems** that multiply over time
- **They hide root causes** and prevent proper solutions
- **They create technical debt** that becomes impossible to track
- **They break when underlying systems change**
- **They make debugging exponentially harder**

### **✅ CORRECT APPROACH - Fix Root Causes:**

1. **Identify the Root Problem** - Never treat symptoms
2. **Fix the Underlying Issue** - Address the actual cause
3. **Verify the Fix Works** - Ensure proper resolution
4. **Remove Any Existing Workarounds** - Clean up previous band-aids

### **❌ FORBIDDEN - Never Do These:**

- **"Quick fixes"** or **"temporary solutions"**
- **Disabling functionality** instead of fixing it
- **Hardcoding values** to bypass broken systems
- **Try/catch blocks** that hide errors without fixing them
- **Timeouts** as solutions to performance problems
- **Comments like "TODO: fix this properly later"**

### **🎯 When You Hit a Blocker:**

1. **STOP working on the current issue**
2. **Identify what's blocking you**
3. **Fix the blocking issue FIRST**
4. **Return to original issue** after blocker is resolved
5. **Never work around blockers** - always through them

**THIS POLICY APPLIES TO ALL AGENTS, ALL CODE, ALL SITUATIONS - NO EXCEPTIONS**

---

## 🚫 HARDCODING PREVENTION (AUTOMATED ENFORCEMENT)

**⚠️ MANDATORY RULE: NO HARDCODED VALUES**

### **What Constitutes Hardcoding:**

- IP addresses (use `NetworkConstants` or `.env`)
- Port numbers (use `NetworkConstants` or `.env`)
- LLM model names (use `config.get_default_llm_model()` or `AUTOBOT_DEFAULT_LLM_MODEL`)
- URLs (use environment variables)
- API keys, passwords, secrets (use environment variables, NEVER commit)

### **Automated Detection:**

**Pre-Commit Hook**: Automatically scans staged files before every commit
```bash
# Runs automatically on git commit
./scripts/detect-hardcoded-values.sh
```

**Manual Scan**:
```bash
# Scan entire codebase for violations
./scripts/detect-hardcoded-values.sh

# Get detailed report
./scripts/detect-hardcoded-values.sh | less
```

### **How to Fix Violations:**

1. **For IPs/Ports**: Use `NetworkConstants` class
   ```python
   # ❌ BAD
   url = "http://172.16.168.20:8001/api/chat"

   # ✅ GOOD
   from src.constants.network_constants import NetworkConstants
   url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}/api/chat"
   ```

2. **For LLM Models**: Use config methods
   ```python
   # ❌ BAD
   model = "llama3.2:1b-instruct-q4_K_M"

   # ✅ GOOD
   model = config.get_default_llm_model()
   # OR
   model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2:1b")
   ```

3. **For Other Values**: Use `.env` file
   ```bash
   # Add to .env
   AUTOBOT_MY_SETTING=value

   # Use in code
   setting = os.getenv("AUTOBOT_MY_SETTING")
   ```

### **Override (Emergency Only):**

If hardcoding is ABSOLUTELY necessary (rare):
1. Document WHY in code comments
2. Add entry to `.hardcode-exceptions` file
3. Get approval in code review
4. Bypass pre-commit: `git commit --no-verify` (NOT RECOMMENDED)

**Detection script location**: `scripts/detect-hardcoded-values.sh`
**Pre-commit hook**: `.git/hooks/pre-commit-hardcode-check`

---

## 🚨 STANDARDIZED PROCEDURES

### Setup (Required First Time)

```bash
bash setup.sh [--full|--minimal|--distributed]
```

### Startup (Daily Use)

```bash
bash run_autobot.sh [--dev|--prod] [--desktop|--no-desktop] [--no-browser]
```

**❌ OBSOLETE METHODS:** `run_agent_unified.sh`, `setup_agent.sh` (archived in `scripts/archive/`)

---

## 🧹 REPOSITORY CLEANLINESS

**❌ NEVER place in root directory:**
- Test files (`test_*.py`, `*_test.py`)
- Report files (`*REPORT*.md`, `*_report.*`)
- Log files (`*.log`, `*.log.*`, `*.bak`)
- Analysis outputs, temporary files, backup files

**✅ USE proper directories:**
```
tests/           # All test files and results
logs/            # Application logs (gitignored)
reports/         # Generated reports (gitignored)
temp/            # Temporary files (gitignored)
analysis/        # Analysis outputs (gitignored)
backups/         # Backup files (gitignored)
```

---

## 🎨 CODE QUALITY ENFORCEMENT

**Status**: ✅ Automated via pre-commit hooks + CI/CD

**Setup once**: `bash scripts/install-pre-commit-hooks.sh`

**Auto-enforces**: Black, isort, flake8, autoflake, bandit, whitespace, YAML/JSON validation

👉 **Full details**: [`docs/developer/CODE_QUALITY_ENFORCEMENT.md`](docs/developer/CODE_QUALITY_ENFORCEMENT.md)

---

## 📋 TASK MANAGEMENT

**MANDATORY: Use Memory MCP for persistent task storage**

```bash
# View current tasks
mcp__memory__search_nodes --query "task"

# Create task entity
mcp__memory__create_entities --entities '[{"name": "Task Name", "entityType": "active_task", "observations": ["Description", "Status: pending", "Priority: High"]}]'

# Track progress
mcp__memory__add_observations --observations '[{"entityName": "Task Name", "contents": ["Progress update"]}]'

# Create task dependencies
mcp__memory__create_relations --relations '[{"from": "Task B", "to": "Task A", "relationType": "depends_on"}]'
```

**Use TodoWrite for immediate/short-term tracking during active work**

---

## ⚠️ CRITICAL: Single Frontend Server Architecture

### **Frontend Server Rules**

- **ONLY** `172.16.168.21:5173` runs the frontend (Frontend VM)
- **NO** frontend servers on main machine (`172.16.168.20`)
- **NO** local development servers (`localhost:5173`)
- **NO** multiple frontend instances permitted

### **Development Workflow**

1. **Edit Code Locally**: Make all changes in `/home/kali/Desktop/AutoBot/autobot-vue/`
2. **Sync to Frontend VM**: Use `./sync-frontend.sh` or `./scripts/utilities/sync-to-vm.sh frontend`
3. **Frontend VM Runs**: Either dev or production mode via `run_autobot.sh`

### **❌ STRICTLY FORBIDDEN**

- Starting frontend servers on main machine (`172.16.168.20`)
- Running `npm run dev`, `yarn dev`, `vite dev` locally
- Running any Vite development server on main machine
- Multiple frontend instances (causes port conflicts)
- Direct editing on remote VMs
- **ANY command that starts a server on port 5173 on main machine**

---

## 🚀 INFRASTRUCTURE & DEPLOYMENT

### **SSH Authentication & File Sync**

**SSH Keys**: `~/.ssh/autobot_key` (4096-bit RSA) configured for all 5 VMs: frontend(21), npu-worker(22), redis(23), ai-stack(24), browser(25)

**Sync files to VMs:**
```bash
# Sync specific file/directory to specific VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/ /home/autobot/autobot-vue/src/components/

# Sync to ALL VMs
./scripts/utilities/sync-to-vm.sh all scripts/setup.sh /home/autobot/scripts/
```

### **🚨 MANDATORY: Local-Only Development**

**NEVER edit code directly on remote VMs (172.16.168.21-25) - ZERO TOLERANCE**

**Required workflow:**
1. **Edit locally** in `/home/kali/Desktop/AutoBot/`
2. **Sync immediately** using sync scripts
3. **Never skip sync** - remote machines must stay synchronized

**Why this is critical:**
- ❌ **No version control** on remote VMs - changes completely untracked
- ❌ **No backup system** - remote edits never saved or recorded
- ❌ **VMs are ephemeral** - can be reinstalled anytime, **PERMANENT WORK LOSS**
- ❌ **No recovery mechanism** - cannot track or recover remote changes

### **Network Configuration**

**Service binding:**
- ✅ Bind services on `0.0.0.0:PORT` (accessible from network)
- ❌ NEVER use `localhost` or `127.0.0.1` (not accessible from remote VMs)
- ✅ Use actual IPs `172.16.168.x` for inter-VM communication

**Example**: Backend binds `0.0.0.0:8001`, accessed via `172.16.168.20:8001`

---

## Architecture Notes

### Service Layout - Distributed VM Infrastructure

**Infrastructure Overview:**
- 📡 **Main Machine (WSL)**: `172.16.168.20` - Backend API (port 8001) + Desktop/Terminal VNC (port 6080)
- 🌐 **Remote VMs:**
  - **VM1 Frontend**: `172.16.168.21:5173` - Web interface (SINGLE FRONTEND SERVER)
  - **VM2 NPU Worker**: `172.16.168.22:8081` - Hardware AI acceleration
  - **VM3 Redis**: `172.16.168.23:6379` - Data layer
  - **VM4 AI Stack**: `172.16.168.24:8080` - AI processing
  - **VM5 Browser**: `172.16.168.25:3000` - Web automation (Playwright)

### Key Files

- `setup.sh`: Standardized setup and installation script
- `run_autobot.sh`: Main startup script (replaces all other run methods)
- `backend/fast_app_factory_fix.py`: Fast backend with Redis timeout fix
- `compose.yml`: Distributed VM configuration
- `.env`: Main environment configuration for distributed infrastructure
- `config/config.yaml`: Central configuration file

---

## 🤖 AGENT DELEGATION

### **When to Use Research → Plan → Implement (R→P→I) Workflow**

**ONLY required for:**
- `code-skeptic` - Needs thorough risk analysis phase
- `systems-architect` - Requires comprehensive architecture planning

**For these agents, follow R→P→I phases:**
1. **Research**: Analyze problem, evaluate 2-3 solutions, document findings
2. **Plan**: Select solution, break down tasks, identify risks
3. **Implement**: Execute, review, test, document

**For all other agents:** Use direct delegation with TodoWrite tracking

### **Available Specialized Agents**

**Implementation Agents:**
- `senior-backend-engineer` - Complex backend development
- `frontend-engineer` - Vue.js/TypeScript frontend development
- `database-engineer` - Database schema and query optimization
- `devops-engineer` - Infrastructure and deployment tasks
- `testing-engineer` - Test implementation and validation
- `code-reviewer` - **MANDATORY** for all code changes
- `documentation-engineer` - Documentation updates

**Analysis Agents:**
- `code-skeptic` - Bug analysis, risk identification (use R→P→I)
- `systems-architect` - Architecture design, complex decisions (use R→P→I)
- `performance-engineer` - Performance optimization analysis
- `security-auditor` - Security analysis and audits
- `ai-ml-engineer` - AI/ML features and optimizations

**Planning Agents:**
- `project-task-planner` - Task breakdown from requirements
- `project-manager` - Project organization and coordination

### **Launch Multiple Agents in Parallel**

```bash
# Single message with multiple Task calls for parallel execution
Task(subagent_type="senior-backend-engineer", description="Backend work", prompt="...")
Task(subagent_type="frontend-engineer", description="Frontend work", prompt="...")
Task(subagent_type="code-reviewer", description="Review changes", prompt="...")
```

---

## 🔔 WORKFLOW VIOLATION DETECTION

### **System Reminders Are Requirements**

When you see these system reminders, they indicate **workflow violations**:

| System Reminder | Required Action |
|----------------|-----------------|
| **"TodoWrite hasn't been used recently"** | Create TodoWrite immediately |
| **"Consider using agents"** | Launch appropriate agents for complex tasks |
| **"Code review recommended"** | Launch code-reviewer agent immediately |
| **"Memory MCP could help"** | Search and store findings in Memory MCP |

### **Proactive Violation Detection**

**Check these patterns before proceeding:**

- [ ] Am I working alone on complex tasks? → Delegate to agents
- [ ] Did I start without TodoWrite? → Create it now
- [ ] Am I about to modify code? → Plan code-reviewer agent
- [ ] Have I searched Memory MCP? → Search before proceeding
- [ ] Am I considering a "quick fix"? → STOP - Fix root cause
- [ ] Did I skip analysis for complex problems? → Use code-skeptic or systems-architect with R→P→I

---

## Development Guidelines

### **Core Principles**

- **Fix root causes, never temporary fixes** (CRITICAL - NO EXCEPTIONS)
- **Use TodoWrite** to track all task progress
- **Code review is mandatory** - always use `code-reviewer` agent
- **Search Memory MCP** before starting work on similar problems
- **Delegate complex tasks** to specialized agents
- **Store findings** in Memory MCP for knowledge retention
- **Sync changes** to remote VMs immediately

### **Implementation Standards**

- Reason from facts, not assumptions
- **Timeout is not a solution** - fix the underlying performance issue
- **Never disable functionality** - fix it properly
- **Never work around blockers** - fix blocking issues first
- Trace errors end-to-end (frontend ↔ backend)
- Update install scripts when adding dependencies
- **ALWAYS ask user approval before start/stop/restart** - May disrupt active work
- Use agents and MCP tools for optimal solutions

### **Memory MCP Integration**

**Store findings and decisions:**
```bash
# Store research findings
mcp__memory__create_entities --entities '[{"name": "Finding Name", "entityType": "research_findings", "observations": ["Details here"]}]'

# Track implementation
mcp__memory__add_observations --observations '[{"entityName": "Finding Name", "contents": ["Implementation complete", "Tests passing"]}]'

# Link related work
mcp__memory__create_relations --relations '[{"from": "Finding A", "to": "Implementation B", "relationType": "informs"}]'
```

---

## 📋 Status Updates & System State

**For all system status updates, fixes, and improvements:**

👉 **See:** [`docs/system-state.md`](docs/system-state.md)

This includes:
- Critical fixes and resolutions
- System status changes
- Performance improvements
- Architecture updates
- Error resolutions

---

## How to Run AutoBot

**Daily startup**: `bash run_autobot.sh --dev`

**Other modes**: `bash run_autobot.sh [--prod|--dev] [--no-browser] [--desktop|--no-desktop] [--status|--stop|--restart]`

**VNC Desktop**: `http://127.0.0.1:6080/vnc.html` (enabled by default)

**Full options**: `bash run_autobot.sh --help`

---

## Monitoring & Debugging

**Health checks:**
- Backend: `curl http://localhost:8001/api/health`
- Redis: `redis-cli -h 172.16.168.23 ping`
- Logs: `tail -f logs/backend.log`

**Browser automation**: Use Browser VM (`172.16.168.25:3000`) - Playwright pre-installed. **Never install locally on Kali** (incompatible).

---

## Documentation

**Key docs**: [`docs/developer/PHASE_5_DEVELOPER_SETUP.md`](docs/developer/PHASE_5_DEVELOPER_SETUP.md) (setup) | [`docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`](docs/api/COMPREHENSIVE_API_DOCUMENTATION.md) (API) | [`docs/system-state.md`](docs/system-state.md) (status)

**All docs**: `docs/` contains api/, architecture/, developer/, features/, security/, troubleshooting/

---

## 📋 QUICK REFERENCE

### **Task Start Checklist**

```bash
# 1. TodoWrite (MANDATORY)
TodoWrite: Track task progress

# 2. Memory MCP Search
mcp__memory__search_nodes --query "relevant keywords"

# 3. Agent Delegation (for complex tasks)
Task(subagent_type="appropriate-agent", description="...", prompt="...")

# 4. Code Review (MANDATORY for code changes)
Task(subagent_type="code-reviewer", description="Review changes", prompt="...")
```

### **Critical Policies**

| Policy | Rule |
|--------|------|
| **Temporary Fixes** | ❌ NEVER - Always fix root causes (NO EXCEPTIONS) |
| **Process Control** | ⚠️ ALWAYS ask user approval before start/stop/restart |
| **TodoWrite** | ✅ MANDATORY for all tasks |
| **Code Review** | ✅ MANDATORY for all code changes |
| **Frontend Server** | ⚠️ ONLY on VM1 (172.16.168.21:5173) |
| **Remote VM Edits** | ❌ FORBIDDEN - Edit locally, sync immediately |
| **Blockers** | 🔧 Fix blockers first, never work around them |
| **R→P→I Workflow** | ⚠️ ONLY for code-skeptic and systems-architect agents |

### **Workflow Violations - Self Check**

- Did I create TodoWrite? ✓
- Did I search Memory MCP? ✓
- Am I using agents for complex tasks? ✓
- Will code be reviewed? ✓
- Am I fixing root cause (not workaround)? ✓

**If ANY unchecked → STOP and correct immediately**

---
