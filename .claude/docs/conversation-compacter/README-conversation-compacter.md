# Conversation Compacter - Usage Guide

## Purpose
Avoid "Conversation too long" errors by compacting verbose history into actionable summaries (~300 tokens) with zero context loss.

## When to Trigger
- Conversation >150k tokens (75% of 200k limit)
- Many iterations/revisions accumulated
- Starting fresh while preserving context

## Usage

### Direct Call
```
@conversation-compacter
Analyze conversation. Preserve: [feature], todos, blockers, file paths.
```

### Via Task Tool
```
Task(subagent_type="conversation-compacter", prompt="Compact full conversation")
```

## Output Structure (~300 tokens)
| Section | Tokens | Content |
|---------|--------|---------|
| Context | 30 | Project, stack, architecture |
| Status | 50 | Done, WIP, blocked |
| Todos | 40 | Prioritized tasks |
| Decisions | 80 | Architecture, findings, files |
| Next Steps | 30 | Immediate actions |
| State | 60 | MCP, agents, constraints |

## After Summary

1. Copy summary
2. Start new conversation
3. First message: "Continue from previous:\n\n[SUMMARY]"
4. Continue with 199,700+ tokens available

### Optional: Store in MCP
```bash
mcp__memory__create_entities --entities '[{
  "name": "Summary [Date]",
  "entityType": "conversation_archive",
  "observations": ["[summary]"]
}]'
```

## Compression Stats
- Original: 150,000 tokens
- Compressed: 300-500 tokens
- Ratio: 99.7% reduction
- Context loss: Near zero

## Tips
1. **Be specific** about critical aspects
2. **Review output** before new conversation
3. **Use early** (don't wait for limit)
4. **Combine with MCP** for long-term reference

## Custom Compression
```
@conversation-compacter
Target 200 tokens. Focus: frontend Vue.js.
Preserve: component paths, last 3 errors.
Eliminate: backend discussion.
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Lost critical info | Re-run: "Include all IPs, ports, Redis mappings" |
| Summary too long | "Target 250 tokens maximum, telegraphic style" |
| Can't continue work | Verify: file paths, todos, blockers present |

## Quick Reference
```
WHEN:   >150k tokens
HOW:    @conversation-compacter [instructions]
OUTPUT: ~300 token summary
USE:    Start new conversation with summary
RESULT: Near-zero context loss
```
