# Industry Agent Architecture Patterns Analysis

**Issue**: #645 - Implement Industry-Standard Agent Architecture Patterns
**Author**: mrveiss
**Date**: 2025-12-28

---

## Executive Summary

This document analyzes agent architecture patterns from 5 industry-leading AI tools (Manus, Cursor, Devin, Windsurf) and compares them with AutoBot's current implementation. The analysis identifies key patterns for improving AutoBot's agent system.

---

## 1. Manus Agent Architecture (⭐⭐⭐⭐⭐ Priority)

### 1.1 Core Agent Loop (6-Step Iteration)

Manus implements a clear, well-defined agent loop:

```
┌─────────────────────────────────────────────────────────────┐
│                    MANUS AGENT LOOP                         │
├─────────────────────────────────────────────────────────────┤
│ 1. ANALYZE EVENTS                                           │
│    └─ Understand user needs + current state from event      │
│       stream, focusing on latest messages + results         │
│                                                             │
│ 2. SELECT TOOLS                                             │
│    └─ Choose next tool based on:                            │
│       • Current state                                       │
│       • Task planning (from Planner module)                 │
│       • Relevant knowledge (from Knowledge module)          │
│       • Available data APIs (from Datasource module)        │
│                                                             │
│ 3. WAIT FOR EXECUTION                                       │
│    └─ Sandbox executes selected tool action                 │
│    └─ New observations added to event stream                │
│                                                             │
│ 4. ITERATE                                                  │
│    └─ Choose ONLY ONE tool call per iteration               │
│    └─ Patiently repeat steps until task completion          │
│                                                             │
│ 5. SUBMIT RESULTS                                           │
│    └─ Send results via message tools                        │
│    └─ Provide deliverables + files as attachments           │
│                                                             │
│ 6. ENTER STANDBY                                            │
│    └─ Enter idle state when tasks complete                  │
│    └─ Wait for new tasks                                    │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Event Stream System

Manus uses a typed event stream for context management:

| Event Type | Purpose | Source |
|------------|---------|--------|
| `Message` | User inputs | User |
| `Action` | Tool calls (function calling) | Agent |
| `Observation` | Execution results | Sandbox |
| `Plan` | Task step planning + status updates | Planner Module |
| `Knowledge` | Task-relevant knowledge + best practices | Knowledge Module |
| `Datasource` | Data API documentation | Datasource Module |

**Key Insight**: Events are chronological and may be truncated/omitted. The agent must focus on latest user messages and execution results.

### 1.3 Modular Architecture

#### Planner Module
- Provides overall task planning as events in event stream
- Uses **numbered pseudocode** to represent execution steps
- Each update includes:
  - Current step number
  - Status
  - Reflection
- Pseudocode updates when overall task objective changes
- **Must complete all planned steps** before task completion

#### Knowledge Module
- Provides best practice references
- Task-relevant knowledge as events
- Each knowledge item has **scope** and **adoption conditions**

#### Datasource Module
- Provides data API access
- API documentation provided as events
- Priority: **Data API > Web Search > Internal Knowledge**
- APIs called through Python code (not as tools)
- Pre-installed libraries ready to use

### 1.4 Todo-Based Progress Tracking

```markdown
## Manus Todo Rules
- Create todo.md as checklist based on Planner module output
- Task planning takes precedence over todo.md
- Update markers immediately after completing each item
- Rebuild todo.md when planning changes significantly
- Must use todo.md for information gathering tasks
- Verify todo.md completion before task completion
- Remove skipped items at the end
```

### 1.5 Message Communication Pattern

Two message types with clear purposes:

| Type | Blocking | Purpose |
|------|----------|---------|
| `notify` | No | Progress updates, no reply needed |
| `ask` | Yes | Essential questions, reply required |

**Rules**:
- Reply immediately to new user messages before other operations
- First reply must be brief (only confirming receipt)
- Use `notify` actively for progress updates
- Reserve `ask` for essential needs only
- Provide files as attachments (users can't access local filesystem)

### 1.6 Error Handling Pattern

```
1. Verify tool names and arguments
2. Attempt fix based on error messages
3. Try alternative methods if unsuccessful
4. Report failure reasons + request assistance if all fail
```

---

## 2. Cursor Agent Architecture (⭐⭐⭐⭐⭐ Priority)

### 2.1 Parallel Tool Execution

**Critical Pattern**: Cursor defaults to parallel execution for independent tools.

```
┌─────────────────────────────────────────────────────────────┐
│              CURSOR PARALLEL EXECUTION RULES                │
├─────────────────────────────────────────────────────────────┤
│ ALWAYS PARALLEL:                                            │
│ • Multiple grep_search calls (different patterns)           │
│ • Multiple file_search calls (different queries)            │
│ • Multiple list_dir calls (different directories)           │
│ • Multiple web_search calls (different topics)              │
│ • Independent read_file operations                          │
│                                                             │
│ ALWAYS SEQUENTIAL:                                          │
│ • When output of A is required for input of B               │
│ • read_file → edit_file (same file)                        │
│ • search → read → edit chain                               │
└─────────────────────────────────────────────────────────────┘
```

**Performance Impact**: 3-5x faster task completion

### 2.2 Code Edit Philosophy

```markdown
## Cursor Edit Rules
1. NEVER output code to user unless requested
2. Use code edit tools to implement changes
3. Group all edits to SAME FILE in SINGLE tool call
4. Use `// ... existing code ...` to represent unchanged code
5. Bias towards repeating as few lines as possible
6. Each edit must have sufficient context to resolve ambiguity
7. DO NOT omit spans of code without the placeholder comment
```

### 2.3 Search Priority

```
1. Semantic search (highest priority) - for higher-level questions
2. Grep search - for exact text/regex patterns
3. File search - for finding files by name
4. List dir - for directory exploration (use sparingly)
```

### 2.4 Linter Error Handling

```
If linter errors introduced:
  1. Fix if clear how to
  2. Do NOT make uneducated guesses
  3. DO NOT loop more than 3 times on same file
  4. On third attempt: STOP and ask user
