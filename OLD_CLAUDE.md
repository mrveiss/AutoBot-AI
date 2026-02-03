# AutoBot Development Instructions & Project Reference

This document contains development guidelines, project setup instructions, and architectural rules for the AutoBot platform.

> **📋 For system status updates and fixes, see:** [`docs/system-state.md`](docs/system-state.md)

---

## ⚡ WORKFLOW REQUIREMENTS

### **Every Task Must:**

1. **Link to GitHub Issue** - ALL work must be tied to a GitHub issue in https://github.com/mrveiss/AutoBot-AI (MANDATORY - PRIMARY task tracking)
2. **Search Memory MCP** for similar past work: `mcp__memory__search_nodes`
3. **Break down into subtasks** - Execute every task as smaller, manageable subtasks (MANDATORY)
4. **Use TodoWrite** for current session subtasks - Links to parent GitHub issue (for immediate tracking only)
5. **Use specialized agents** for complex tasks
6. **Code review is mandatory** for ALL code changes (use `code-reviewer` agent)
7. **Update GitHub Issue** with progress comments throughout work
8. **Complete GitHub Issue properly** - Issue is ONLY done when: all code committed, acceptance criteria met, issue closed with summary (MANDATORY)
9. **Store in Memory MCP** - At session end, store conversation/decisions/findings (MANDATORY)

### **Workflow Violation Self-Check**

**Before proceeding, verify:**

- ❓ **Is this work tied to a GitHub issue in https://github.com/mrveiss/AutoBot-AI?** → If NO: Create issue first or link to existing
- ❓ **Did I create TodoWrite?** → If NO: Create it now
- ❓ **Did I break down the task into subtasks?** → If NO: Break it down now
- ❓ **Am I working alone on complex tasks?** → If YES: Delegate to agents
- ❓ **Will I modify code without review?** → If YES: Plan code-reviewer agent
- ❓ **Did I search Memory MCP?** → If NO: Search now
- ❓ **Am I considering a "quick fix"?** → If YES: STOP - Fix root cause instead
- ❓ **Does this feature need frontend/backend integration?** → If YES: Plan BOTH sides before implementing

**At session end, verify:**

- ❓ **Did I store conversation in Memory MCP?** → If NO: Store it now before ending
- ❓ **Did I document decisions with rationale?** → If NO: Create decision entities
- ❓ **Did I link problems to solutions?** → If NO: Create relationships

**Before marking issue complete, verify:**

- ❓ **Is ALL code committed?** → If NO: Commit all changes with issue reference
- ❓ **Are ALL acceptance criteria met?** → If NO: Complete remaining work or update issue
- ❓ **Did I add closing summary to issue?** → If NO: Add summary of changes made
- ❓ **Is the issue closed?** → If NO: Close it now with proper status

**If ANY answer reveals violation → STOP and correct immediately**

---

## 👤 CODE OWNERSHIP & AUTHORSHIP (MANDATORY)

**⚠️ MANDATORY RULE: MRVEISS IS THE SOLE OWNER AND AUTHOR OF ALL CODE**

### **Ownership Declaration:**

- **mrveiss** is the **SOLE OWNER** of all AutoBot code
- **mrveiss** is the **SOLE AUTHOR** of all AutoBot code
- **NO OTHER NAMES** may appear as code owners or authors
- This applies to **ALL FILES** - Python, TypeScript, Vue, Scripts, Configuration, Documentation

### **Implementation Requirements:**

