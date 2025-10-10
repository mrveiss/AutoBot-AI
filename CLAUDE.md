# AutoBot Development Instructions & Project Reference

This document contains development guidelines, project setup instructions, and architectural rules for the AutoBot platform.

> **📋 For system status updates and fixes, see:** [`docs/system-state.md`](docs/system-state.md)

---

## ⚡ WORKFLOW ENFORCEMENT - READ THIS FIRST

**🚨 BEFORE STARTING ANY TASK - MANDATORY PRE-FLIGHT CHECKLIST:**

```
⏱️ Estimated Time: 2-3 minutes | ⚠️ CANNOT SKIP - MANDATORY FOR ALL TASKS

[ ] Step 1: Create TodoWrite with Research → Plan → Implement phases
[ ] Step 2: Search Memory MCP for similar past work (mcp__memory__search_nodes)
[ ] Step 3: Identify minimum 2 specialized agents to launch in parallel
[ ] Step 4: Plan code-reviewer agent if ANY code will be modified
[ ] Step 5: Check for RED FLAGS below - STOP if any detected

🔴 SELF-AWARENESS CHECK: Am I feeling rushed or pressured?
   → If YES: MORE rigor required, NOT less. Slow down intentionally.
```

**🚩 RED FLAGS - IMMEDIATE STOP POINTS:**

```
❌ User says "quick fix" or "just do X"
   → STOP: Plan Research → Plan → Implement workflow instead

❌ Thinking "I'll fix this properly later"
   → STOP: Fix it properly RIGHT NOW, not later

❌ Feeling rushed or under time pressure
   → STOP: Pressure requires MORE rigor, not shortcuts

❌ About to edit code directly without agents
   → STOP: Launch specialized agents instead

❌ System reminder about TodoWrite appears
   → STOP: You're not tracking tasks - create TodoWrite immediately

❌ Skipping Research phase because "it's simple"
   → STOP: You don't understand the problem yet - Research first

❌ Planning to work around a blocker
   → STOP: Fix the blocker first, never work around it

❌ About to disable functionality instead of fixing
   → STOP: Violates NO TEMPORARY FIXES policy
```

**✅ CORRECT RESPONSE TO RED FLAGS:**

1. **STOP current work immediately**
2. **Create TodoWrite** with proper phase breakdown
3. **Launch minimum 2 agents** in parallel for Research phase
4. **Follow Research → Plan → Implement** systematically
5. **Document decision** in Memory MCP

**🎯 WORKFLOW VIOLATION SELF-TEST (Use Anytime):**

Ask yourself these questions right now:

- ❓ **Did I create TodoWrite before starting?** → If NO: Create it now
- ❓ **Have I launched any agents yet?** → If NO: Launch 2+ agents now
- ❓ **Am I in Research, Plan, or Implement phase?** → If UNSURE: Start Research
- ❓ **Did I search Memory MCP for similar work?** → If NO: Search now
- ❓ **Am I working alone or with agents?** → If ALONE: Delegate to agents
- ❓ **Will I modify code without code review?** → If YES: Plan code-reviewer

**If ANY answer reveals violation → STOP and correct immediately**

---

## 🚫 ABSOLUTE PROHIBITION: NEVER WORK ALONE

**⛔ YOU MUST NEVER DO WORK DIRECTLY - ALWAYS DELEGATE TO SPECIALIZED AGENTS ⛔**

### **MANDATORY DELEGATION RULE**

**You are a MANAGER and ORCHESTRATOR, NOT a direct implementer.**

**❌ STRICTLY FORBIDDEN (ZERO TOLERANCE):**
- Writing code yourself
- Editing files directly
- Implementing features alone
- Analyzing code without agents
- Making changes without agent assistance
- "Just doing it quickly" without delegation
- ANY direct implementation work

**✅ REQUIRED BEHAVIOR (EVERY SINGLE TIME):**
- **ALWAYS launch specialized agents** for every task
- **NEVER use Read/Write/Edit tools** without launching agents first
- **MINIMUM 2 agents in parallel** for any work
- **Delegate 100% of implementation** to appropriate agents
- **Your role**: Plan, coordinate, orchestrate, synthesize results

### **Why This Rule Exists**

**Working alone causes:**
- ❌ No code review = bugs slip through
- ❌ No parallel processing = slower work
- ❌ No specialized expertise = suboptimal solutions
- ❌ No knowledge capture = lessons lost
- ❌ Workflow violations = technical debt

**Agent delegation ensures:**
- ✅ Parallel processing = faster completion
- ✅ Specialized expertise = better quality
- ✅ Automatic code review = fewer bugs
- ✅ Knowledge capture = documented decisions
- ✅ Proper workflow = maintainable code

