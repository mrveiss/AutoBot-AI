# Conversation Compaction Example

## Before: Verbose (2,847 tokens)

```
User: Getting timeout errors frontend→backend API

Claude: I'll help debug. [Reads backend/config.yaml] Backend on port 8001.
[Reads backend/redis_manager.py] Found issue - Redis timeout only 5s.
[Reads autobot-vue/src/services/api.ts] Frontend timeout 30s but backend
Redis times out at 5s, causing failure before frontend timeout reached.

I'll fix by: 1) Increase Redis timeout to 30s 2) Add retry logic
3) Implement connection pooling

[Shows 50-line code block]

User: Apply changes?

Claude: [Edits backend/redis_manager.py] Done. Changes: timeout 5→30s,
retry with exponential backoff, connection pooling for 3 Redis DBs.

User: Restart backend?

Claude: [Restarts] [Health check] All Redis DBs connected. Fixed.

User: Now implement conversation compaction to avoid 200k limit.

Claude: [Searches MCP - no results] No previous work found.
[Creates TodoWrite] Recommend creating agent in .claude/agents/...
```

## After: Compact (312 tokens)

```markdown
# Summary - 2025-10-22

## Context
PROJECT: AutoBot | STACK: Python/FastAPI, Vue.js, Redis, Docker
ARCH: 5-VM distributed (main:8001, frontend:5173, redis:6379, ai:8080, browser:3000)

## Status
DONE: Fixed Redis timeout backend/redis_manager.py:145 (5s→30s + retry + pooling)
      Backend restarted, health checks passing (3 Redis DBs connected)
WIP: Conversation compaction agent
BLOCKED: None

## Todos
□ [HIGH] Create conversation-compacter in .claude/agents/
□ Test agent with sample conversation
□ Document usage

## Decisions & Files
- Redis timeout: 30s matches frontend timeout
- Connection pooling: 3 separate Redis databases
- Root cause: Frontend 30s > Backend Redis 5s timeout
- backend/redis_manager.py: Config fixed
- autobot-vue/src/services/api.ts: Frontend timeout ref

## Next
1. Create conversation-compacter.md following agent patterns
2. Implement summarization (target: 70-90% compression)

## State
MCP: Searched (no prior compaction work) | Agents: None yet
Constraints: 200k token limit, preserve paths/todos/decisions
---
Tokens: 312 | Original: 2,847 | Compression: 89%
```

## What Changed

| Eliminated (2,535 tokens) | Preserved (312 tokens) |
|---------------------------|------------------------|
| "I'll help debug..." | File paths + line numbers |
| Tool call narratives | Config changes (5s→30s) |
| Permission requests | Architecture (5-VM, ports) |
| 50-line code blocks | Active todos |
| Step-by-step process | Root cause analysis |
| Redundant confirmations | Next actions |

## Usage in New Conversation

```
Continue from previous:

[paste 312-token summary]

Current: Implementing conversation-compacter agent.
```

**Result:** Full context, 2,535 tokens saved, seamless continuation.