**File Headers:**
```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

**Commit Messages:**
```bash
# Author field must always be mrveiss
git config user.name "mrveiss"
git config user.email "mrveiss@example.com"
```

**Documentation:**
```markdown
**Author**: mrveiss
**Copyright**: © 2025 mrveiss
```

### **❌ FORBIDDEN:**

- **Other names in author fields** - Only mrveiss permitted
- **Shared ownership claims** - mrveiss is sole owner
- **Generic/anonymous authorship** - Must attribute to mrveiss
- **Organization names as authors** - Individual author is mrveiss
- **AI/tool credits as authors** - Tools assist, mrveiss authors

### **Why This Matters:**

- **Legal clarity** - Unambiguous code ownership
- **Intellectual property** - Clear IP rights
- **Project continuity** - Single authoritative owner
- **Attribution accuracy** - Proper credit to creator

**THIS IS AN UNBREAKABLE RULE - NO EXCEPTIONS, NO CIRCUMSTANCES WHERE THIS CHANGES**

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

## 📏 FUNCTION LENGTH STANDARDS (MANDATORY)

**⚠️ MANDATORY RULE: KEEP FUNCTIONS UNDER 50 LINES**

### **The Problem with Long Functions:**

- **Hard to understand** - Large functions require excessive mental load
- **Hard to test** - Multiple responsibilities make unit testing difficult
- **Hard to maintain** - Changes risk unintended side effects
- **Hard to reuse** - Tightly coupled logic can't be shared
- **Code smell** - Often indicates violation of Single Responsibility Principle

### **Line Length Limits:**

| Severity | Lines | Action Required |
|----------|-------|-----------------|
| ✅ Good | ≤30 | Ideal function length |
| ⚠️ Warning | 31-50 | Consider refactoring |
| 🔴 Violation | 51-65 | Must refactor before merge |
| ❌ Critical | >65 | Immediate refactoring required |

### **✅ CORRECT Approach - Extract Method Pattern:**

When a function exceeds 50 lines, use **Extract Method** refactoring:

```python
# ❌ BAD - Long function with multiple responsibilities
def process_data(data):
    # 80+ lines of validation, transformation, and storage
    ...

# ✅ GOOD - Extracted helper functions
def _validate_data(data: dict) -> bool:
    """Validate input data structure."""
    ...

def _transform_data(data: dict) -> dict:
    """Transform data to required format."""
    ...

def _store_data(data: dict) -> str:
    """Store processed data and return ID."""
    ...

def process_data(data: dict) -> str:
    """Process data through validation, transformation, and storage."""
    if not _validate_data(data):
        raise ValueError("Invalid data")
    transformed = _transform_data(data)
    return _store_data(transformed)
```

### **Extraction Guidelines:**

1. **Identify logical blocks** - Find code that does one specific thing
2. **Name descriptively** - Helper names should describe what they do
3. **Use underscore prefix** - Private helpers start with `_`
4. **Add docstrings** - Include "Issue #XXX: Extracted from..." reference
5. **Keep related code together** - Group helpers near their parent function

### **Docstring Template for Extracted Helpers:**

```python
def _helper_function(args):
    """Brief description of what this helper does.

    Issue #XXX: Extracted from parent_function to reduce function length.

    Args:
        args: Description of arguments

    Returns:
        Description of return value
    """
```

### **When to Extract:**

- **Nested loops** - Extract inner loop logic
- **Conditional blocks** - Extract complex if/else branches
- **Data transformations** - Extract mapping/filtering operations
- **Validation logic** - Extract validation into dedicated helpers
- **Initialization code** - Extract setup/configuration logic
- **Cleanup code** - Extract resource cleanup

### **❌ FORBIDDEN:**

- **Functions >65 lines** - Must be refactored immediately
- **Nested functions >30 lines** - Extract to module-level helpers
- **Ignoring length warnings** - Address during development, not later
- **"I'll refactor later"** - Refactor NOW, before commit

### **Pre-Commit Enforcement:**

A function length check runs as part of the pre-commit validation:
- Functions >65 lines will trigger warnings
- Address all warnings before committing
- Use `python scripts/analyze_function_lengths.py` to check

**THIS POLICY PREVENTS TECHNICAL DEBT FROM ACCUMULATING - NO EXCEPTIONS**

---

## 📛 FILE NAMING STANDARDS (MANDATORY)

**⚠️ MANDATORY RULE: NO TEMPORARY OR VERSIONED FILE NAMES**

### **Forbidden File Naming Patterns:**

**NEVER use these suffixes or patterns in filenames:**
- `_fix`, `_fixed`, `_fix2`
- `_v2`, `_v3`, `_version2`
- `_optimized`, `_improved`, `_better`
- `_new`, `_old`, `_legacy`
- `_temp`, `_tmp`, `_backup`
- `_copy`, `_draft`, `_test` (except in test directories)
- `_updated`, `_revised`, `_refactored`
- Any date-based suffixes: `_20250113`, `_jan2025`

### **Why This Matters:**

- **Version control exists for versions** - Use git, not filenames
- **Creates confusion** - Which file is the "real" one?
- **Indicates poor practices** - Suggests incomplete refactoring
- **Violates "No Temporary Fixes" policy** - Implies temporary solution
- **Breaks imports** - Other files may still reference old names

### **✅ CORRECT Approach:**

```bash
# ✅ GOOD - Permanent, descriptive names
config.py
user_service.py
authentication_handler.py
network_constants.py

