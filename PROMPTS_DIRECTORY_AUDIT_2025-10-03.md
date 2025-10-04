# Prompts Directory Comprehensive Audit Report
**Date:** 2025-10-03
**Auditor:** Claude Code (AutoBot Management Agent)
**Total Files Analyzed:** 117 files across 13 directories
**Status:** Research Phase Complete

---

## Executive Summary

The `/home/kali/Desktop/AutoBot/prompts/` directory contains a mixed collection of prompts from multiple sources:

- **AutoBot-Specific Prompts:** ~18 files (15% - actual AutoBot platform prompts)
- **Agent Zero Framework:** ~90 files (77% - imported from external agent framework)
- **Empty/Obsolete:** ~9 files (8% - test files, empty directories, Zone.Identifier artifacts)

**Critical Finding:** The prompts directory is predominantly populated with Agent Zero framework templates that are NOT being used by AutoBot's actual implementation. Only 4 prompt keys are actively referenced in the codebase.

---

## 1. Complete Inventory by Directory

### 1.1 AutoBot-Specific Directories (KEEP)

#### `/prompts/chat/` - **5 files** ✅ HIGH PRIORITY - NEWLY CREATED
**Purpose:** Specialized chat context prompts for AutoBot
**Relevance:** HIGH - Core chat functionality
**Action:** KEEP - Essential for chat system

Files:
- `system_prompt.md` (243 lines) - Main chat system prompt with conversation management
- `installation_help.md` - Installation guidance context
- `api_documentation.md` - API documentation context
- `architecture_explanation.md` - Architecture explanation context
- `troubleshooting.md` - Troubleshooting guidance context

**Integration Status:** ✅ Used by `chat_workflow_manager.py` via `get_prompt("chat.system_prompt")`

**Strengths:**
- Comprehensive conversation management rules
- Intent-based context switching
- Exit intent detection patterns
- AutoBot-specific installation/architecture guidance

---

#### `/prompts/autobot/` - **8 files** (6 actual + 2 artifacts) ✅ HIGH PRIORITY
**Purpose:** AutoBot core identity and role definitions
**Relevance:** HIGH - Defines AutoBot's identity
**Action:** KEEP - Clean up Zone.Identifier files

Files:
- `_context.md` - AutoBot platform description (35 lines)
- `agent.system.main.role.md` - AutoBot role definition (37 lines)
- `agent.system.tool.response.md` - Tool response formatting
- `system_identity_override.md` - Critical identity facts (28 lines)
- `context` - Directory or file (needs inspection)
- **3x `:Zone.Identifier` files** ❌ REMOVE

**Integration Status:** Partial - Identity definitions available but may not be actively loaded

**Cleanup Needed:**
```bash
rm prompts/autobot/*:Zone.Identifier
```

---

#### `/prompts/orchestrator/` - **2 files** ✅ MEDIUM PRIORITY
**Purpose:** AutoBot orchestrator system prompts
**Relevance:** MEDIUM - Legacy and current orchestrator prompts
**Action:** KEEP - Verify which is current, archive legacy

Files:
- `system_prompt.md` - Current orchestrator prompt (63 lines)
- `legacy_system_prompt.txt` - Legacy version (2.9KB)

**Integration Status:** ✅ Used by `llm_interface.py` via `prompt_manager.get("orchestrator.system_prompt")`

**Recommendation:**
- Keep `system_prompt.md` (actively used)
- Archive `legacy_system_prompt.txt` to `scripts/archive/prompts/`

---

### 1.2 Agent Zero Framework Directories (EVALUATE)

#### `/prompts/default/` - **74 files** ⚠️ FRAMEWORK TEMPLATES
**Purpose:** Default prompt templates from Agent Zero framework
**Relevance:** LOW - Generic agent framework, not AutoBot-specific
**Action:** EVALUATE - Most unused, some potentially adaptable

**File Categories:**
- **Agent System Prompts (25 files):** `agent.system.*` - Agent behavior, tools, memory, solving
- **Framework Messages (30 files):** `fw.*` - Message templates, warnings, summaries, errors
- **Behavior Templates (5 files):** `behaviour.*` - Search, merge, update behaviors
- **Memory Templates (4 files):** `memory.*` - Memory query and summary templates
- **Browser Agent (1 file):** `browser_agent.system.md`
- **Context Files (9 files):** Various context and configuration

**Framework Origin:** Agent Zero (open-source multi-agent framework)

**Integration Status:** ❌ NOT USED - No code references to `default.*` prompts except fallback mechanisms