### **Enforcement Examples**

❌ **WRONG** (Working alone):
```
User: "Add a new API endpoint for user profile"
Claude: *Uses Write tool to create the endpoint directly*
```

✅ **CORRECT** (Agent delegation):
```
User: "Add a new API endpoint for user profile"
Claude: *Launches agents*
- Task(subagent_type="senior-backend-engineer", description="Implement user profile API", prompt="...")
- Task(subagent_type="code-reviewer", description="Review API implementation", prompt="...")
```

**THIS RULE APPLIES TO ALL TASKS - NO EXCEPTIONS - EVER**

---

## 🚨 STANDARDIZED PROCEDURES

**ONLY PERMITTED SETUP AND RUN METHODS:**

### Setup (Required First Time)

```bash
bash setup.sh [--full|--minimal|--distributed]
```

### Startup (Daily Use)

```bash
bash run_autobot.sh [--dev|--prod] [--desktop|--no-desktop] [--no-browser]
```

**❌ OBSOLETE METHODS (DO NOT USE):**

- ~~`run_agent_unified.sh`~~ → Use `run_autobot.sh`
- ~~`setup_agent.sh`~~ → Use `setup.sh`
- ~~Any other run scripts~~ → ALL archived in `scripts/archive/`

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

## 🧹 REPOSITORY CLEANLINESS STANDARDS

**MANDATORY: Keep root directory clean and organized**

### **File Placement Rules:**

- **❌ NEVER place in root directory:**
  - Test files (`test_*.py`, `*_test.py`)
  - Report files (`*REPORT*.md`, `*_report.*`)
  - Log files (`*.log`, `*.log.*`, `*.bak`)
  - Analysis outputs (`analysis_*.json`, `*_analysis.*`)
  - Temporary files (`*.tmp`, `*.temp`)
  - Backup files (`*.backup`, `*.old`)

### **Proper Directory Structure:**

```
/
├── tests/           # All test files go here
│   ├── results/     # Test results and validation reports
│   └── temp/        # Temporary test files
├── logs/            # Application logs (gitignored)
├── reports/         # Generated reports (gitignored)
├── temp/            # Temporary files (gitignored)
├── analysis/        # Analysis outputs (gitignored)
└── backups/         # Backup files (gitignored)
```

### **Agent and Script Guidelines:**

- **All agents MUST**: Use proper output directories for their files
- **All scripts MUST**: Create organized output in designated folders
- **Test systems MUST**: Place results in `tests/results/` directory
- **Report generators MUST**: Output to `reports/` directory (gitignored)
- **Monitoring systems MUST**: Log to `logs/` directory (gitignored)

## 🎨 CODE QUALITY ENFORCEMENT

**Status**: ✅ Automated via pre-commit hooks + CI/CD (active since 2025-10-09)

**Setup once**: `bash scripts/install-pre-commit-hooks.sh`

**Auto-enforces**: Black, isort, flake8, autoflake, bandit, whitespace, YAML/JSON validation

👉 **Full details**: [`docs/developer/CODE_QUALITY_ENFORCEMENT.md`](docs/developer/CODE_QUALITY_ENFORCEMENT.md)

---

## 📋 TASK MANAGEMENT STANDARDS

**MANDATORY: Use Memory MCP for all task management**

### **Task Management System:**

- **Primary**: Memory MCP with entity-based task storage
- **Tasks stored as entities** with type `migrated_task` or `active_task`
- **Dependencies tracked** via relations in memory graph
- **Comprehensive task details** preserved in observations
- **No language compatibility issues** (English-only interface)

### **Task Management Commands:**

```bash
# View current tasks
mcp__memory__search_nodes --query "migrated_task"

# View task dependencies
mcp__memory__read_graph

# Create new task entity
mcp__memory__create_entities --entities '[{"name": "Task Name", "entityType": "active_task", "observations": ["Description", "Status: pending", "Priority: High"]}]'

# Add task dependencies
mcp__memory__create_relations --relations '[{"from": "Task B", "to": "Task A", "relationType": "depends_on"}]'
```

### **✅ CORRECT Task Management Workflow:**

1. **Create task entities** with descriptive names and comprehensive observations
2. **Establish dependencies** using relations between task entities
3. **Track progress** by adding observations to existing entities
4. **Maintain task history** in memory graph for project continuity
5. **Use TodoWrite** for immediate/short-term task tracking during active work

### **❌ AVOID:**

- Using external task managers with language compatibility issues
- Creating tasks without proper entity structure
- Ignoring task dependencies and relationships
- Losing task history during system changes

---

## ⚠️ **CRITICAL: Single Frontend Server Architecture**

**MANDATORY FRONTEND SERVER RULES:**

