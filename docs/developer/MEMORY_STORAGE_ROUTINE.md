# Memory MCP Storage Routine - Developer Guide

**Version**: 1.0
**Date**: 2025-10-26
**Status**: Active Policy

---

## Purpose

This document defines the **mandatory** routine for storing conversations, decisions, and findings in the Memory MCP knowledge graph to ensure institutional knowledge retention and prevent information loss.

---

## Why Memory Storage Matters

### Problems Without Memory Storage:
- **Knowledge Loss**: Critical context disappears when moving to new topics
- **Repeated Work**: Re-solving already-solved problems
- **Poor Decisions**: Missing historical context for future decisions
- **Onboarding Difficulty**: New team members lack institutional knowledge
- **Low Coverage**: Memory audit revealed only **15-20% coverage** before establishing this routine

### Benefits With Memory Storage:
- ✅ **Knowledge Retention**: Critical context preserved and searchable
- ✅ **Prevent Duplication**: Search for similar past work before starting
- ✅ **Better Decisions**: Historical context available for informed choices
- ✅ **Easier Onboarding**: Complete work history documented
- ✅ **Institutional Memory**: System "remembers" past solutions and patterns

---

## When to Store

### Required Storage Events:

1. **End of Each Work Session**
   - Store conversation summary before ending session
   - Link to problems identified and solutions created

2. **After Major Decisions**
   - Architectural choices (e.g., technology selection)
   - Design decisions (e.g., API structure, data models)
   - Process changes (e.g., new workflows, policies)

3. **When Completing Implementations**
   - Feature completions
   - Bug fixes
   - Refactoring work
   - Infrastructure changes

4. **After Problem Analysis**
   - Root cause identified
   - Solution approach determined
   - Implementation verified

---

## What to Store

### Entity Types and Use Cases:

| Entity Type | When to Use | Examples |
|------------|-------------|----------|
| **conversation** | Work sessions, troubleshooting, design sessions | "Terminal Integration Troubleshooting Session - 2025-10-25" |
| **problem** | Bugs, issues, architectural flaws | "Session Persistence Bug", "Redis SCAN Performance Bug" |
| **solution** | Fixes, implementations, approaches | "Redis Session Fallback Implementation", "PTY Architecture Utilization Fix" |
| **decision** | Architectural/design choices with rationale | "ChromaDB Selection for Code Embeddings", "CodeBERT Model Selection" |
| **implementation** | Completed work, features, migrations | "Redis to ChromaDB Migration", "Hardcoding Prevention Policy Implementation" |
| **process** | Workflows, routines, procedures | "Memory MCP Storage Routine" |
| **active_task** | Unfinished work that needs completion | "Vectorization Status Check Fix - UNFINISHED" |

---

## How to Store - Step by Step

### Step 1: Create Conversation Entity

```python
mcp__memory__create_entities(entities=[{
    "name": "Descriptive Session Name - YYYY-MM-DD",
    "entityType": "conversation",
    "observations": [
        "Date: YYYY-MM-DD, Duration: X hours, Status: Complete/In Progress",
        "Initial Problem: [Brief description]",
        "Root Cause: [What was causing the issue]",
        "Fix Applied: [Solution implemented]",
        "Impact: [Results and benefits]",
        "Files Modified: [Locations with line numbers]",
        "Key Insights/Lessons: [Important learnings]"
    ]
}])
```

### Step 2: Create Problem Entities

```python
mcp__memory__create_entities(entities=[{
    "name": "Problem Name",
    "entityType": "problem",
    "observations": [
        "Identified: YYYY-MM-DD during [context]",
        "Symptom: [What users/system experienced]",
        "Root cause: [Underlying issue]",
        "Location: [File/function where problem exists]",
        "Impact: [Effect on system/users]",
        "Severity: Critical/High/Medium/Low"
    ]
}])
```

### Step 3: Create Solution Entities

```python
mcp__memory__create_entities(entities=[{
    "name": "Solution Name",
    "entityType": "solution",
    "observations": [
        "Implemented: YYYY-MM-DD in [file:lines]",
        "Approach: [Strategy used]",
        "Implementation: [Key code/configuration changes]",
        "Key Insight: [Important realization that led to solution]",
        "Result: [Outcome and verification]",
        "Trade-offs: [Any compromises made]"
    ]
}])
```

### Step 4: Create Decision Entities (for architecture/design choices)

```python
mcp__memory__create_entities(entities=[{
    "name": "Decision Name",
    "entityType": "decision",
    "observations": [
        "Made during: [Session/date]",
        "Decision: [What was decided]",
        "Rationale: [Why this choice was made]",
        "Alternatives considered: [Other options evaluated]",
        "Benefits: [Advantages of this approach]",
        "Trade-offs: [Disadvantages or compromises]"
    ]
}])
```

### Step 5: Link Everything with Relationships