# ❌ BAD - Temporary/versioned names
config_v2.py
user_service_fixed.py
authentication_handler_optimized.py
network_constants_new.py
```

### **🔧 When Refactoring:**

1. **Rename the file properly** - Use meaningful, permanent name
2. **Update all imports** - Fix all references in one commit
3. **Delete old file** - Don't leave both versions
4. **Commit atomically** - Rename + import updates in single commit

### **Exception:**

- Test files in `tests/` may use descriptive suffixes like `_unit_test.py`, `_integration_test.py`
- This is acceptable as it indicates test type, not version

**IF YOU FIND FILES WITH THESE PATTERNS → RENAME THEM IMMEDIATELY**

**THIS POLICY APPLIES TO ALL FILES: Python, TypeScript, Vue, Config, Scripts - NO EXCEPTIONS**

---

## 🔄 CONSOLIDATION & REFACTORING STANDARDS (MANDATORY)

**⚠️ MANDATORY RULE: PRESERVE ALL FEATURES, CHOOSE BEST IMPLEMENTATION**

### **The Consolidation Principle:**

When consolidating duplicate code, config systems, or competing implementations:

**1. PRESERVE ALL FEATURES** ✅
- **Never lose functionality** during consolidation
- **Inventory all features** from all implementations being merged
- **Create feature checklist** to verify nothing is lost
- **Test all features** after consolidation

**2. CHOOSE BEST IMPLEMENTATION** ✅
- **Analyze all approaches** objectively
- **Select superior patterns** based on:
  - Code quality and maintainability
  - Performance characteristics
  - Type safety and error handling
  - Consistency with project standards
  - Test coverage
- **Document why** you chose specific implementation

**3. MIGRATE SYSTEMATICALLY** ✅
- **Plan migration** with clear steps
- **Update all references** atomically
- **Remove old implementations** only after verification
- **Commit atomically** - consolidation + all updates together

### **❌ FORBIDDEN During Consolidation:**

- **Dropping features** to make consolidation "easier"
- **Keeping both implementations** indefinitely (choose one!)
- **Choosing inferior approach** for convenience
- **Partial migrations** that leave broken references
- **Undocumented decisions** about which approach won

### **✅ CORRECT Consolidation Process:**

```bash
# Example: Consolidating 3 config systems into 1

# Step 1: Inventory features
- List all features from config.py
- List all features from unified_config.py
- List all features from config_helper.py
- Create combined feature matrix

# Step 2: Choose best base
- Analyze code quality of each
- Select unified_config.py (best architecture)
- Document: "Chosen for type safety + validation framework"

# Step 3: Add missing features
- Port feature X from config.py
- Port feature Y from config_helper.py
- Verify all features present in unified_config.py

# Step 4: Migrate systematically
- Update all imports to unified_config.py
- Test each migration
- Remove old files only when all references updated

# Step 5: Verify
- Run full test suite
- Check all features work
- Confirm no regressions
```

### **Feature Preservation Checklist:**

Before consolidation:
- ✓ Documented all features from all implementations
- ✓ Analyzed which implementation is best
- ✓ Created migration plan
- ✓ Identified all code using old implementations

During consolidation:
- ✓ Ported all features to chosen implementation
- ✓ Updated all imports/references
- ✓ Tests pass for all features

After consolidation:
- ✓ No features lost
- ✓ Old implementations removed
- ✓ Documentation updated
- ✓ Team aware of changes

**THIS POLICY PREVENTS REGRESSION AND ENSURES QUALITY IMPROVEMENTS, NOT FEATURE LOSS**

---

## 🔗 GITHUB ISSUE TRACKING (MANDATORY)

**⚠️ MANDATORY RULE: ALL WORK MUST BE TIED TO GITHUB ISSUE OR TASK**

**📍 Repository: https://github.com/mrveiss/AutoBot-AI**

### **The Traceability Principle:**

Every task, change, feature, or fix MUST be linked to a GitHub issue or task for:
- **Traceability** - Know why every change was made
- **Project Management** - Track progress and priorities
- **Documentation** - Automatic history of decisions
- **Collaboration** - Team visibility into work

### **✅ CORRECT Workflow:**

```bash
# Step 1: Check for existing issue in https://github.com/mrveiss/AutoBot-AI
- Search GitHub issues for related work
- If exists: Link to it
- If not: Create new issue in the repository

