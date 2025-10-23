# Conversation Compaction Agent - Usage Guide

## Purpose

The conversation-compacter agent helps you avoid "Conversation too long" errors by summarizing verbose conversation history into compact, actionable summaries while preserving all critical context.

## When to Use

Trigger this agent when:
- Conversation approaches 150k+ tokens (75% of 200k limit)
- Claude Code shows "Conversation too long" warning
- Conversation contains many iterations/revisions
- You want to start fresh while preserving context

## How to Use

### Method 1: Direct Agent Call

```bash
@conversation-compacter

Please analyze this entire conversation and create a compact summary
following your framework. Focus on preserving:
- Current work on [specific feature/task]
- Active todos and blockers
- Recent decisions about [specific area]
- File paths and technical details
```

### Method 2: Use Task Tool

```
Task(
    subagent_type="conversation-compacter",
    description="Compact conversation to avoid token limits",
    prompt="Analyze full conversation and create maximally concise summary"
)
```

## What to Expect

The agent will produce a structured summary (~300 tokens) that replaces thousands of tokens of conversation history, including:

1. **Project Context** - What you're working on (30 tokens)
2. **Current Status** - Completed/In Progress/Blocked (50 tokens)
3. **Active Todos** - Prioritized task list (40 tokens)
4. **Key Decisions** - Architecture decisions, findings, file references (80 tokens)
5. **Next Steps** - Immediate and upcoming actions (30 tokens)
6. **Workflow State** - MCP entities, agents used, constraints (60 tokens)

## After Getting Summary

### Starting New Conversation

1. **Copy the summary** from agent output
2. **Start new conversation** in Claude Code
3. **Paste summary as first message**: "Continue work from previous conversation:\n\n[SUMMARY]"
4. **Continue normally** - full context preserved

### Optional: Store in Memory MCP

```bash
mcp__memory__create_entities --entities '[{
  "name": "Conversation Summary [Date]",
  "entityType": "conversation_archive",
  "observations": ["[paste summary content]"]
}]'
```

## Expected Compression

- **Original**: 150,000 tokens (75% of limit)
- **Compressed**: 300-500 tokens (summary)
- **Compression Ratio**: 99.7% reduction
- **Context Loss**: Near zero (all critical info preserved)

## Example Use Case

### Scenario
You've been working on fixing Redis timeouts for 100+ messages. Conversation is at 160k tokens.

### Action
```
@conversation-compacter

Summarize this conversation about Redis timeout fixes.
Preserve: completed fixes, remaining todos, file paths,
architectural decisions about connection pooling.
```

### Output
Agent produces 400-token summary covering:
- Fixed Redis timeout in backend/redis_manager.py
- Added connection pooling (3 databases)
- Remaining: implement retry logic
- Next: test under load

### Result
Start new conversation with summary, continue work seamlessly with 199,600 tokens available.

## Tips for Best Results

1. **Be Specific**: Tell agent what aspects are most critical
2. **Review Output**: Ensure no critical details lost
3. **Use Early**: Don't wait until absolute limit
4. **Combine with MCP**: Store summaries for long-term reference
5. **Update CLAUDE.md**: If agent reveals workflow improvements

## Token Monitoring

Check token usage in Claude Code:
- Bottom of each response shows: `Token usage: X/200000`
- Trigger compaction at ~150k tokens (75% threshold)
- Gives you buffer to complete current task

## Integration with AutoBot Workflows

This agent follows AutoBot policies:
- ✅ Uses TodoWrite for tracking
- ✅ Searches Memory MCP for previous summaries
- ✅ Preserves architectural decisions
- ✅ Maintains file path references
- ✅ Focuses on root causes, not symptoms

## Troubleshooting

### "Summary lost critical information"
- **Solution**: Re-run with explicit instructions about what to preserve
- **Example**: "Include all IP addresses, port configurations, and Redis database mappings"

### "Summary still too long"
- **Solution**: Ask for more aggressive compression
- **Example**: "Target 250 tokens maximum, use telegraphic style"

### "Can't continue work after summary"
- **Solution**: Summary missing context. Check:
  - Are file paths included?
  - Are active todos clear?
  - Are blockers explained?
  - Re-run with more specific requirements

## Advanced: Custom Compression

For specialized needs:

```
@conversation-compacter

Custom requirements:
- Target 200 tokens maximum
- Focus only on frontend work
- Preserve Vue.js component paths
- Eliminate all backend discussion
- Include last 3 error messages verbatim
```

## Related Documentation

- **CLAUDE.md**: AutoBot development policies
- **Memory MCP**: Persistent storage for summaries
- **TodoWrite**: Task tracking integration

## Quick Reference Card

```
WHEN: Conversation >150k tokens
HOW: @conversation-compacter [specific instructions]
OUTPUT: ~300 token summary
USE: Start new conversation with summary
RESULT: Continue work with near-zero context loss
```

---

**Created**: 2025-10-22
**Agent**: conversation-compacter.md
**Purpose**: Avoid context window overflow in Claude Code