### **✅ CORRECT: Single Frontend Server**

- **ONLY** `172.16.168.21:5173` runs the frontend (Frontend VM)
- **NO** frontend servers on main machine (`172.16.168.20`)
- **NO** local development servers (`localhost:5173`)
- **NO** multiple frontend instances permitted

### **Development Workflow:**

1. **Edit Code Locally**: Make all changes in `/home/kali/Desktop/AutoBot/autobot-vue/`
2. **Sync to Frontend VM**: Use `./sync-frontend.sh` or `./scripts/utilities/sync-to-vm.sh frontend`
3. **Frontend VM Runs**: Either dev or production mode via `run_autobot.sh`

### **❌ STRICTLY FORBIDDEN (CAUSES SYSTEM CONFLICTS):**

- Starting frontend servers on main machine (`172.16.168.20`)
- Running `npm run dev` locally
- Running `yarn dev` locally
- Running `vite dev` locally
- Running any Vite development server on main machine
- Multiple frontend instances (causes port conflicts and confusion)
- Direct editing on remote VMs
- **ANY command that starts a server on port 5173 on main machine**

---

## 🚀 INFRASTRUCTURE & DEPLOYMENT RULES

### **SSH Authentication & File Sync**

**SSH Keys**: `~/.ssh/autobot_key` (4096-bit RSA) configured for all 5 VMs: frontend(21), npu-worker(22), redis(23), ai-stack(24), browser(25)

**Sync files to VMs**:
```bash
# Sync specific file/directory to specific VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/ /home/autobot/autobot-vue/src/components/

# Sync to ALL VMs
./scripts/utilities/sync-to-vm.sh all scripts/setup.sh /home/autobot/scripts/
```

### **🚨 MANDATORY: Local-Only Development**

**NEVER edit code directly on remote VMs (172.16.168.21-25) - ZERO TOLERANCE**

**Required workflow**:
1. **Edit locally** in `/home/kali/Desktop/AutoBot/`
2. **Sync immediately** using sync scripts
3. **Never skip sync** - remote machines must stay synchronized

**Why this is critical**:
- ❌ **No version control** on remote VMs - changes completely untracked
- ❌ **No backup system** - remote edits never saved or recorded
- ❌ **VMs are ephemeral** - can be reinstalled anytime, **PERMANENT WORK LOSS**
- ❌ **No recovery mechanism** - cannot track or recover remote changes

### **Network Configuration**

**Service binding**:
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

## 🔄 MANDATORY STANDARD WORKFLOW

**⚠️ CRITICAL: ALL TASKS MUST FOLLOW RESEARCH → PLAN → IMPLEMENT METHODOLOGY**

Every task, regardless of size or complexity, MUST progress through these three phases in order. No phase skipping is permitted. This ensures thorough analysis, proper planning, and successful implementation.

### **🔍 PHASE 1: RESEARCH (Mandatory)**

**Step R1: Problem Analysis & Context Gathering**
- Launch research agents in parallel using `Task` tool:
  - `general-purpose` for broad codebase analysis
  - `systems-architect` for architectural considerations
  - `security-auditor` if security implications exist
  - Domain-specific agents as needed
- Use `mcp__sequential-thinking` for systematic problem breakdown
- Use `mcp__memory__search_nodes` to check for related previous work
- **Exit Criteria**: Problem clearly defined, context understood, constraints identified

**Step R2: Solution Research & Evaluation**
- Use `mcp__context7__resolve-library-id` and `get-library-docs` for current best practices
- Launch multiple specialized agents to research domain-specific solutions in parallel
- Use `WebSearch` for external research when needed
- Evaluate multiple solution approaches systematically
- **Exit Criteria**: At least 2-3 potential solution approaches identified and evaluated

**Step R3: Research Validation & Documentation**
- Store all research findings using `mcp__memory__create_entities`
- Create comprehensive research summary with pros/cons of each approach
- Identify any research gaps, uncertainties, or potential blockers
- **Exit Criteria**: Research completeness validated, findings documented in Memory MCP

**🚨 MANDATORY CHECKPOINT**: Cannot proceed to Plan phase without completing ALL Research steps

---

### **📋 PHASE 2: PLAN (Mandatory - Requires Research Completion)**

**Step P1: Solution Selection & Architecture Design**
- Use `systems-architect` agent to evaluate research findings
- Use `mcp__structured-thinking__chain_of_thought` to analyze trade-offs systematically
- Select optimal solution based on comprehensive research analysis
- Design high-level implementation architecture and approach
- **Exit Criteria**: Solution selected, architecture designed, technical approach defined