```

### 2.5 Memory System (Rating-Based)

Cursor uses a sophisticated memory rating system (1-5):

| Score | Criteria |
|-------|----------|
| 5 | Specific, actionable, general preference (e.g., "Prefer Svelte over React") |
| 4 | Clear configuration/workflow preference (e.g., "strictNullChecks: true") |
| 3 | Project-specific but helpful (e.g., "Frontend in 'components' dir") |
| 1-2 | Vague, obvious, or tied to specific code/files |

---

## 3. Devin Agent Architecture (⭐⭐⭐⭐ Priority)

### 3.1 Dual-Mode Operation

Devin operates in two distinct modes:

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVIN DUAL MODES                         │
├─────────────────────────────────────────────────────────────┤
│ PLANNING MODE                                               │
│ ├─ Gather all information needed                            │
│ ├─ Search and understand codebase                           │
│ │   • Open files                                            │
│ │   • Search using LSP                                      │
│ │   • Use browser for online sources                        │
│ ├─ Ask user for help if needed                              │
│ └─ Call <suggest_plan/> when confident                      │
│    (Must know ALL locations to edit)                        │
│                                                             │
│ STANDARD MODE                                               │
│ ├─ See current + possible next plan steps                   │
│ ├─ Output actions for current/next steps                    │
│ └─ Abide by plan requirements                               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Think Tool (Reasoning Scratchpad)

**MANDATORY use cases**:
1. Before critical git/GitHub decisions
2. When transitioning from exploring to making changes
3. Before reporting completion to user

**SHOULD use cases**:
1. No clear next step
2. Details unclear but important
3. Unexpected difficulties
4. Multiple failed approaches
5. Critical decisions
6. Test/lint/CI failures
7. Environment setup issues
8. Repo uncertainty
9. Viewing images/screenshots
10. Search not finding matches

### 3.3 Coding Best Practices

```markdown
## Devin Coding Rules
- NO comments unless requested or complex code
- Mimic existing code conventions
- NEVER assume library availability - always verify
- Look at existing components before creating new ones
- Understand surrounding context before editing
```

### 3.4 Git/GitHub Workflow

```markdown
## Devin Git Rules
- NEVER force push (ask user if push fails)
- NEVER use `git add .` - be selective
- Use gh cli for GitHub operations
- Default branch format: `devin/{timestamp}-{feature-name}`
- Push to same PR for follow-ups (unless told otherwise)
- Ask user if CI fails after 3rd attempt
```

### 3.5 Error Escalation Pattern

```
1. When struggling with tests: NEVER modify tests (unless task requires)
2. Root cause is likely in tested code, not test itself
3. Environment issues: Report to user → Continue without fixing → Use CI
4. CI failures: Ask user after 3rd attempt
```

---

## 4. Windsurf (Cascade) Architecture (⭐⭐⭐⭐ Priority)

### 4.1 Tool Calling Philosophy

```markdown
## Windsurf Tool Rules
1. ONLY call tools when ABSOLUTELY NECESSARY
2. If already know answer → respond without tools
3. NEVER make redundant tool calls (expensive)
4. If stating you'll use a tool → IMMEDIATELY call it
5. Tools run asynchronously → may not see output immediately
6. If need previous output → stop making new calls
```

### 4.2 Code Change Rules

```markdown
## Windsurf Edit Rules
1. NEVER output code to user (use edit tools)
2. Code must be IMMEDIATELY RUNNABLE
3. Add ALL necessary imports, dependencies, endpoints
4. Create dependency management file if from scratch
5. NEVER generate long hashes or binary
6. **COMBINE ALL changes into SINGLE edit_file call**
7. After changes: provide BRIEF summary + proactively run code
```

### 4.3 Memory System

**Proactive Memory Creation**:
- Create memories immediately when encountering important info
- NO permission needed from user
- NO need to wait until end of task
- Be liberal with memory creation (user can reject)
- Context window is limited - memories preserve key context

**Memory Types**:
- User preferences
- Explicit requests to remember
- Important code snippets
- Technical stacks
- Project structure
- Milestones/features
- Design patterns
- Architectural decisions

### 4.4 Communication Style

```markdown
## Windsurf Communication Rules
- BE CONCISE - BREVITY IS CRITICAL
- Minimize output tokens while maintaining quality
- Address only the specific query/task
- Proactive only when user asks to do something
- Balance: (a) doing right thing (b) not surprising user
- If asked "how to approach" → answer first, don't jump to editing
```

### 4.5 Browser Preview Integration

```
ALWAYS invoke browser_preview after running local web server
DO NOT run for non-web apps (pygame, desktop apps, etc.)
```

---

## 5. Architecture Comparison: AutoBot vs Industry

### 5.1 Current AutoBot Architecture

| Component | Status | Gap |
|-----------|--------|-----|
| Agent Loop | Implicit | No formal loop definition |
| Event Stream | ❌ Missing | No typed event system |
| Planner Module | Partial (TodoWrite) | Not integrated with agent loop |
| Knowledge Module | ✅ ChromaDB | Needs scoped relevance |
| Parallel Execution | ❌ Missing | Sequential by default |
| Memory System | ✅ MCP Memory | Needs rating system |
| Error Handling | Basic | Needs retry + escalation |

### 5.2 Recommended Improvements

#### Priority 1: Agent Loop Formalization
```
Current: Ad-hoc tool execution
Target: 6-step Manus-style loop with clear phases
```

#### Priority 2: Event Stream System
```
Current: Conversation history only
Target: Typed events (Message, Action, Observation, Plan, Knowledge)
Implementation: Redis pub/sub for real-time event stream
```

#### Priority 3: Parallel Tool Execution
```
Current: Sequential tool calls
Target: Automatic parallelization of independent operations
Expected: 3-5x performance improvement
```

#### Priority 4: Planner Module
```
Current: TodoWrite (simple checklist)
Target: Numbered pseudocode steps with status tracking
Integration: Events feed into agent loop
```

#### Priority 5: Think Tool / Reasoning Scratchpad
```
Current: ❌ Not available
Target: Dedicated reasoning phase before critical decisions
Trigger: Git operations, code changes, task completion
```

---

## 6. Implementation Roadmap

### Phase 1: Event Stream System (Week 1-2)

```python
# Proposed event types
@dataclass
class AgentEvent:
    type: EventType  # MESSAGE, ACTION, OBSERVATION, PLAN, KNOWLEDGE
    timestamp: datetime
    content: dict
    source: str  # user, agent, planner, knowledge_module

