# LLM Shows Fake Tool Results During Streaming

**Issue Number**: #727
**Date Reported**: 2026-01-19
**Severity**: Medium
**Component**: Backend / LLM Streaming

---

## Symptoms

- Chat UI shows tool execution results **before** tool actually runs
- Results appear instantly (no delay) for operations that should take seconds
- Tool results don't match actual command output
- User sees "hallucinated" results that look plausible but are wrong
- Real results arrive later and overwrite fake ones

## Root Cause

LLM providers (Claude, GPT-4) sometimes **hallucinate tool execution results** during streaming:
- Model predicts what the tool result "should" be
- Sends predicted result before tool actually executes
- Frontend displays hallucinated result immediately
- Real result arrives later from actual tool execution

This creates confusion and trust issues.

## Quick Fix

```python
# Backend: api/endpoints/chat.py

async def stream_chat():
    # ... streaming logic ...

    for chunk in stream:
        # Skip hallucinated tool results
        if chunk.type == "tool_result" and not chunk.actual_execution:
            continue  # Don't send to frontend

        yield chunk
```

## Detailed Resolution Steps

### Step 1: Identify Hallucination Pattern

**Signs of hallucination**:
- Tool results appear **instantly** (< 100ms)
- Results are too perfect (no errors, clean formatting)
- Multiple tool calls complete simultaneously
- Results don't match actual command output when verified

**Example**:
```
User: "Check if Redis is running"
[Instantly shows]:
  Redis is running on port 6379
  Status: active (running)
  Uptime: 2 days 4 hours

[But actual `systemctl status` shows]:
  Status: inactive (dead)
```

### Step 2: Add Execution Validation

```python
# services/llm/streaming.py

class ToolCallValidator:
    def is_hallucinated(self, tool_result):
        """Detect if tool result is hallucinated."""
        # Check 1: Result arrived too fast
        if tool_result.execution_time_ms < 50:
            return True

        # Check 2: No actual tool execution ID
        if not tool_result.execution_id:
            return True

        # Check 3: Result before tool dispatch
        if tool_result.timestamp < tool_result.dispatched_at:
            return True

        return False
```

### Step 3: Filter Stream in Backend

```python
# api/endpoints/chat.py

async for chunk in llm_stream:
    if chunk.type == "tool_result":
        # Only send real tool results
        if validator.is_hallucinated(chunk):
            logger.warning(f"Filtered hallucinated tool result: {chunk.tool_name}")
            continue

        # Verify result matches execution
        if not await verify_tool_execution(chunk.execution_id):
            logger.error(f"Tool result mismatch: {chunk.tool_name}")
            continue

    yield chunk
```

### Step 4: Add Frontend Safeguard

```typescript
// composables/useChatStream.ts

function handleStreamChunk(chunk: StreamChunk) {
  if (chunk.type === 'tool_result') {
    // Only show results with execution confirmation
    if (!chunk.executionId || !chunk.timestamp) {
      console.warn('Skipping unconfirmed tool result', chunk)
      return
    }

    // Wait for real result
    if (chunk.executionTimeMs < 100) {
      console.warn('Tool result suspiciously fast', chunk)
      // Show loading indicator instead
      showToolExecuting(chunk.toolName)
      return
    }
  }

  displayChunk(chunk)
}
```

### Step 5: Add Execution Tracking

```python
# services/tools/executor.py

class ToolExecutor:
    def __init__(self):
        self.executions = {}  # track real executions

    async def execute(self, tool_call):
        exec_id = generate_id()
        self.executions[exec_id] = {
            'tool': tool_call.name,
            'started_at': time.time(),
            'status': 'executing'
        }

        try:
            result = await run_tool(tool_call)
            self.executions[exec_id]['status'] = 'completed'
            self.executions[exec_id]['result'] = result
            return result
        finally:
            # Cleanup after 5 minutes
            schedule_cleanup(exec_id, delay=300)
```

## Verification

```bash
# 1. Test tool execution timing
# Run tool call, measure response time
curl -X POST http://localhost:8001/api/chat/message \
  -d '{"message": "Check Redis status"}' | jq '.execution_time_ms'

# Should be > 100ms for real execution

# 2. Check logs for filtered hallucinations
tail -f logs/autobot.log | grep "Filtered hallucinated"

# 3. Verify execution IDs in tool results
# All tool results should have:
# - execution_id (UUID)
# - execution_time_ms > 50
# - timestamp > dispatched_at
```

**Success Indicators**:
- No instant tool results (all take realistic time)
- Tool results match actual command output
- No result overwrites after initial display
- Execution IDs present in all tool results
- Logs show filtered hallucinations (if any)

## Prevention

1. **Always track tool execution** with unique IDs
2. **Validate timing**: Real tools take >50ms minimum
3. **Log hallucinations**: Track frequency per model
4. **Add execution confirmation** to stream protocol
5. **Frontend safeguard**: Show loading state for suspicious results
6. **Model selection**: Some models hallucinate less (test & document)

## Related Issues

- #710: API endpoint mismatches
- #608: User-centric session tracking

## References

- PR #727: Add tool execution validation
- Commit: `8c3d4f1e`
- File: `autobot-user-backend/services/llm/streaming.py`
- File: `autobot-user-frontend/src/composables/useChatStream.ts`