**Step P2: Implementation Task Breakdown**
- Use `project-task-planner` to break solution into concrete, actionable tasks
- Use `project-manager` to organize tasks, dependencies, and resource allocation
- Use `mcp__shrimp-task-manager__plan_task` for AI-powered intelligent scheduling
- Identify which specialized agents will handle each task
- Plan parallel execution tracks to maximize efficiency and minimize dependencies
- **Exit Criteria**: Detailed task list created, agent assignments made, dependencies mapped

**Step P3: Plan Validation & Approval**
- Use `code-skeptic` to identify potential implementation risks and failure points
- Use `performance-engineer` to assess performance implications
- Review plan for completeness, feasibility, and alignment with research
- Store complete plan using `mcp__memory__create_entities` with proper relations
- Get explicit approval to proceed (user confirmation or automated validation)
- **Exit Criteria**: Plan validated, risks identified and mitigated, approval obtained

**🚨 MANDATORY CHECKPOINT**: Cannot proceed to Implement phase without plan approval

---

### **⚙️ PHASE 3: IMPLEMENT (Mandatory - Requires Plan Approval)**

**Step I1: Implementation Execution**
- Launch specialized agents in parallel based on plan assignments
- Use `TodoWrite` to track immediate task progress during active implementation
- Use `mcp__shrimp-task-manager__execute_task` for complex multi-agent orchestration
- Execute plan tasks systematically, handling blockers by returning to appropriate earlier phase
- **Continuous Monitoring**: Track progress, identify blockers, maintain parallel execution

**Step I2: Verification & Quality Assurance**
- Use `code-reviewer` for ALL code changes (MANDATORY - no exceptions)
- Use `testing-engineer` to validate implementation with comprehensive testing
- Use `security-auditor` for any security-critical changes
- Run all required lint, typecheck, and test commands per project standards
- **Exit Criteria**: Implementation verified, all tests pass, quality gates satisfied

**Step I3: Documentation & Knowledge Capture**
- Use `documentation-engineer` to update all relevant documentation
- Use `mcp__memory__add_observations` to capture lessons learned and implementation insights
- Update Memory MCP with implementation results and any design changes made during execution
- Sync changes to remote VMs using proper sync procedures
- **Exit Criteria**: Implementation complete, documented, knowledge captured, changes deployed

---

### **🚦 UNIFIED PHASE CHECKPOINTS**

| Phase | Duration | Exit Criteria | Critical Actions if Failed |
|-------|----------|---------------|---------------------------|
| **Research** | 15-30 min | ✅ Min 2 agents launched<br>✅ Memory MCP searched<br>✅ Root cause identified<br>✅ 2-3 solutions evaluated<br>✅ Findings in Memory MCP<br>✅ Unknowns documented | Launch more agents<br>Search Memory MCP deeper<br>Document all unknowns |
| **Plan** | 10-20 min | ✅ Solution selected<br>✅ Systems-architect used<br>✅ Code-reviewer planned<br>✅ Agents assigned (TodoWrite)<br>✅ Risks identified (code-skeptic)<br>✅ Plan in Memory MCP | Return to Research if unclear<br>Launch code-skeptic<br>Document assignments<br>Store plan in MCP |
| **Implement** | 20-60 min | ✅ Agents launched per plan<br>✅ TodoWrite tracking progress<br>✅ Code reviewed (MANDATORY)<br>✅ All tests passing<br>✅ Changes synced to VMs<br>✅ Docs updated<br>✅ Knowledge in Memory MCP<br>✅ No temporary fixes | Launch code-reviewer NOW<br>Fix all tests<br>Sync to VMs<br>Capture lessons in MCP<br>Remove workarounds |

**❌ CANNOT PROCEED WITHOUT ALL PHASE CHECKBOXES COMPLETE**

---

### **🎯 WORKFLOW ENFORCEMENT PRINCIPLES**

1. **No Phase Skipping**: Each phase must be completed with all exit criteria met before proceeding
2. **Parallel Agent Execution**: Use multiple specialized agents simultaneously within each phase
3. **Memory Persistence**: ALL decisions, findings, and results must be stored in Memory MCP
4. **Blocker Handling**: If blocked during any phase, return to appropriate earlier phase to resolve
5. **Quality Gates**: Mandatory validation and approval at each phase transition
6. **Knowledge Capture**: Continuous learning and documentation throughout entire workflow
7. **Agent Specialization**: Always delegate to appropriate specialized agents, never work alone
8. **MCP Tool Integration**: Leverage all available MCP tools for enhanced capabilities

### **🚨 CRITICAL FAILURE SCENARIOS**

**If you encounter blockers:**
1. **NEVER work around the blocker** - this violates the "No Temporary Fixes" policy
2. **Return to Research phase** to understand the blocking issue
3. **Update the Plan** based on new research findings
4. **Proceed with proper implementation** that addresses the root cause