# Redis pub/sub integration
class EventStream:
    def publish(self, event: AgentEvent)
    def subscribe(self, event_types: list[EventType])
    def get_latest(self, count: int) -> list[AgentEvent]
```

### Phase 2: Planner Module (Week 2-3)

```python
class PlannerModule:
    def create_plan(self, task: str) -> Plan:
        """Generate numbered pseudocode steps"""

    def update_step(self, step_num: int, status: str, reflection: str):
        """Update step status and emit Plan event"""

    def get_current_step(self) -> PlanStep:
        """Return current in-progress step"""
```

### Phase 3: Parallel Execution (Week 3-4)

```python
class ToolExecutor:
    def analyze_dependencies(self, tools: list[ToolCall]) -> DependencyGraph:
        """Identify which tools can run in parallel"""

    async def execute_parallel(self, tools: list[ToolCall]) -> list[Result]:
        """Execute independent tools concurrently"""
```

### Phase 4: Knowledge Module Enhancement (Week 4-5)

```python
class ScopedKnowledge:
    def __init__(self, content: str, scope: str, conditions: list[str]):
        self.content = content
        self.scope = scope  # "python", "frontend", "database", etc.
        self.conditions = conditions  # when to apply

    def is_applicable(self, context: dict) -> bool:
        """Check if knowledge applies to current context"""