```python
mcp__memory__create_relations(relations=[
    {"from": "Conversation Name", "to": "Problem Name", "relationType": "identified"},
    {"from": "Conversation Name", "to": "Solution Name", "relationType": "produced"},
    {"from": "Conversation Name", "to": "Decision Name", "relationType": "made_decision"},
    {"from": "Solution Name", "to": "Problem Name", "relationType": "solves"}
])
```

---

## Relationship Types Reference

| Relationship | From → To | Meaning |
|-------------|-----------|---------|
| **identified** | Conversation → Problem | Session discovered this issue |
| **produced** | Conversation → Solution/Implementation | Session created this work |
| **made_decision** | Conversation → Decision | Session made this choice |
| **solves** | Solution → Problem | This fix addresses this issue |
| **caused_by** | Problem → Implementation/Change | This change caused the problem |
| **related_to** | Any → Any | General association |
| **depends_on** | Task → Task | Task requires completion of other task |
| **implements** | Solution → Decision | Solution carries out decision |
| **created_task** | Conversation → Task | Session identified work to be done |

---

## Observation Format Guidelines

### Good Observations:

✅ **Include dates**: "Implemented: 2025-10-25 in backend/api/terminal.py:595-660"
✅ **Be specific**: "Root Cause: VectorStoreIndex.from_vector_store() loading 545,255 vectors synchronously"
✅ **Include file locations**: "Files Modified: src/knowledge_base_v2.py (lines 225-230, 385-428)"
✅ **Add context**: "Key Insight: PTY sessions already handle terminal WebSocket output automatically"
✅ **Quantify impact**: "Impact: Eliminated 4.17M SCAN operations → only O(1) lookups"
✅ **Include status**: "Status: Complete/In Progress/Pending"

### Bad Observations:

❌ **Too vague**: "Fixed the bug"
❌ **Missing context**: "Changed configuration"
❌ **No location**: "Updated files"
❌ **No dates**: "Implemented recently"
❌ **No specifics**: "Made it faster"

---

## Naming Conventions

### Conversations:
- Format: `"{Topic} - YYYY-MM-DD"`
- Examples:
  - "Terminal Integration Troubleshooting Session - 2025-10-25"
  - "Code Vectorization Architecture Design Session - 2025-10-25"
  - "Hardcoding Prevention Policy Implementation - 2025-10-24"

### Problems:
- Format: `"{Problem Name} [Brief Context]"`
- Examples:
  - "Session Persistence Bug"
  - "Redis SCAN Performance Bug - 4.17M Operations"
  - "ChromaDB Event Loop Blocking Bug"

### Solutions:
- Format: `"{Solution Name} [Implementation]"`
- Examples:
  - "Redis Session Fallback Implementation"
  - "PTY Architecture Utilization Fix"
  - "Redis O(1) Index-Based Duplicate Detection"

### Decisions:
- Format: `"{Decision Topic} [Key Choice]"`
- Examples:
  - "ChromaDB Selection for Code Embeddings"
  - "CodeBERT Model Selection"
  - "8-Week Implementation Timeline"

### Active Tasks:
- Format: `"{Task Name} - UNFINISHED"`
- Examples:
  - "Vectorization Status Check Fix - UNFINISHED"
  - "Code Refactoring Phase 1 - UNFINISHED"

---

## Complete Example

### Scenario: Fixed terminal command duplication bug

```python
# Step 1: Create conversation entity
mcp__memory__create_entities(entities=[{
    "name": "Terminal Output Duplication Fix - 2025-10-25",
    "entityType": "conversation",
    "observations": [
        "Date: 2025-10-25, Duration: 2 hours, Status: Complete",
        "Problem: Commands appeared twice in Terminal tab",
        "Root Cause: PTY session sends output via _read_pty_output(), manual send_output_to_conversation() added duplicate",
        "Fix: Removed manual WebSocket sends in execute_command() and approve_command()",
        "Files Modified: backend/services/agent_terminal_service.py (lines 732-750, 898-909)",
        "Result: Single execution, clean output display",
        "Key Insight: PTY architecture already had solution, added code made it worse"
    ]
}])

# Step 2: Create problem entity
mcp__memory__create_entities(entities=[{
    "name": "Terminal Output Duplication Bug",
    "entityType": "problem",
    "observations": [
        "Identified: 2025-10-25 during terminal integration troubleshooting",
        "Symptom: Commands appeared twice in Terminal tab",
        "Root cause: PTY _read_pty_output() + manual send_output_to_conversation() = 2x output",
        "Location: backend/services/agent_terminal_service.py execute_command() and approve_command()",
        "Impact: Confusing UX, duplicate data in terminal display",
        "Severity: High - degraded user experience"
    ]
}])

# Step 3: Create solution entity
mcp__memory__create_entities(entities=[{
    "name": "PTY Architecture Utilization Fix",
    "entityType": "solution",
    "observations": [
        "Implemented: 2025-10-25 in backend/services/agent_terminal_service.py:732-750, 898-909",
        "Approach: Removed manual WebSocket output routing, rely on PTY's existing _read_pty_output() task",
        "Key Insight: PTY sessions already handle terminal WebSocket output automatically",
        "Implementation: Removed send_output_to_conversation() calls from execute_command() and approve_command()",
        "Result: Single execution, clean output display, proper PTY architecture utilization",
        "Lesson: Understand existing architecture before adding new code"
    ]
}])

# Step 4: Link entities
mcp__memory__create_relations(relations=[
    {"from": "Terminal Output Duplication Fix - 2025-10-25", "to": "Terminal Output Duplication Bug", "relationType": "identified"},
    {"from": "Terminal Output Duplication Fix - 2025-10-25", "to": "PTY Architecture Utilization Fix", "relationType": "produced"},
    {"from": "PTY Architecture Utilization Fix", "to": "Terminal Output Duplication Bug", "relationType": "solves"}
])
```