# Step 2: Reference in work
- Mention issue number in commits: "feat: Add config consolidation (#123)"
- Reference in PR description: "Closes #123"
- Link in documentation updates

# Step 3: Update issue throughout work
- Mark as "In Progress" when starting
- Add comments for decisions/blockers
- Update with progress regularly

# Step 4: Close issue ONLY when complete
- ALL code changes committed to repository
- ALL acceptance criteria verified and met
- Add closing comment with summary of what was done
- Close the issue with final status
```

### **Issue Completion Criteria (MANDATORY):**

**⚠️ An issue is ONLY complete when ALL of the following are true:**

1. **All code committed** - Every change is committed to the repository with proper commit messages referencing the issue
2. **Acceptance criteria met** - All requirements listed in the issue are verified as working
3. **Tests passing** - All relevant tests pass (if applicable)
4. **Code reviewed** - Changes have been reviewed via code-reviewer agent
5. **Issue updated** - Final comment added summarizing what was done
6. **Issue closed** - Issue status changed to closed

**❌ An issue is NOT complete if:**
- Code exists only locally (not committed)
- Some acceptance criteria are unverified
- Tests are failing or skipped
- No closing summary provided
- Issue left open

**Closing Comment Format:**
```markdown
## Completed ✅

### Changes Made:
- [List of changes made]

### Acceptance Criteria Verified:
- [x] Criterion 1 - verified by [method]
- [x] Criterion 2 - verified by [method]