```

### Phase 5: Agent Prompt Updates (Week 5-6)

Update all agent prompts with:
- Formal agent loop instructions
- Parallel execution guidelines
- Error handling patterns
- Think tool integration

---

## 7. Key Takeaways

### From Manus
1. **6-step agent loop** - Clear, repeatable process
2. **Event stream** - Typed events for context management
3. **Modular architecture** - Planner, Knowledge, Datasource modules
4. **One tool per iteration** - Prevents chaos, enables reflection

### From Cursor
1. **Parallel by default** - 3-5x faster execution
2. **Memory rating system** - Quality over quantity
3. **Linter error limit** - Stop after 3 attempts
4. **Semantic search priority** - Better than grep for understanding

### From Devin
1. **Planning vs Standard modes** - Separate information gathering from execution
2. **Think tool** - Mandatory reasoning before critical decisions
3. **Never modify tests** - Root cause is in code, not tests
4. **3-strike rule** - Ask user after 3 CI failures

### From Windsurf
1. **Tool call minimization** - Only when absolutely necessary
2. **Single edit call** - Combine all changes into one call
3. **Proactive memory** - Create memories immediately
4. **Brevity** - Minimize output tokens

---

## 8. Next Steps

1. **Create detailed design documents** for each component
2. **Prototype event stream** with Redis pub/sub
3. **Implement Planner module** as separate service
4. **Add parallel execution** to agent prompts
5. **Update all specialized agents** with new patterns
6. **Benchmark performance** before/after implementation

---

## References

- Manus Agent Prompt: `docs/external_apps/.../Manus Agent Tools & Prompt/`
- Cursor Agent Prompt: `docs/external_apps/.../Cursor Prompts/`
- Devin Agent Prompt: `docs/external_apps/.../Devin AI/`
- Windsurf Agent Prompt: `docs/external_apps/.../Windsurf/`