---

## Searching Stored Memory

### Find Past Conversations:
```python
mcp__memory__search_nodes(query="terminal troubleshooting")
mcp__memory__search_nodes(query="Redis performance")
mcp__memory__search_nodes(query="ChromaDB")
```

### Find Unfinished Tasks:
```python
mcp__memory__search_nodes(query="UNFINISHED")
mcp__memory__search_nodes(query="active_task")
```

### Find Specific Problems:
```python
mcp__memory__search_nodes(query="bug performance")
mcp__memory__search_nodes(query="event loop blocking")
```

### Find Solutions:
```python
mcp__memory__search_nodes(query="Redis optimization")
mcp__memory__search_nodes(query="lazy loading")
```

---

## Maintenance

### Updating Existing Entities:

```python
# Add progress updates to existing task
mcp__memory__add_observations(observations=[{
    "entityName": "Vectorization Status Check Fix - UNFINISHED",
    "contents": [
        "2025-10-27: Started Phase 1 implementation",
        "Modified backend/api/knowledge.py check_vectorization_status_batch()",
        "Replaced Redis pipeline with ChromaDB collection query"
    ]
}])
```

### Marking Tasks Complete:

```python
# Update task status
mcp__memory__add_observations(observations=[{
    "entityName": "Vectorization Status Check Fix - UNFINISHED",
    "contents": [
        "Status: COMPLETE - 2025-10-27",
        "All phases implemented successfully",
        "Vectorization status now accurate"
    ]
}])
```

---

## Integration with CLAUDE.md

This Memory Storage Routine is referenced in CLAUDE.md as a mandatory workflow requirement:

1. **Every Task Must** include Memory MCP search before starting
2. **Code review** findings should be stored in memory
3. **TodoWrite** progress should align with memory storage
4. **Workflow violations** detected when memory search is skipped

---

## Success Metrics

### Current Status (2025-10-26):
- **Coverage**: ~60-70% (up from 15-20%)
- **Conversations Stored**: 6 critical sessions (Oct 22-26)
- **Entities Created**: 40+ (conversations, problems, solutions, decisions, tasks)
- **Relationships**: 50+ meaningful links

### Target Status:
- **Coverage**: >90%
- **All Sessions**: Stored within 24 hours
- **All Decisions**: Documented with rationale
- **All Tasks**: Tracked from creation to completion

---

## Troubleshooting

### "MCP tool response exceeds maximum tokens"
- **Solution**: Use specific search queries instead of `mcp__memory__read_graph()`
- **Example**: `mcp__memory__search_nodes(query="specific topic")` instead of reading entire graph

### "Cannot find previous conversation"
- **Solution**: Use multiple search terms
- **Example**: Try "terminal", "Redis", "ChromaDB", "performance", etc.

### "Don't know what entity type to use"
- **Refer to**: "Entity Types and Use Cases" table above
- **Default**: Use "conversation" for sessions, "problem" for bugs, "solution" for fixes

---

## Policy Enforcement

### MANDATORY Requirements:

1. ✅ **Search memory** before starting similar work
2. ✅ **Store all conversations** at end of session
3. ✅ **Document all decisions** with rationale
4. ✅ **Link entities** with appropriate relationships
5. ✅ **Track unfinished work** with active_task entities

### Workflow Violation:

If memory storage is skipped:
- Knowledge loss risk
- Potential duplicate work
- Missing context for future decisions
- Violation of CLAUDE.md workflow requirements

---

## Additional Resources

- **CLAUDE.md**: Project development guidelines (includes memory workflow)
- **Memory MCP Tools Documentation**: MCP server tool specifications
- **Memory Audit Report**: Coverage analysis and gap identification

---

**Status**: ✅ **ACTIVE POLICY - MANDATORY FOR ALL DEVELOPMENT WORK**
