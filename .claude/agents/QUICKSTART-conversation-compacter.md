# Quick Start: Conversation Compaction

## When You See This Warning

```
Token usage: 150000/200000; 50000 remaining
```

**It's time to compact your conversation.**

## How to Use (30 seconds)

### Step 1: Call the Agent

```
@conversation-compacter

Summarize this conversation. Preserve:
- Current work on [your task]
- Active todos and blockers
- File paths and technical decisions
```

### Step 2: Copy the Summary

Agent produces ~300 token summary like:

```markdown
# Conversation Summary - 2025-10-22

## Project Context
PROJECT: AutoBot
ARCHITECTURE: 5-VM distributed

## Current Status
COMPLETED: [key achievements]
IN PROGRESS: [active work]

## Active Todos
□ [todo 1]
□ [todo 2]

## Key Decisions
- Decision 1: rationale
FILE: /path/to/file.py: what changed

## Next Steps
1. [immediate action]
2. [following action]
```

### Step 3: Start New Conversation

1. Start new conversation in Claude Code
2. First message: "Continue from previous conversation:\n\n[paste summary]"
3. Continue working with 199,700+ tokens available

## That's It!

**Before**: 150k tokens used, 50k remaining
**After**: 300 tokens used, 199.7k remaining
**Context Loss**: Near zero

---

## Advanced Usage (Optional)

### Custom Compression Focus

```
@conversation-compacter

Target 200 tokens. Focus only on:
- Frontend Vue.js work
- Component file paths
- Last 3 error messages
Eliminate all backend discussion.
```

### Store for Later Reference

```bash
mcp__memory__create_entities --entities '[{
  "name": "Conversation Summary 2025-10-22",
  "entityType": "conversation_archive",
  "observations": ["[paste summary]"]
}]'
```

---

## Troubleshooting

**"Lost important details"**
→ Re-run with specific preservation instructions

**"Summary too long"**
→ Ask for more aggressive compression ("Target 250 tokens max")

**"Can't continue work"**
→ Summary missing context. Check file paths, todos, blockers are included

---

## Full Documentation

- **Agent File**: `.claude/agents/conversation-compacter.md`
- **Usage Guide**: `.claude/agents/README-conversation-compacter.md`
- **Example**: `.claude/agents/EXAMPLE-conversation-compaction.md`

---

**Created**: 2025-10-22
**Purpose**: Avoid "Conversation too long" errors in Claude Code