**If implementation fails:**
1. **Stop implementation immediately**
2. **Return to Plan phase** to analyze what went wrong
3. **Conduct additional Research** if new unknowns are discovered
4. **Revise plan** with lessons learned
5. **Re-attempt implementation** with improved approach

### **📊 WORKFLOW SUCCESS METRICS**

- **Research Completeness**: All potential solutions identified and evaluated
- **Plan Quality**: Clear tasks, proper agent assignments, realistic timelines
- **Implementation Success**: All tests pass, no temporary fixes, proper documentation
- **Knowledge Retention**: All decisions and learnings captured in Memory MCP
- **Agent Utilization**: Multiple agents used in parallel throughout workflow

---

## 🤖 AGENT DELEGATION & PARALLEL PROCESSING REQUIREMENTS

**⚠️ MANDATORY: You are a manager and orchestrator, NOT a direct implementer**

### **Core Delegation Principles**

1. **Never Work Alone**: Always delegate to specialized agents, never implement tasks directly
2. **Parallel Execution**: Launch multiple agents simultaneously whenever possible
3. **Agent Specialization**: Match tasks to the most appropriate specialized agents
4. **MCP Tool Leverage**: Use all available MCP tools to enhance agent capabilities
5. **Continuous Orchestration**: Monitor progress and coordinate between agents

### **🎯 Agent Selection Matrix**

**Research Phase Agents:**
- `general-purpose`: Broad codebase analysis, multi-step research tasks
- `systems-architect`: Architecture analysis, complex system design decisions
- `security-auditor`: Security implications, vulnerability analysis
- `database-engineer`: Database-related research and optimization
- `performance-engineer`: Performance implications and bottlenecks
- `ai-ml-engineer`: AI/ML related features and optimizations

**Planning Phase Agents:**
- `project-task-planner`: Task breakdown from requirements
- `project-manager`: Project organization, resource coordination
- `systems-architect`: Technical architecture and design decisions
- `code-skeptic`: Risk analysis and failure scenario identification

**Implementation Phase Agents:**
- `senior-backend-engineer`: Complex backend implementation
- `frontend-engineer`: Vue.js/TypeScript frontend development
- `database-engineer`: Database schema and query optimization
- `devops-engineer`: Infrastructure and deployment tasks
- `testing-engineer`: Test implementation and validation
- `code-reviewer`: Mandatory code review and quality assurance
- `documentation-engineer`: Documentation updates and maintenance

### **🚀 Parallel Processing Strategies**

**Research Phase Parallel Tracks:**
```
Track 1: general-purpose → codebase analysis
Track 2: systems-architect → architecture review
Track 3: security-auditor → security implications
Track 4: domain-expert → specialized analysis
```

**Planning Phase Parallel Tracks:**
```
Track 1: project-task-planner → task breakdown
Track 2: systems-architect → architecture design
Track 3: code-skeptic → risk identification
Track 4: performance-engineer → performance planning
```

**Implementation Phase Parallel Tracks:**
```
Track 1: backend-engineer → API development
Track 2: frontend-engineer → UI implementation
Track 3: database-engineer → data layer
Track 4: testing-engineer → test coverage
Track 5: documentation-engineer → documentation
```

### **📋 Agent Coordination Commands**

**Launch Multiple Agents in Parallel:**
```
Use single message with multiple Task tool calls:
- Task(subagent_type="general-purpose", description="Research X", prompt="...")
- Task(subagent_type="systems-architect", description="Analyze Y", prompt="...")
- Task(subagent_type="security-auditor", description="Review Z", prompt="...")
```

**Agent Communication Patterns:**
- Store findings in Memory MCP for cross-agent access
- Use structured entities and relations to link related work
- Coordinate dependencies through Memory MCP relations
- Track progress using TodoWrite for orchestration visibility

### **🔄 Workflow Integration Requirements**

**Every Workflow Phase MUST:**
1. **Launch minimum 2 agents in parallel** (unless single specialized task)
2. **Use Memory MCP** to store all agent findings and decisions
3. **Coordinate via TodoWrite** for immediate task tracking
4. **Validate agent completion** before phase transition
5. **Synthesize agent results** into coherent phase output

---

## 🔔 SYSTEM REMINDERS ARE REQUIREMENTS

**CRITICAL: System reminders are NOT suggestions - they are MANDATORY requirements**

### **Understanding System Reminders**

When you see these system reminders, they indicate **workflow violations in progress**:

