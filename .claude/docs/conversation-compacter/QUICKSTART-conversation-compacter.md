# Quick Start: Conversation Compaction

## When to Use
```
Token usage: 150000/200000 → Time to compact
```

## Steps (30 seconds)

### 1. Call Agent
```
@conversation-compacter
Summarize. Preserve: [current task], todos, blockers, file paths.
```

### 2. Copy Output (~300 tokens)
```markdown
# Summary - 2025-10-22
## Context
PROJECT: AutoBot | ARCH: 5-VM distributed
## Status
DONE: [achievements] | WIP: [active] | BLOCKED: [none]
## Todos
□ [task 1]
□ [task 2]
## Next
1. [immediate action]
```

### 3. New Conversation
Paste: "Continue from previous:\n\n[summary]"

**Result:** 150k → 300 tokens. Context preserved.

---

## Custom Compression
```
@conversation-compacter
Target 200 tokens. Focus: frontend Vue.js, component paths.
Eliminate: backend discussion.
```

## Store for Reference
```bash
mcp__memory__create_entities --entities '[{
  "name": "Summary 2025-10-22",
  "entityType": "conversation_archive",
  "observations": ["[summary]"]
}]'
```

## Troubleshooting
| Issue | Fix |
|-------|-----|
| Lost details | Re-run with specific preservation instructions |
| Too long | "Target 250 tokens max" |
| Can't continue | Check file paths, todos, blockers included |

## Files
- Agent: `.claude/agents/conversation-compacter.md`
- Guide: `.claude/docs/conversation-compacter/`