### Commits:
- abc1234: feat(scope): description
- def5678: fix(scope): description
```

### **Issue Requirements:**

**Every issue should have:**
- ✅ **Clear title** - Descriptive, actionable
- ✅ **Description** - What needs to be done and why
- ✅ **Labels** - Type (bug, feature, refactor), priority
- ✅ **Assignee** - Who's working on it
- ✅ **Milestone** - Which release/sprint (if applicable)

**Before starting work:**
1. Verify issue exists and is assigned to you
2. Understand the requirements completely
3. Ask questions in issue comments if unclear
4. Link issue number in TodoWrite for tracking

### **Commit Message Format:**

```bash
# Use conventional commits with issue reference
<type>(scope): <description> (#issue-number)

# Examples:
feat(config): Consolidate 5 config systems into unified_config (#156)
fix(redis): Correct timeout handling in get_redis_client (#157)
refactor(components): Migrate 21 components to BaseButton (#158)
docs(api): Update configuration documentation (#159)
```

### **❌ FORBIDDEN:**

- **Starting work without an issue** - Always create/link first
- **Vague issue titles** - "Fix stuff" or "Update code"
- **No issue reference in commits** - Breaks traceability
- **Closing issues without verification** - Must be tested/merged
- **Working on unassigned issues** - Coordinate to avoid conflicts

### **Exception:**

- **Emergency hotfixes** may be committed first, issue created immediately after
- Issue MUST be created within same work session
- Reference issue in follow-up commit

**IF YOU START WORK WITHOUT AN ISSUE → CREATE ONE IMMEDIATELY IN https://github.com/mrveiss/AutoBot-AI**

**THIS POLICY ENSURES COMPLETE PROJECT TRACEABILITY AND TEAM COORDINATION**

---

## 🚫 HARDCODING PREVENTION (AUTOMATED ENFORCEMENT)

**⚠️ MANDATORY RULE: NO HARDCODED VALUES - USE SSOT CONFIG**

**What constitutes hardcoding:**
- IP addresses (use `config.backend.host` or SSOT env vars)
- Port numbers (use `config.backend.port` or SSOT env vars)
- LLM model names (use `config.llm.default_model` or `AUTOBOT_DEFAULT_LLM_MODEL`)
- URLs (use `getBackendUrl()` or SSOT config)
- API keys, passwords, secrets (use environment variables, NEVER commit)

**SSOT Configuration Pattern:**
```python
# Python - Use SSOT config
from src.config.ssot_config import config
redis_host = config.redis.host
```

```typescript
// TypeScript - Use SSOT config
import { getConfig, getBackendUrl } from '@/config/ssot-config'
const apiUrl = getBackendUrl()
```

```bash
# Shell - Load .env and use fallbacks
source "$PROJECT_ROOT/.env"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
```

**Pre-commit hook**: Automatically scans for violations before every commit
```bash
# Runs automatically on git commit
./scripts/detect-hardcoded-values.sh
```

👉 **Full guide**: [`docs/developer/HARDCODING_PREVENTION.md`](docs/developer/HARDCODING_PREVENTION.md)
👉 **SSOT Config Guide**: [`docs/developer/SSOT_CONFIG_GUIDE.md`](docs/developer/SSOT_CONFIG_GUIDE.md)
👉 **Migration Checklist**: [`docs/developer/CONFIG_MIGRATION_CHECKLIST.md`](docs/developer/CONFIG_MIGRATION_CHECKLIST.md)

---

## 🔴 REDIS CLIENT USAGE (MANDATORY PATTERN)

**⚠️ MANDATORY RULE: ALWAYS USE CANONICAL REDIS UTILITY**

**Canonical pattern**: `src/utils/redis_client.py::get_redis_client()`

```python
# ✅ CORRECT - Use canonical utility (uses SSOT config internally)
from src.utils.redis_client import get_redis_client

# Get synchronous client for 'main' database
redis_client = get_redis_client(async_client=False, database="main")

# Get async client for 'knowledge' database
async_redis = await get_redis_client(async_client=True, database="knowledge")

# ❌ FORBIDDEN - Direct instantiation with hardcoded values
import redis
client = redis.Redis(host="172.16.168.23", port=6379, db=0)  # NEVER DO THIS
```

**Use named databases** (self-documenting):

- `main` - General cache/queues
- `knowledge` - Knowledge base vectors
- `prompts` - LLM prompts/templates
- `analytics` - Analytics data

👉 **Full guide**: [`docs/developer/REDIS_CLIENT_USAGE.md`](docs/developer/REDIS_CLIENT_USAGE.md)
👉 **SSOT Config Guide**: [`docs/developer/SSOT_CONFIG_GUIDE.md`](docs/developer/SSOT_CONFIG_GUIDE.md)

---

## 📝 UTF-8 ENCODING (MANDATORY STANDARD)

**⚠️ MANDATORY RULE: ALWAYS USE UTF-8 ENCODING EXPLICITLY**

**Canonical utilities**: `src/utils/encoding_utils.py`

### Why UTF-8 Matters

- ✅ Prevents ANSI escape codes bleeding (terminal control sequences)
- ✅ Proper box-drawing characters (terminal prompts: ┌──, └─)
- ✅ Emoji support in UI and responses
- ✅ International text (Cyrillic, Chinese, Arabic, etc.)
- ✅ Consistent JSON serialization

### Quick Reference

```python
# ✅ CORRECT - File I/O with UTF-8
from src.utils.encoding_utils import async_read_utf8_file, async_write_utf8_file

content = await async_read_utf8_file("path/to/file.txt")
await async_write_utf8_file("path/to/file.txt", content)

# ✅ CORRECT - JSON with UTF-8 (no ASCII escaping)
from src.utils.encoding_utils import json_dumps_utf8

json_str = json_dumps_utf8({"emoji": "🤖"})  # Not escaped to \ud83e\udd16

# ✅ CORRECT - FastAPI responses
from fastapi.responses import JSONResponse

return JSONResponse(
    content={"message": "Hello 🤖"},
    media_type="application/json; charset=utf-8"
)

# ✅ CORRECT - Terminal output stripping
from src.utils.encoding_utils import strip_ansi_codes

clean_text = strip_ansi_codes(terminal_output)
```

### Critical Rules

- **File I/O**: Always use `encoding='utf-8'` parameter
- **aiofiles**: Always specify `encoding='utf-8'`
- **FastAPI**: Always set `media_type="application/json; charset=utf-8"`
- **JSON**: Always use `ensure_ascii=False`
- **subprocess**: Always decode with UTF-8: `text=True, encoding='utf-8'`

👉 **Full guide**: [`docs/developer/UTF8_ENFORCEMENT.md`](docs/developer/UTF8_ENFORCEMENT.md)

---

## 📊 LOGGING STANDARDS (MANDATORY)

**⚠️ MANDATORY RULE: USE STRUCTURED LOGGING, NOT console.*/print()**

### Quick Reference

**Frontend (Vue/TypeScript):**
```typescript
import { createLogger } from '@/utils/debugUtils'
const logger = createLogger('ComponentName')

logger.debug('Detailed info', data)   // Dev only
logger.info('Normal operation')       // Normal events
logger.warn('Warning', context)       // Recovered issues
logger.error('Error occurred', error) // Failures
```

**Backend (Python):**
```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Detailed: %s", data)           # Dev only
logger.info("Normal operation")               # Normal events
logger.warning("Warning: %s", context)        # Recovered issues
logger.error("Error: %s", e, exc_info=True)   # Failures with stack trace
```

### Pre-commit Enforcement

A pre-commit hook blocks new console.*/print() statements. Bypass with `--no-verify` (NOT recommended).

### Acceptable Exceptions

- `if __name__ == "__main__":` blocks (test/demo code)
- CLI tools with intentional user output
- Logger implementation itself (debugUtils.ts)
- RUM/monitoring tools that need console output

👉 **Full guide**: [`docs/developer/LOGGING_STANDARDS.md`](docs/developer/LOGGING_STANDARDS.md)

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

**⚠️ MANDATORY RULE: ALL WORK MUST BE TRACKED IN GITHUB ISSUES**

### **Task Tracking Hierarchy:**

**1. GitHub Issues - PRIMARY task tracking (MANDATORY)**
- **ALL work** must be tied to a GitHub issue in https://github.com/mrveiss/AutoBot-AI
- Issues provide traceability, project management, and collaboration
- **NEVER start work without a GitHub issue**
- Update issue comments with progress and decisions

**2. TodoWrite - Immediate/short-term tracking only**
- **Use ONLY during active work sessions** to track subtasks
- Helps manage current workflow and subtask execution
- **NOT a replacement for GitHub issues**
- All TodoWrite tasks must link to a parent GitHub issue

**3. Memory MCP - Persistent storage of findings/decisions**
- Store conversations, decisions, and findings at session end
- Create relationships between problems and solutions
- Search before starting work to learn from past work

### **Workflow Example:**

```bash
# 1. Check GitHub issue exists (REQUIRED)
gh issue view 156

# 2. Add progress comment to GitHub issue
gh issue comment 156 --body "Starting work on LoggingSettings.vue"

# 3. Use TodoWrite for current session subtasks
TodoWrite: [
  "Issue #156: Fix LoggingSettings.vue (12 errors)",
  "Add typed event handlers",
  "Run type-check verification"
]

# 4. Update GitHub issue when complete
gh issue comment 156 --body "LoggingSettings.vue: 12 → 0 errors ✅"

# 5. Store findings in Memory MCP at session end
mcp__memory__create_entities --entities '[...]'
```

### **Memory MCP Commands:**

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

👉 **Complete Memory Storage Guide**: [`docs/developer/MEMORY_STORAGE_ROUTINE.md`](docs/developer/MEMORY_STORAGE_ROUTINE.md)

---

## 🔄 SUBTASK EXECUTION (MANDATORY)

**⚠️ MANDATORY RULE: EVERY TASK MUST BE EXECUTED AS SUBTASKS**

### **The Subtask Principle:**

- **All tasks MUST be broken down** into smaller, atomic subtasks
- **Execute ONE subtask at a time** - Complete fully before moving to next
- **Track each subtask** in TodoWrite with clear status
- **Never execute monolithic tasks** - Always decompose first

### **Workflow:**

1. **Receive Task** - Understand the overall goal
2. **Break Down** - Decompose into 3-10 smaller subtasks
3. **Create TodoWrite** - List all subtasks with clear descriptions
4. **Execute Sequentially** - Complete one subtask fully before next
5. **Mark Progress** - Update TodoWrite after each subtask completion
6. **Verify Completion** - Ensure each subtask is truly done

### **Subtask Guidelines:**

Each subtask should be:
- **Atomic** - Single, well-defined action
- **Testable** - Clear success criteria
- **Independent** - Can be executed without waiting on other tasks (when possible)
- **Trackable** - Can mark as in_progress/completed in TodoWrite

**Even "simple" tasks need 2-3 subtasks minimum** (research, implement, test, review)

**THIS POLICY ENSURES QUALITY, TRACKING, AND PREVENTS SKIPPED STEPS - NO EXCEPTIONS**

---

## 🔗 FRONTEND/BACKEND INTEGRATION CHECK (MANDATORY)

**⚠️ MANDATORY RULE: NEVER FORGET THE OTHER SIDE OF INTEGRATIONS**

### **The Integration Principle:**

When building features that involve **both frontend and backend**, you MUST:

1. **Identify integration requirements BEFORE implementing**
2. **Plan BOTH sides** (API endpoints + frontend consumption)
3. **Implement BOTH sides** in the same task/issue
4. **Test the FULL flow** end-to-end

### **Integration Checklist:**

**Before starting a feature, ask:**
- ❓ **Does this feature need a backend API?** → Plan the endpoint
- ❓ **Does this feature need frontend UI?** → Plan the component
- ❓ **Does this connect frontend to backend?** → Plan BOTH together
- ❓ **Are there existing APIs to consume?** → Check backend first
- ❓ **Are there existing components to update?** → Check frontend first

### **Common Integration Patterns:**

| Feature Type | Backend Needed | Frontend Needed |
|-------------|----------------|-----------------|
| New data display | ✅ API endpoint | ✅ Component + API call |
| Form submission | ✅ POST endpoint | ✅ Form + submit handler |
| Settings/Config | ✅ GET/PUT endpoints | ✅ Settings UI |
| Real-time updates | ✅ WebSocket/SSE | ✅ Event listeners |
| File upload | ✅ Upload endpoint | ✅ File input + progress |

### **❌ FORBIDDEN:**

- **Building backend API without frontend consumption** (orphaned endpoints)
- **Building frontend UI without backend support** (broken features)
- **Assuming "someone else" will do the other side** (you must do both)
- **Closing issues with only half the integration** (incomplete work)

### **✅ CORRECT Workflow:**

```bash
# Example: Adding a new "Export Report" feature

# Step 1: Plan BOTH sides
- Backend: POST /api/reports/export endpoint
- Frontend: Export button + download handler

# Step 2: Implement backend first
- Create endpoint in backend/api/reports.py
- Add proper response format (JSON/file download)
- Test with curl/Postman

# Step 3: Implement frontend
- Add export button to ReportsView.vue
- Add API call in useApi.ts
- Handle loading/error states

# Step 4: Test full integration
- Click button → API call → File downloads
- Verify error handling works
- Test edge cases
```

### **Integration Verification:**

Before marking a feature complete:
- [ ] Backend endpoint exists and works (test with curl)
- [ ] Frontend calls the endpoint correctly
- [ ] Error states are handled on both sides
- [ ] Loading states show appropriate feedback
- [ ] Success flow works end-to-end

**THIS POLICY PREVENTS ORPHANED CODE AND BROKEN FEATURES - NO EXCEPTIONS**

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

👉 **Full guide**: [`docs/developer/INFRASTRUCTURE_DEPLOYMENT.md`](docs/developer/INFRASTRUCTURE_DEPLOYMENT.md)

---

## Architecture Notes

### Service Layout - Distributed VM Infrastructure

| Service | IP:Port | Purpose |
|---------|---------|---------|
| **Main Machine (WSL)** | 172.16.168.20:8001 | Backend API + VNC Desktop (6080) |
| **VM1 Frontend** | 172.16.168.21:5173 | Web interface (SINGLE FRONTEND SERVER) |
| **VM2 NPU Worker** | 172.16.168.22:8081 | Hardware AI acceleration |
| **VM3 Redis** | 172.16.168.23:6379 | Data layer |
| **VM4 AI Stack** | 172.16.168.24:8080 | AI processing |
| **VM5 Browser** | 172.16.168.25:3000 | Web automation (Playwright) |

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

- [ ] Did I start without TodoWrite? → Create it now
- [ ] Did I break down task into subtasks? → Break it down now
- [ ] Am I working alone on complex tasks? → Delegate to agents
- [ ] Am I about to modify code? → Plan code-reviewer agent
- [ ] Have I searched Memory MCP? → Search before proceeding
- [ ] Am I considering a "quick fix"? → STOP - Fix root cause
- [ ] Did I skip analysis for complex problems? → Use code-skeptic or systems-architect with R→P→I
- [ ] Does this feature need frontend/backend integration? → Plan BOTH sides before implementing

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

**Technical guides**:
- [`docs/developer/HARDCODING_PREVENTION.md`](docs/developer/HARDCODING_PREVENTION.md) - No hardcoded values policy
- [`docs/developer/REDIS_CLIENT_USAGE.md`](docs/developer/REDIS_CLIENT_USAGE.md) - Redis client patterns
- [`docs/developer/UTF8_ENFORCEMENT.md`](docs/developer/UTF8_ENFORCEMENT.md) - UTF-8 encoding requirements
- [`docs/developer/INFRASTRUCTURE_DEPLOYMENT.md`](docs/developer/INFRASTRUCTURE_DEPLOYMENT.md) - VM infrastructure & deployment

**All docs**: `docs/` contains api/, architecture/, developer/, features/, security/, troubleshooting/

---

## 📋 QUICK REFERENCE

### **Task Start Checklist**

```bash
# 1. GitHub Issue (MANDATORY - PRIMARY task tracking)
gh issue view <issue-number>  # Verify issue exists
gh issue comment <issue-number> --body "Starting work on..."

# 2. Memory MCP Search
mcp__memory__search_nodes --query "relevant keywords"

# 3. TodoWrite (for current session subtasks only)
TodoWrite: [
  "Issue #<number>: Main task description",
  "Subtask 1",
  "Subtask 2"
]

# 4. Agent Delegation (for complex tasks)
Task(subagent_type="appropriate-agent", description="...", prompt="...")

# 5. Code Review (MANDATORY for code changes)
Task(subagent_type="code-reviewer", description="Review changes", prompt="...")

# 6. Update GitHub Issue when complete
gh issue comment <issue-number> --body "Task complete ✅"
```

### **Critical Policies**

| Policy | Rule |
|--------|------|
| **Code Ownership** | ✅ MANDATORY - mrveiss is SOLE OWNER and AUTHOR of ALL code (UNBREAKABLE) |
| **GitHub Issue Tracking** | ✅ MANDATORY - ALL work must be tied to GitHub issue/task in https://github.com/mrveiss/AutoBot-AI |
| **Issue Completion** | ✅ MANDATORY - Issue ONLY done when: code committed, acceptance criteria met, issue closed with summary |
| **Temporary Fixes** | ❌ NEVER - Always fix root causes (NO EXCEPTIONS) |
| **Function Length** | ✅ MANDATORY - Keep functions under 50 lines, >65 lines requires immediate refactoring |
| **File Naming** | ❌ FORBIDDEN - No _fix, _v2, _optimized, _new, _temp suffixes |
| **Consolidation** | ✅ MANDATORY - Preserve ALL features, choose BEST implementation |
| **Subtask Execution** | ✅ MANDATORY - Break down every task into subtasks |
| **Memory Storage** | ✅ MANDATORY - Store conversations/decisions at session end |
| **Process Control** | ⚠️ ALWAYS ask user approval before start/stop/restart |
| **TodoWrite** | ✅ Use for immediate session tracking - NOT a replacement for GitHub issues |
| **Code Review** | ✅ MANDATORY for all code changes |
| **UTF-8 Encoding** | ✅ MANDATORY - Always specify encoding='utf-8' explicitly |
| **Frontend Server** | ⚠️ ONLY on VM1 (172.16.168.21:5173) |
| **Remote VM Edits** | ❌ FORBIDDEN - Edit locally, sync immediately |
| **Blockers** | 🔧 Fix blockers first, never work around them |
| **R→P→I Workflow** | ⚠️ ONLY for code-skeptic and systems-architect agents |
| **Frontend/Backend Integration** | ✅ MANDATORY - Plan and implement BOTH sides of integrations |

### **Workflow Violations - Self Check**

**Before starting work:**
- Is this work tied to a GitHub issue in https://github.com/mrveiss/AutoBot-AI? ✓ (MANDATORY)
- Did I add a comment to the GitHub issue noting I'm starting? ✓

**During work:**
- Did I create TodoWrite for current session subtasks? ✓
- Did I break down task into subtasks? ✓
- Did I search Memory MCP? ✓
- Am I using agents for complex tasks? ✓
- Will code be reviewed? ✓
- Am I fixing root cause (not workaround)? ✓
- Did I use permanent file names (no _fix, _v2, _temp)? ✓
- Are my functions under 50 lines? (>65 requires immediate refactoring) ✓
- If consolidating: Did I preserve ALL features and choose BEST implementation? ✓
- Did I update GitHub issue with progress? ✓
- If feature needs integration: Did I implement BOTH frontend AND backend? ✓

**Before marking issue complete (MANDATORY):**
- Is ALL code committed with issue references? ✓
- Are ALL acceptance criteria verified and met? ✓
- Did I add closing summary to GitHub issue? ✓
- Is the GitHub issue closed? ✓

**At session end:**
- Did I update GitHub issue with final results? ✓ (MANDATORY)
- Did I store conversation in Memory MCP? ✓
- Did I document decisions with rationale? ✓
- Did I link problems to solutions? ✓

**If ANY unchecked → STOP and correct immediately**

---