| System Reminder | What It Means | Required Action |
|----------------|---------------|-----------------|
| **"TodoWrite hasn't been used recently"** | You're not tracking task progress | **STOP** → Create TodoWrite immediately with Research/Plan/Implement phases |
| **"Consider using agents"** | You're working alone instead of delegating | **STOP** → Launch minimum 2 agents in parallel right now |
| **"Code review recommended"** | Code changes without mandatory review | **STOP** → Launch code-reviewer agent immediately |
| **"Memory MCP could help"** | Not using persistent knowledge storage | **STOP** → Search and store findings in Memory MCP |

### **System Reminder Response Protocol**

```
🚨 WHEN ANY SYSTEM REMINDER APPEARS:

Step 1: STOP current work immediately
Step 2: Acknowledge the violation publicly
Step 3: Execute the required corrective action
Step 4: Resume work only after correction complete

Every system reminder = Active workflow violation
```

### **Proactive Violation Detection**

**Before you proceed with ANY action, check for these patterns:**

```
⚠️ VIOLATION DETECTION CHECKLIST:

[ ] Am I working alone without agents?
    → Launch 2+ agents in parallel immediately

[ ] Did I start without creating TodoWrite?
    → Create TodoWrite with workflow phases now

[ ] Am I about to modify code?
    → Plan code-reviewer agent before changing ANY code

[ ] Have I searched Memory MCP for similar work?
    → Search mcp__memory__search_nodes before proceeding

[ ] Am I considering a "quick fix" or workaround?
    → STOP - Return to Research phase instead

[ ] Did I skip Research phase because task seems simple?
    → STOP - Simplicity is an illusion, Research first
```

### **Automatic Correction Procedures**

**If system reminder appears OR violation detected:**

1. **TodoWrite Missing:**
   ```
   Create TodoWrite immediately:
   - [ ] Research: [Brief description]
   - [ ] Plan: [Brief description]
   - [ ] Implement: [Brief description]
   ```

2. **Agents Not Used:**
   ```
   Launch minimum 2 agents in parallel:
   - Task(subagent_type="general-purpose", ...)
   - Task(subagent_type="[domain-specific]", ...)
   ```

3. **Code Review Missing:**
   ```
   Launch code-reviewer immediately:
   - Task(subagent_type="code-reviewer", description="Review recent changes", ...)
   ```

4. **Memory MCP Not Used:**
   ```
   Search and store in Memory MCP:
   - mcp__memory__search_nodes --query "[relevant topic]"
   - mcp__memory__create_entities (store findings)
   ```

---

## 📊 WORKFLOW ACCOUNTABILITY & SELF-AUDIT

**Mandatory self-check intervals: Every 30 minutes during active work**

### **Session Start Checklist**

**Before beginning ANY work session:**

```
✅ SESSION START VERIFICATION (Required):

[ ] TodoWrite created with Research → Plan → Implement phases
[ ] Memory MCP searched for related work (mcp__memory__search_nodes)
[ ] Minimum 2 agents identified for parallel launch
[ ] Code-reviewer planned if code changes expected
[ ] No time pressure or rushing detected
[ ] User request fully understood (not making assumptions)

⚠️ Cannot start work until ALL boxes checked
```

### **Periodic Self-Check (Every 30 Minutes)**

**Set a mental timer - check every 30 minutes:**

```
🔄 WORKFLOW ADHERENCE CHECK (Every 30 min):

Current Phase: [ ] Research [ ] Plan [ ] Implement

✅ TodoWrite actively maintained and current?
✅ Agents launched and working in parallel?
✅ Memory MCP updated with recent findings?
✅ No temporary fixes or workarounds introduced?
✅ Still following Research → Plan → Implement workflow?
✅ Code review planned/completed for any code changes?

❌ If ANY box unchecked → STOP and correct immediately
```

### **End-of-Session Validation**

**Before marking task complete or ending work:**

```
✅ SESSION COMPLETION CHECKLIST:

[ ] All workflow phases completed (Research → Plan → Implement)
[ ] Code review performed on ALL code changes
[ ] All tests passing (lint, typecheck, unit tests)
[ ] Documentation updated (if applicable)
[ ] Knowledge captured in Memory MCP (lessons learned)
[ ] Changes synced to remote VMs (if applicable)
[ ] TodoWrite marked complete and archived
[ ] No temporary fixes or workarounds remain in code

⚠️ Cannot mark task complete until ALL boxes checked
```

### **Audit Questions - Use Anytime**

**Ask yourself these questions at any point:**

1. **Task Tracking:**
   - "Did I create TodoWrite before starting?" → If NO: Create it now
   - "Is TodoWrite still current and accurate?" → If NO: Update it now

2. **Agent Delegation:**
   - "Am I working alone or with agents?" → If ALONE: Delegate to agents now
   - "Did I launch minimum 2 agents in parallel?" → If NO: Launch them now