**Key Observations:**
- Total: 1,782 lines of framework templates
- Template variables: `{{rules}}`, `{{name}}`, `{{message}}`, etc.
- Jinja2 formatting for dynamic content
- Designed for subordinate agent spawning (not AutoBot's architecture)

**Recommendation:**
- **Archive 90%** - Move to `scripts/archive/prompts/agent-zero-framework/`
- **Keep 5 templates** for potential adaptation:
  - `agent.system.main.role.md` - Generic agent role template
  - `agent.system.behaviour.md` - Behavioral rules template
  - `fw.user_message.md` - User message formatting
  - `fw.tool_result.md` - Tool result formatting
  - `_context.md` - Framework description

---

#### `/prompts/developer/` - **6 files** (3 actual + 3 artifacts) ⚠️ AGENT ZERO ROLE
**Purpose:** Developer specialist agent role from Agent Zero
**Relevance:** LOW - Not AutoBot's architecture
**Action:** ARCHIVE - Not being used

Files:
- `_context.md` - "agent specialized in complex software development"
- `agent.system.main.role.md` - Developer role definition
- `agent.system.main.communication.md` - Communication guidelines
- **3x `:Zone.Identifier` files** ❌ REMOVE

**Integration Status:** ❌ NOT USED

**Recommendation:** Archive to `scripts/archive/prompts/agent-zero-roles/developer/`

---

#### `/prompts/researcher/` - **6 files** (3 actual + 3 artifacts) ⚠️ AGENT ZERO ROLE
**Purpose:** Researcher specialist agent role from Agent Zero
**Relevance:** LOW - Not AutoBot's architecture
**Action:** ARCHIVE

Files:
- `_context.md` - "agent specialized in research, data analysis and reporting"
- `agent.system.main.role.md` - Researcher role definition
- `agent.system.main.communication.md` - Communication guidelines
- **3x `:Zone.Identifier` files** ❌ REMOVE

**Integration Status:** ❌ NOT USED

**Recommendation:** Archive to `scripts/archive/prompts/agent-zero-roles/researcher/`

---

#### `/prompts/hacker/` - **6 files** (3 actual + 3 artifacts) ⚠️ AGENT ZERO ROLE
**Purpose:** Security/penetration testing specialist from Agent Zero
**Relevance:** LOW - Not AutoBot's architecture
**Action:** ARCHIVE

Files:
- `_context.md` - "agent specialized in cyber security and penetration testing"
- `agent.system.main.role.md` - Hacker role definition
- `agent.system.main.environment.md` - Environment description
- **3x `:Zone.Identifier` files** ❌ REMOVE

**Integration Status:** ❌ NOT USED

**Recommendation:** Archive to `scripts/archive/prompts/agent-zero-roles/hacker/`

---

#### `/prompts/reflection/` - **6 files** ⚠️ AGENT ZERO FRAMEWORK
**Purpose:** Reflection/thinking framework from Agent Zero
**Relevance:** LOW - Alternative agent framework
**Action:** ARCHIVE

Files:
- `agent.system.main.role.md` - Minimal role ("agent zero autonomous json ai agent")
- `agent.system.main.communication.md`
- `agent.system.main.environment.md`
- `agent.system.main.solving.md`
- `agent.system.main.tips.md`
- `agent.system.behaviour.md`

**Integration Status:** ❌ NOT USED

**Recommendation:** Archive to `scripts/archive/prompts/agent-zero-framework/reflection/`

---

### 1.3 Minimal/Legacy Directories (CLEAN UP)

#### `/prompts/llm/` - **1 file** ✅ KEEP (MINIMAL)
**Purpose:** Task system prompt
**Relevance:** MEDIUM - Used by LLM interface
**Action:** KEEP - Actively used

Files:
- `task_system_prompt.txt` (6 lines) - Minimal task execution prompt

**Integration Status:** ✅ Used by `llm_interface.py` via `prompt_manager.get("llm.task_system_prompt")`

**Recommendation:** Keep as-is (minimal, functional)

---

#### `/prompts/test/` - **1 file** ❌ REMOVE
**Purpose:** Test placeholder
**Relevance:** NONE - Test artifact
**Action:** DELETE

Files:
- `test_update.md` (1 line) - "test to see if knowledge base is updated"

**Integration Status:** ❌ NOT USED

**Recommendation:** Delete - no value

---

#### `/prompts/diagnostics/` - **EMPTY** ❌ REMOVE
**Purpose:** Unknown - directory exists but empty
**Relevance:** NONE
**Action:** DELETE DIRECTORY

**Recommendation:** Remove empty directory

---

#### `/prompts/knowledge_base/` - **EMPTY** ❌ REMOVE
**Purpose:** Unknown - directory exists but empty
**Relevance:** NONE
**Action:** DELETE DIRECTORY

**Recommendation:** Remove empty directory

---

#### `/prompts/settings` - **FILE (not directory)** ⚠️ INVESTIGATE
**Status:** Listed in tree output but type unclear
**Action:** INVESTIGATE - Verify if file or directory

---

#### `/prompts/tool_interpreter_system_prompt.txt` - **1 file** ✅ KEEP
**Purpose:** Tool interpreter system prompt (root level)
**Relevance:** MEDIUM - Used by LLM interface
**Action:** KEEP - Actively used

**Integration Status:** ✅ Used by `llm_interface.py` via `prompt_manager.get("tool_interpreter_system_prompt")`

**Content:** 54 lines - JSON tool call formatting rules

**Recommendation:** Consider moving to organized directory structure

---

## 2. Code Integration Analysis

### 2.1 Actively Used Prompts (4 total)

Based on grep analysis of Python codebase:

1. **`chat.system_prompt`** ✅ ACTIVE
   - Used by: `chat_workflow_manager.py` (line 441)
   - Used by: `test_conversation_handling_fix.py` (lines 208, 221)
   - File: `/prompts/chat/system_prompt.md`
   - Purpose: Main chat system prompt with conversation management

2. **`orchestrator.system_prompt`** ✅ ACTIVE
   - Used by: `llm_interface.py` (line 340)
   - File: `/prompts/orchestrator/system_prompt.md`
   - Purpose: Orchestrator agent system prompt

3. **`llm.task_system_prompt`** ✅ ACTIVE
   - Used by: `llm_interface.py` (line 352)
   - File: `/prompts/llm/task_system_prompt.txt`
   - Purpose: Task execution prompt

4. **`tool_interpreter_system_prompt`** ✅ ACTIVE
   - Used by: `llm_interface.py` (line 364)
   - File: `/prompts/tool_interpreter_system_prompt.txt`
   - Purpose: Tool interpreter prompt

### 2.2 Context-Based Prompts (5 total)

Used by intent detection system in `chat_workflow_manager.py`:

1. `chat.installation_help` - Installation context
2. `chat.architecture_explanation` - Architecture context
3. `chat.troubleshooting` - Troubleshooting context
4. `chat.api_documentation` - API documentation context
5. `chat.system_prompt` - Default/general context

### 2.3 Unused Prompts (108 files)

- All `default/*` prompts (74 files) - Agent Zero framework
- All `developer/*` prompts (6 files) - Agent Zero role
- All `researcher/*` prompts (6 files) - Agent Zero role
- All `hacker/*` prompts (6 files) - Agent Zero role
- All `reflection/*` prompts (6 files) - Agent Zero framework
- `orchestrator/legacy_system_prompt.txt` - Replaced by .md version
- Most `autobot/*` prompts - Not actively referenced
- `test/test_update.md` - Test artifact
- Empty directories: `diagnostics/`, `knowledge_base/`

---

## 3. Zone.Identifier Files Analysis

**Total Found:** 12 files (Windows transfer artifacts)

These are NTFS alternate data stream files created when files are downloaded or transferred from Windows systems. They are NOT needed on Linux and should be removed.

**Files to Remove:**
```bash
prompts/autobot/_context.md:Zone.Identifier
prompts/autobot/agent.system.main.role.md:Zone.Identifier
prompts/autobot/agent.system.tool.response.md:Zone.Identifier
prompts/developer/_context.md:Zone.Identifier
prompts/developer/agent.system.main.communication.md:Zone.Identifier
prompts/developer/agent.system.main.role.md:Zone.Identifier
prompts/researcher/_context.md:Zone.Identifier
prompts/researcher/agent.system.main.communication.md:Zone.Identifier
prompts/researcher/agent.system.main.role.md:Zone.Identifier
prompts/hacker/_context.md:Zone.Identifier
prompts/hacker/agent.system.main.role.md:Zone.Identifier
prompts/hacker/agent.system.main.environment.md:Zone.Identifier
```

**Cleanup Command:**
```bash
find /home/kali/Desktop/AutoBot/prompts -name "*:Zone.Identifier" -delete
```

---

## 4. Categorization Summary

### Category A: AutoBot-Specific (KEEP) - 18 files
- ✅ `chat/` - 5 files (NEW, actively used)
- ✅ `autobot/` - 5 files (identity/role definitions)
- ✅ `orchestrator/` - 1 file (system_prompt.md - actively used)
- ✅ `llm/` - 1 file (task_system_prompt.txt - actively used)
- ✅ Root: `tool_interpreter_system_prompt.txt` - 1 file (actively used)

**Total Lines:** ~500 lines of actual AutoBot prompts

### Category B: Agent Zero Framework (ARCHIVE) - 90 files
- ⚠️ `default/` - 74 files (framework templates)
- ⚠️ `developer/` - 3 files (role template)
- ⚠️ `researcher/` - 3 files (role template)
- ⚠️ `hacker/` - 3 files (role template)
- ⚠️ `reflection/` - 6 files (thinking framework)
- ⚠️ `orchestrator/legacy_system_prompt.txt` - 1 file

**Total Lines:** ~2,500 lines of external framework code

### Category C: Cleanup Required (DELETE) - 9 files
- ❌ Zone.Identifier files - 12 files
- ❌ `test/` - 1 file
- ❌ Empty directories: `diagnostics/`, `knowledge_base/`

---

## 5. Integration with New Chat Prompts

### 5.1 Current Integration Status

The new `chat/` prompts are well-integrated:

**System Prompt (`chat/system_prompt.md`):**
- ✅ Loaded by `chat_workflow_manager.py` via `get_prompt("chat.system_prompt")`
- ✅ Contains comprehensive conversation management rules
- ✅ Defines exit intent detection patterns
- ✅ Provides AutoBot-specific context

**Context Prompts:**
- ✅ Loaded by intent detection: `get_prompt(context_key)` where `context_key` is:
  - `chat.installation_help`
  - `chat.architecture_explanation`
  - `chat.troubleshooting`
  - `chat.api_documentation`

### 5.2 Potential Conflicts

**No direct conflicts detected, but considerations:**

1. **Identity Definition Overlap:**
   - `chat/system_prompt.md` defines AutoBot identity
   - `autobot/agent.system.main.role.md` also defines AutoBot role
   - `autobot/system_identity_override.md` contains "CRITICAL IDENTITY OVERRIDE"

   **Recommendation:** Consolidate identity definitions or establish clear hierarchy

2. **Framework Template Confusion:**
   - `default/agent.system.main.role.md` defines generic agent role
   - Could conflict if fallback mechanisms are triggered

   **Recommendation:** Remove/archive default/ to prevent fallback confusion

3. **Multiple System Prompts:**
   - `chat/system_prompt.md` - Chat system
   - `orchestrator/system_prompt.md` - Orchestrator system
   - `default/agent.system.main.role.md` - Framework template

   **Recommendation:** Maintain clear separation with proper prompt key usage

### 5.3 Integration Quality Assessment

**Strengths:**
- ✅ Clear prompt key naming: `chat.*` prefix prevents conflicts
- ✅ Intent-based context switching implemented
- ✅ Comprehensive conversation management rules
- ✅ AutoBot-specific guidance (installation, architecture, troubleshooting)

**Weaknesses:**
- ⚠️ Large volume of unused framework templates could cause confusion
- ⚠️ Multiple identity definitions not clearly prioritized
- ⚠️ No documentation on prompt precedence/hierarchy

---

## 6. Cleanup Plan

### Phase 1: Immediate Cleanup (Safe - No Risk)

**Remove Windows Artifacts:**
```bash
# Remove all Zone.Identifier files
find /home/kali/Desktop/AutoBot/prompts -name "*:Zone.Identifier" -delete
```

**Remove Test/Empty Directories:**
```bash
# Remove test directory
rm -rf /home/kali/Desktop/AutoBot/prompts/test

# Remove empty directories
rmdir /home/kali/Desktop/AutoBot/prompts/diagnostics
rmdir /home/kali/Desktop/AutoBot/prompts/knowledge_base
```

**Expected Result:** 14 files removed, 2 empty directories removed

---

### Phase 2: Archive Agent Zero Framework (Medium Risk - Verify First)

**Create Archive Structure:**
```bash
# Create archive directory
mkdir -p /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-framework
mkdir -p /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-roles
```

**Archive Framework Templates:**
```bash
# Archive default/ framework
mv /home/kali/Desktop/AutoBot/prompts/default \
   /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-framework/

# Archive reflection/ framework
mv /home/kali/Desktop/AutoBot/prompts/reflection \
   /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-framework/

# Archive role templates
mv /home/kali/Desktop/AutoBot/prompts/developer \
   /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-roles/

mv /home/kali/Desktop/AutoBot/prompts/researcher \
   /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-roles/

mv /home/kali/Desktop/AutoBot/prompts/hacker \
   /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-roles/

# Archive legacy orchestrator
mv /home/kali/Desktop/AutoBot/prompts/orchestrator/legacy_system_prompt.txt \
   /home/kali/Desktop/AutoBot/scripts/archive/prompts/
```

**Expected Result:** 90 files archived, significantly cleaner prompts directory

**Verification Before Archiving:**
```bash
# Check for any code references to these prompts
grep -r "default\." /home/kali/Desktop/AutoBot/src/
grep -r "developer\." /home/kali/Desktop/AutoBot/src/
grep -r "researcher\." /home/kali/Desktop/AutoBot/src/
grep -r "reflection\." /home/kali/Desktop/AutoBot/src/
grep -r "hacker\." /home/kali/Desktop/AutoBot/src/
```

---

### Phase 3: Reorganize AutoBot Prompts (Low Risk - Organizational)

**Proposed New Structure:**
```
prompts/
├── core/                          # Core AutoBot prompts
│   ├── identity.md                # Consolidated AutoBot identity
│   ├── orchestrator.md            # Orchestrator system prompt
│   ├── task_executor.md           # Task execution prompt
│   └── tool_interpreter.md        # Tool interpreter prompt
│
├── chat/                          # Chat-specific prompts
│   ├── system_prompt.md           # Main chat prompt (KEEP AS-IS)
│   ├── installation_help.md       # Installation context (KEEP AS-IS)
│   ├── architecture_explanation.md # Architecture context (KEEP AS-IS)
│   ├── troubleshooting.md         # Troubleshooting context (KEEP AS-IS)
│   └── api_documentation.md       # API documentation context (KEEP AS-IS)
│
└── agents/                        # Future: AutoBot-specific agent prompts
    └── README.md                  # Documentation for agent prompt structure
```

**Migration Steps:**
1. Create `core/` directory
2. Consolidate identity from `autobot/` into `core/identity.md`
3. Move `orchestrator/system_prompt.md` to `core/orchestrator.md`
4. Move `llm/task_system_prompt.txt` to `core/task_executor.md`
5. Move `tool_interpreter_system_prompt.txt` to `core/tool_interpreter.md`
6. Update code references to new prompt keys
7. Keep `chat/` directory as-is (already well-organized)

**Code Updates Required:**
```python
# src/llm_interface.py
orchestrator_prompt_key = "core.orchestrator"  # was "orchestrator.system_prompt"
task_prompt_key = "core.task_executor"         # was "llm.task_system_prompt"
tool_prompt_key = "core.tool_interpreter"      # was "tool_interpreter_system_prompt"

# src/chat_workflow_manager.py
# No changes needed - chat.* already well-organized
```

---

### Phase 4: Documentation & Guidelines

**Create Prompt Documentation:**
```markdown
# prompts/README.md

## AutoBot Prompts Directory

### Structure

- `core/` - Core system prompts (orchestrator, task executor, tool interpreter)
- `chat/` - Chat-specific prompts with intent-based context switching
- `agents/` - Future specialized agent prompts

### Adding New Prompts

1. Choose appropriate directory based on purpose
2. Use descriptive filename (lowercase, underscore-separated)
3. Add prompt key to code using dot notation (e.g., `chat.new_context`)
4. Document in this README

### Prompt Key Convention

- Core prompts: `core.*`
- Chat prompts: `chat.*`
- Agent prompts: `agents.*`

### Currently Used Prompts

- `core.orchestrator` - Orchestrator system prompt
- `core.task_executor` - Task execution prompt
- `core.tool_interpreter` - Tool interpreter prompt
- `chat.system_prompt` - Main chat system prompt
- `chat.installation_help` - Installation guidance context
- `chat.architecture_explanation` - Architecture explanation context
- `chat.troubleshooting` - Troubleshooting guidance context
- `chat.api_documentation` - API documentation context
```

---

## 7. Recommended New Directory Structure

### After Complete Cleanup & Reorganization:

```
prompts/
├── README.md                          # Documentation (NEW)
│
├── core/                              # Core AutoBot prompts (NEW)
│   ├── identity.md                    # Consolidated identity
│   ├── orchestrator.md                # Orchestrator prompt
│   ├── task_executor.md               # Task executor prompt
│   └── tool_interpreter.md            # Tool interpreter prompt
│
├── chat/                              # Chat prompts (EXISTING - KEEP)
│   ├── system_prompt.md               # Main chat prompt
│   ├── installation_help.md           # Installation context
│   ├── architecture_explanation.md    # Architecture context
│   ├── troubleshooting.md             # Troubleshooting context
│   └── api_documentation.md           # API documentation context
│
└── agents/                            # Future agent prompts (NEW)
    └── README.md                      # Agent prompt guidelines
```

**Total Files:** ~15 files (down from 117)
**All AutoBot-Specific:** 100% relevant prompts
**No Framework Templates:** Clean, purpose-built prompts

---

## 8. Migration Script

### Automated Cleanup & Reorganization Script

```bash
#!/bin/bash
# prompts_cleanup_migration.sh
# AutoBot Prompts Directory Cleanup & Reorganization

set -e  # Exit on error

PROMPTS_DIR="/home/kali/Desktop/AutoBot/prompts"
ARCHIVE_DIR="/home/kali/Desktop/AutoBot/scripts/archive/prompts"

echo "=== AutoBot Prompts Cleanup & Migration ==="
echo "This script will:"
echo "  1. Remove Windows Zone.Identifier files"
echo "  2. Remove test files and empty directories"
echo "  3. Archive Agent Zero framework prompts"
echo "  4. Reorganize AutoBot prompts"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Phase 1: Remove Windows Artifacts
echo ""
echo "Phase 1: Removing Windows artifacts..."
find "$PROMPTS_DIR" -name "*:Zone.Identifier" -delete
echo "✓ Removed Zone.Identifier files"

# Remove test directory
if [ -d "$PROMPTS_DIR/test" ]; then
    rm -rf "$PROMPTS_DIR/test"
    echo "✓ Removed test directory"
fi

# Remove empty directories
for dir in diagnostics knowledge_base; do
    if [ -d "$PROMPTS_DIR/$dir" ]; then
        rmdir "$PROMPTS_DIR/$dir" 2>/dev/null || echo "⚠ $dir not empty, skipped"
    fi
done
echo "✓ Removed empty directories"

# Phase 2: Archive Agent Zero Framework
echo ""
echo "Phase 2: Archiving Agent Zero framework..."
mkdir -p "$ARCHIVE_DIR/agent-zero-framework"
mkdir -p "$ARCHIVE_DIR/agent-zero-roles"

# Archive framework directories
for dir in default reflection; do
    if [ -d "$PROMPTS_DIR/$dir" ]; then
        mv "$PROMPTS_DIR/$dir" "$ARCHIVE_DIR/agent-zero-framework/"
        echo "✓ Archived $dir/"
    fi
done

# Archive role directories
for dir in developer researcher hacker; do
    if [ -d "$PROMPTS_DIR/$dir" ]; then
        mv "$PROMPTS_DIR/$dir" "$ARCHIVE_DIR/agent-zero-roles/"
        echo "✓ Archived $dir/"
    fi
done

# Archive legacy orchestrator
if [ -f "$PROMPTS_DIR/orchestrator/legacy_system_prompt.txt" ]; then
    mv "$PROMPTS_DIR/orchestrator/legacy_system_prompt.txt" "$ARCHIVE_DIR/"
    echo "✓ Archived legacy_system_prompt.txt"
fi

# Phase 3: Reorganize AutoBot Prompts
echo ""
echo "Phase 3: Reorganizing AutoBot prompts..."

# Create new structure
mkdir -p "$PROMPTS_DIR/core"
mkdir -p "$PROMPTS_DIR/agents"

# Consolidate identity from autobot/
if [ -f "$PROMPTS_DIR/autobot/system_identity_override.md" ]; then
    cp "$PROMPTS_DIR/autobot/system_identity_override.md" "$PROMPTS_DIR/core/identity.md"
    echo "✓ Created core/identity.md"
fi

# Move orchestrator
if [ -f "$PROMPTS_DIR/orchestrator/system_prompt.md" ]; then
    mv "$PROMPTS_DIR/orchestrator/system_prompt.md" "$PROMPTS_DIR/core/orchestrator.md"
    rmdir "$PROMPTS_DIR/orchestrator" 2>/dev/null || true
    echo "✓ Moved orchestrator.md to core/"
fi

# Move task executor
if [ -f "$PROMPTS_DIR/llm/task_system_prompt.txt" ]; then
    mv "$PROMPTS_DIR/llm/task_system_prompt.txt" "$PROMPTS_DIR/core/task_executor.md"
    rmdir "$PROMPTS_DIR/llm" 2>/dev/null || true
    echo "✓ Moved task_executor.md to core/"
fi

# Move tool interpreter
if [ -f "$PROMPTS_DIR/tool_interpreter_system_prompt.txt" ]; then
    mv "$PROMPTS_DIR/tool_interpreter_system_prompt.txt" "$PROMPTS_DIR/core/tool_interpreter.md"
    echo "✓ Moved tool_interpreter.md to core/"
fi

# Archive remaining autobot/ files
if [ -d "$PROMPTS_DIR/autobot" ]; then
    mv "$PROMPTS_DIR/autobot" "$ARCHIVE_DIR/"
    echo "✓ Archived autobot/ directory"
fi

# Phase 4: Create Documentation
echo ""
echo "Phase 4: Creating documentation..."

cat > "$PROMPTS_DIR/README.md" << 'EOF'
# AutoBot Prompts Directory

## Structure

- `core/` - Core system prompts (orchestrator, task executor, tool interpreter, identity)
- `chat/` - Chat-specific prompts with intent-based context switching
- `agents/` - Future specialized agent prompts

## Adding New Prompts

1. Choose appropriate directory based on purpose
2. Use descriptive filename (lowercase, underscore-separated)
3. Add prompt key to code using dot notation (e.g., `chat.new_context`)
4. Document in this README

## Prompt Key Convention

- Core prompts: `core.*`
- Chat prompts: `chat.*`
- Agent prompts: `agents.*`

## Currently Used Prompts

- `core.identity` - AutoBot identity definition
- `core.orchestrator` - Orchestrator system prompt
- `core.task_executor` - Task execution prompt
- `core.tool_interpreter` - Tool interpreter prompt
- `chat.system_prompt` - Main chat system prompt
- `chat.installation_help` - Installation guidance context
- `chat.architecture_explanation` - Architecture explanation context
- `chat.troubleshooting` - Troubleshooting guidance context
- `chat.api_documentation` - API documentation context

## Archived Prompts

Agent Zero framework prompts have been archived to:
`scripts/archive/prompts/agent-zero-framework/`

See archive for legacy prompt templates if needed for reference.
EOF

echo "✓ Created prompts/README.md"

cat > "$PROMPTS_DIR/agents/README.md" << 'EOF'
# AutoBot Agent Prompts

This directory will contain prompts for specialized AutoBot agents.

## Guidelines

- Each agent should have its own subdirectory
- Use consistent naming: `agent_name/system_prompt.md`
- Include context and role definitions
- Document agent capabilities and limitations

## Future Agents

Specialized agents will be added here as AutoBot's capabilities expand.
EOF

echo "✓ Created agents/README.md"

# Summary
echo ""
echo "=== Migration Complete ==="
echo ""
echo "Summary:"
echo "  - Removed: Windows artifacts, test files, empty directories"
echo "  - Archived: Agent Zero framework (90+ files)"
echo "  - Reorganized: AutoBot prompts into core/ and chat/"
echo "  - Created: Documentation in prompts/README.md"
echo ""
echo "New structure:"
tree -L 2 "$PROMPTS_DIR" -I '__pycache__|*.pyc'
echo ""
echo "⚠ IMPORTANT: Update code references to new prompt keys:"
echo "  - orchestrator.system_prompt → core.orchestrator"
echo "  - llm.task_system_prompt → core.task_executor"
echo "  - tool_interpreter_system_prompt → core.tool_interpreter"
echo ""
echo "✓ All changes complete!"
```

---

## 9. Code Update Requirements

### Files Requiring Updates

**1. `/home/kali/Desktop/AutoBot/src/llm_interface.py`**

Update prompt key references:

```python
# BEFORE
orchestrator_prompt_key = "orchestrator.system_prompt"
task_prompt_key = "llm.task_system_prompt"
tool_interpreter_prompt_key = "tool_interpreter_system_prompt"

# AFTER
orchestrator_prompt_key = "core.orchestrator"
task_prompt_key = "core.task_executor"
tool_interpreter_prompt_key = "core.tool_interpreter"
```

**2. `/home/kali/Desktop/AutoBot/src/chat_workflow_manager.py`**

No changes needed - `chat.*` keys remain the same:
- ✅ `chat.system_prompt`
- ✅ `chat.installation_help`
- ✅ `chat.architecture_explanation`
- ✅ `chat.troubleshooting`
- ✅ `chat.api_documentation`

**3. `/home/kali/Desktop/AutoBot/tests/test_conversation_handling_fix.py`**

No changes needed - uses `chat.system_prompt`

---

## 10. Risk Assessment

### Phase 1: Immediate Cleanup - **ZERO RISK**
- Removing Zone.Identifier files: No impact on functionality
- Removing test directory: No code references
- Removing empty directories: No code references
- **Risk Level:** None ✅

### Phase 2: Archive Framework - **LOW RISK**
- No code actively uses Agent Zero framework prompts
- Fallback mechanisms in PromptManager might reference default.*
- All files preserved in archive
- **Risk Level:** Low ⚠️
- **Mitigation:** Test after archiving, easy rollback from archive

### Phase 3: Reorganize Prompts - **MEDIUM RISK**
- Requires code updates to prompt keys
- Breaking change if not updated correctly
- **Risk Level:** Medium ⚠️
- **Mitigation:**
  - Update all code references before moving files
  - Test thoroughly after changes
  - Keep backup of original structure

### Phase 4: Documentation - **ZERO RISK**
- Documentation only, no code impact
- **Risk Level:** None ✅

---

## 11. Testing Plan

### Pre-Migration Testing

```bash
# Verify current prompt loading
python3 << EOF
from src.prompt_manager import prompt_manager
print("Currently loaded prompts:")
for key in sorted(prompt_manager.list_prompts()):
    print(f"  - {key}")
EOF
```

### Post-Migration Testing

```bash
# Test Phase 1 (Cleanup)
pytest tests/test_conversation_handling_fix.py -v

# Test Phase 2 (Archive)
python3 -c "from src.prompt_manager import reload_prompts; reload_prompts()"
pytest tests/ -k chat -v

# Test Phase 3 (Reorganization)
# Update code first, then:
python3 -c "from src.llm_interface import LLMInterface; llm = LLMInterface(); print('✓ LLM loaded')"
python3 -c "from src.chat_workflow_manager import ChatWorkflowManager; print('✓ Chat loaded')"
pytest tests/ -v
```

### Validation Checklist

- [ ] All Zone.Identifier files removed
- [ ] Test directory removed
- [ ] Empty directories removed
- [ ] Agent Zero framework archived (90 files)
- [ ] Core prompts reorganized
- [ ] Code references updated
- [ ] All tests passing
- [ ] Chat functionality working
- [ ] Orchestrator loading correctly
- [ ] Tool interpreter working
- [ ] Documentation created

---

## 12. Rollback Plan

### If Issues Arise After Migration

**Phase 1 Rollback (Cleanup):**
- No rollback needed - files can be recovered from git history if needed

**Phase 2 Rollback (Archive):**
```bash
# Restore archived framework
mv /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-framework/* \
   /home/kali/Desktop/AutoBot/prompts/

mv /home/kali/Desktop/AutoBot/scripts/archive/prompts/agent-zero-roles/* \
   /home/kali/Desktop/AutoBot/prompts/

# Reload prompts
python3 -c "from src.prompt_manager import reload_prompts; reload_prompts()"
```

**Phase 3 Rollback (Reorganization):**
```bash
# Restore from git
git checkout prompts/
git checkout src/llm_interface.py

# Or restore from archive
cp -r /home/kali/Desktop/AutoBot/scripts/archive/prompts-backup/* \
      /home/kali/Desktop/AutoBot/prompts/
```

---

## 13. Recommendations

### Immediate Actions (High Priority)

1. **✅ EXECUTE PHASE 1 IMMEDIATELY** - Zero risk, immediate cleanup
   - Remove Zone.Identifier files (12 files)
   - Remove test directory
   - Remove empty directories

2. **✅ CREATE BACKUP** - Before any structural changes
   ```bash
   cp -r /home/kali/Desktop/AutoBot/prompts \
         /home/kali/Desktop/AutoBot/scripts/archive/prompts-backup
   ```

3. **✅ DOCUMENT CURRENT STATE** - Before reorganization
   - Save list of current prompt keys
   - Document which prompts are actively used
   - Note any dependencies

### Short-Term Actions (This Week)

4. **⚠️ EXECUTE PHASE 2 WITH TESTING** - Archive Agent Zero framework
   - Verify no code references to framework prompts
   - Archive default/, developer/, researcher/, hacker/, reflection/
   - Test all functionality
   - Monitor for fallback issues

5. **📝 CREATE PROMPT STRATEGY DOCUMENT** - Define prompt management approach
   - Prompt naming conventions
   - Directory organization rules
   - Adding new prompts process
   - Version control for prompts

### Long-Term Actions (Next Sprint)

6. **🔄 EXECUTE PHASE 3 GRADUALLY** - Reorganize in stages
   - Week 1: Create core/ directory, move one prompt
   - Week 2: Test, move remaining core prompts
   - Week 3: Update all code references
   - Week 4: Final testing and documentation

7. **🎯 CONSOLIDATE IDENTITY DEFINITIONS** - Resolve overlaps
   - Single source of truth for AutoBot identity
   - Clear hierarchy of prompts
   - Remove redundant definitions

8. **📚 ENHANCE PROMPT DOCUMENTATION** - Comprehensive guide
   - Prompt engineering guidelines
   - AutoBot-specific prompt patterns
   - Best practices for context switching
   - Examples and templates

---

## 14. Conclusion

The prompts directory audit reveals a system with significant technical debt from imported Agent Zero framework templates (77% of files) that are not being actively used by AutoBot.

**Key Findings:**
- Only 4 prompt keys actively used in code
- 90+ framework template files unused
- 12 Windows artifact files to remove
- 2 empty directories to remove
- New chat/ prompts well-integrated but need documentation

**Recommended Path Forward:**

1. **Immediate:** Execute Phase 1 cleanup (zero risk)
2. **Short-term:** Archive Agent Zero framework (low risk, high value)
3. **Long-term:** Reorganize into clean core/chat/agents structure (medium risk, high value)

**Expected Benefits:**
- 85% reduction in prompt files (117 → ~15)
- 100% AutoBot-specific prompts
- Clear, documented structure
- Easier maintenance and updates
- No framework template confusion

**Implementation Timeline:**
- Phase 1: 5 minutes (immediate)
- Phase 2: 1 hour (this week)
- Phase 3: 2-3 hours (next sprint, staged rollout)
- Phase 4: 30 minutes (documentation)

**Total Effort:** ~4 hours for complete cleanup and reorganization
**Total Value:** Significant improvement in maintainability and clarity

---

## Appendix A: Complete File Listing

### AutoBot-Specific Prompts (18 files)

```
prompts/chat/
  - system_prompt.md (243 lines) ✅ ACTIVE
  - installation_help.md ✅ ACTIVE
  - api_documentation.md ✅ ACTIVE
  - architecture_explanation.md ✅ ACTIVE
  - troubleshooting.md ✅ ACTIVE

prompts/autobot/
  - _context.md
  - agent.system.main.role.md
  - agent.system.tool.response.md
  - system_identity_override.md
  - context (directory/file)

prompts/orchestrator/
  - system_prompt.md ✅ ACTIVE

prompts/llm/
  - task_system_prompt.txt ✅ ACTIVE

prompts/ (root)
  - tool_interpreter_system_prompt.txt ✅ ACTIVE
```

### Agent Zero Framework (90 files)

```
prompts/default/ (74 files)
  - agent.system.* (25 files)
  - fw.* (30 files)
  - behaviour.* (5 files)
  - memory.* (4 files)
  - browser_agent.system.md
  - _context.md
  - (others)

prompts/developer/ (3 files)
prompts/researcher/ (3 files)
prompts/hacker/ (3 files)
prompts/reflection/ (6 files)
prompts/orchestrator/legacy_system_prompt.txt (1 file)
```

### Cleanup Targets (14+ files)

```
Zone.Identifier files (12)
prompts/test/ (1 file)
prompts/diagnostics/ (empty directory)
prompts/knowledge_base/ (empty directory)
```

---

**END OF AUDIT REPORT**