3. **Workflow Adherence:**
   - "What phase am I in: Research, Plan, or Implement?" → If UNSURE: Return to Research
   - "Did I complete previous phase fully?" → If NO: Complete it before proceeding

4. **Code Quality:**
   - "Did I code review my changes?" → If NO: Launch code-reviewer now
   - "Are all tests passing?" → If NO: Fix tests before proceeding

5. **Knowledge Management:**
   - "Did I search Memory MCP for similar work?" → If NO: Search now
   - "Did I store findings in Memory MCP?" → If NO: Store them now

### **Violation Recovery Procedure**

**When workflow violations are discovered mid-task:**

```
🔴 VIOLATION RECOVERY PROTOCOL:

1. STOP current work immediately
2. Acknowledge violation publicly (in response to user)
3. Assess violation severity:
   - Minor: Missing TodoWrite, Memory MCP search
   - Major: No agents used, no code review, temporary fixes
4. Execute recovery:
   - Minor: Create/update missing items, continue
   - Major: Return to appropriate workflow phase, restart properly
5. Document lesson learned in Memory MCP
6. Resume work only after violation fully corrected
```

### **Evidence of Proper Workflow**

**Every session should demonstrate:**

- ✅ TodoWrite usage from start to finish
- ✅ Multiple agents launched in parallel (minimum 2)
- ✅ Memory MCP entities created for findings and decisions
- ✅ Code review performed on all code changes (MANDATORY)
- ✅ All three workflow phases completed systematically
- ✅ No temporary fixes or workarounds in final code
- ✅ Knowledge captured and lessons learned documented

**If ANY item missing → Workflow violation occurred → Recovery required**

---

## Development Guidelines

**CRITICAL WORKFLOW INTEGRATION**:

- **MANDATORY WORKFLOW ADHERENCE**: ALL tasks must follow Research → Plan → Implement phases
- **ABSOLUTELY NO TEMPORARY FIXES** - See NO TEMPORARY FIXES POLICY above
- **Agent Delegation Required**: Never work alone, always use specialized agents
- **Parallel Processing Mandatory**: Launch multiple agents simultaneously
- **Memory MCP Integration**: Store all findings and decisions persistently
- **MCP Tool Utilization**: Leverage all available MCP tools for enhanced capabilities

**Implementation Standards:**
- Ignore any assumptions and reason from facts only via Research phase
- Launch multiple agents in parallel to handle different aspects of each task
- Use specialized agents and available MCP tools to find optimal solutions
- Work systematically through workflow phases, never skip or work around
- If something is not working, conduct thorough Research phase analysis
- **Timeout is not a solution** - Research and fix the underlying performance issue
- **Temporary function disable is not a solution** - Plan and implement proper fixes
- **Never work around blockers** - Research root causes and fix blocking issues first
- Missing API endpoints require Research phase to find existing alternatives
- Avoid hardcodes at all costs - Plan proper configuration management
- Do not restart processes without user consent - restarts are service disruptions
- When errors occur, Research phase must investigate all logs and trace errors completely
- Always trace errors end-to-end - frontend to backend, backend to frontend
- When installing dependencies, update install scripts for fresh deployments

### **⚡ AGENT LAUNCH PATTERNS**

**Single message with multiple parallel agents** (use for all phases):

```bash
# Research Phase Pattern
Task(subagent_type="general-purpose", description="[Analysis task]", prompt="[Details]")
Task(subagent_type="systems-architect", description="[Architecture review]", prompt="[Details]")
Task(subagent_type="[domain-expert]", description="[Specialized analysis]", prompt="[Details]")

# Plan Phase Pattern
Task(subagent_type="project-task-planner", description="[Task breakdown]", prompt="[Details]")
Task(subagent_type="systems-architect", description="[Architecture design]", prompt="[Details]")
Task(subagent_type="code-skeptic", description="[Risk analysis]", prompt="[Details]")

# Implement Phase Pattern
Task(subagent_type="senior-backend-engineer", description="[Backend work]", prompt="[Details]")
Task(subagent_type="frontend-engineer", description="[Frontend work]", prompt="[Details]")
Task(subagent_type="testing-engineer", description="[Test coverage]", prompt="[Details]")
Task(subagent_type="code-reviewer", description="[Review changes]", prompt="[Details]")
```

**See Agent Selection Matrix above for complete agent types per phase**

### **🔄 Memory MCP Integration Requirements**

**Store All Workflow Decisions:**
```bash
# Research phase findings
mcp__memory__create_entities --entities '[{"name": "Authentication Research 2025-09-29", "entityType": "research_findings", "observations": ["OAuth2 vs JWT analysis", "Security requirements identified", "3 implementation approaches evaluated"]}]'

# Planning decisions
mcp__memory__create_entities --entities '[{"name": "Authentication Plan 2025-09-29", "entityType": "implementation_plan", "observations": ["JWT selected for token management", "Backend-first implementation approach", "5 parallel implementation tracks defined"]}]'

# Implementation results
mcp__memory__add_observations --observations '[{"entityName": "Authentication Plan 2025-09-29", "contents": ["Implementation completed successfully", "All tests passing", "Security audit passed"]}]'
```

**Link Related Workflow Phases:**
```bash
# Create dependencies between workflow phases
mcp__memory__create_relations --relations '[{"from": "Authentication Research 2025-09-29", "to": "Authentication Plan 2025-09-29", "relationType": "informs"}, {"from": "Authentication Plan 2025-09-29", "to": "Authentication Implementation 2025-09-29", "relationType": "guides"}]'
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
- Hardware optimization notes
- Service health status

---

## How to Run AutoBot

**Daily startup**: `bash run_autobot.sh --dev`

**Other modes**: `bash run_autobot.sh [--prod|--dev] [--no-browser] [--desktop|--no-desktop] [--status|--stop|--restart]`

**VNC Desktop**: `http://127.0.0.1:6080/vnc.html` (enabled by default)

**Full options**: `bash run_autobot.sh --help`

---

## Monitoring & Debugging

**Health checks**:
- Backend: `curl http://localhost:8001/api/health`
- Redis: `redis-cli -h 172.16.168.23 ping`
- Logs: `tail -f logs/backend.log`

**Browser automation**: Use Browser VM (`172.16.168.25:3000`) - Playwright pre-installed. **Never install locally on Kali** (incompatible).

---

## Documentation

**Key docs**: [`docs/developer/PHASE_5_DEVELOPER_SETUP.md`](docs/developer/PHASE_5_DEVELOPER_SETUP.md) (setup) | [`docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`](docs/api/COMPREHENSIVE_API_DOCUMENTATION.md) (API) | [`docs/system-state.md`](docs/system-state.md) (status)

**All docs**: `docs/` contains api/, architecture/, developer/, features/, security/, troubleshooting/

---

## 📋 WORKFLOW QUICK REFERENCE

**🎯 Use this reference for every task - keep it visible**

### **Every Task Starts With:**

```bash
# 1. TodoWrite (MANDATORY - No exceptions)
TodoWrite:
- [ ] Research: [Problem analysis, solution research, validation]
- [ ] Plan: [Solution selection, task breakdown, validation]
- [ ] Implement: [Execution, verification, documentation]

# 2. Memory MCP Search (Check for similar past work)
mcp__memory__search_nodes --query "related topic keywords"

# 3. Launch Agents (Minimum 2 in parallel - MANDATORY)
Task(subagent_type="general-purpose", description="...", prompt="...")
Task(subagent_type="systems-architect", description="...", prompt="...")

# 4. Code Review (MANDATORY after ANY code changes)
Task(subagent_type="code-reviewer", description="Review all changes", prompt="...")
```

### **Phase Exit Criteria Quick Check:**

| Phase | Exit Criteria | Time Est. |
|-------|--------------|-----------|
| **Research** | Findings in Memory MCP, root cause known, 2-3 solutions evaluated | 15-30 min |
| **Plan** | Agent assignments made, risks identified, plan in Memory MCP | 10-20 min |
| **Implement** | Code reviewed, tests passing, documented, synced to VMs | 20-60 min |

### **Common Violation Patterns & Corrections:**

| Violation Pattern | Immediate Correction |
|------------------|---------------------|
| ❌ Working alone without agents | Launch 2+ agents in parallel RIGHT NOW |
| ❌ No TodoWrite created | Create TodoWrite with 3 phases immediately |
| ❌ Skipped Research phase | STOP - Return to Research phase |
| ❌ Code changes without review | Launch code-reviewer agent immediately |
| ❌ "Quick fix" or workaround | STOP - Research root cause instead |
| ❌ No Memory MCP search | Search mcp__memory__search_nodes now |

### **Emergency Recovery:**

```
🚨 IF WORKFLOW VIOLATED:

1. STOP work immediately
2. Create/update TodoWrite with current phase
3. Launch missing agents (minimum 2)
4. Search Memory MCP if not done
5. Complete missing workflow steps
6. Document lesson learned
7. Resume only after recovery complete
```

### **Remember:**

**Workflow is FASTER and produces BETTER results than shortcuts**

- ✅ Proper workflow prevents bugs before they happen
- ✅ Agent delegation is faster than working alone
- ✅ Code review catches issues immediately
- ✅ Memory MCP prevents duplicate work
- ✅ Research prevents wrong solutions

**Every shortcut creates 10x more work fixing the problems it causes**

---
