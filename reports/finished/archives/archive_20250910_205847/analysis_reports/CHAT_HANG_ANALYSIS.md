# Chat Endpoint Hanging - Detailed Analysis

## Problem Summary

The chat endpoint (`/api/chat` and `/api/chats/{chat_id}/message`) hangs after successfully completing KB search. The frontend times out after 45 seconds, but the backend continues processing without returning a response.

## Flow Analysis

### 1. Request Flow Path

``` Workflow
Frontend (ChatInterface.vue) 
  ↓ POST /api/chat
Backend (chat.py: send_chat_message_legacy)
  ↓ Routes to conversation_chat_message
Backend (chat.py: conversation_chat_message)
  ↓ Creates/gets conversation
Conversation (conversation.py: process_user_message)
  ↓ Parallel: classify_message + search_knowledge_base
  ↓ KB search completes successfully (logs confirm)
  ↓ _generate_response called
LLM Failsafe Agent (llm_failsafe_agent.py: get_robust_llm_response)
  ↓ Tries primary LLM tier
LLM Interface (llm_interface.py: chat_completion)
  ↓ _ollama_chat_completion
  ↓ Makes HTTP request to Ollama service
  [HANGS HERE] - No response received
```

## Identified Issues

### 1. Ollama Service Connection

- **Issue**: The Ollama service on the host might not be responding
- **Evidence**: The hang occurs in `_ollama_chat_completion` after making the HTTP request
- **Location**: `src/llm_interface.py` line ~564

### 2. Timeout Mismatch

- **Frontend timeout**: 45 seconds
- **Backend LLM timeout**: 25 seconds (reduced from 600s)
- **Issue**: Backend should timeout before frontend, but it doesn't

### 3. Streaming Response Handling

- **Issue**: The code uses streaming (`"stream": True`) but might not handle stream interruption properly
- **Location**: `_ollama_chat_completion` processes streaming responses in a loop

### 4. Missing Error Propagation

- **Issue**: Errors in LLM calls might not propagate correctly back to the frontend
- **Evidence**: No error response is sent when timeout occurs

## Root Causes

### 1. Primary Cause: Ollama Service Unavailable

The Ollama service running on the host (`http://localhost:11434`) is likely:

- Not running
- Overloaded
- Has a model loading issue
- Is being accessed by both host and Docker containers simultaneously

### 2. Secondary Cause: Inadequate Error Handling

When Ollama doesn't respond:

- The streaming loop waits indefinitely
- Timeout isn't properly enforced
- Error doesn't bubble up to send a response

### 3. Tertiary Cause: Resource Contention

Multiple services trying to use Ollama:

- Backend on host
- AI Stack in Docker
- Possible model loading conflicts

## Specific Code Issues

### 1. In `llm_interface.py` (_ollama_chat_completion):

```python
async with session.post(url, headers=headers, json=data) as response:
    response.raise_for_status()
    # Handle streaming response
    full_content = ""
    async for line in response.content:  # <-- This can hang indefinitely
        # ... processing ...
```

### 2. In `conversation.py` (_generate_response):

```python
# Get LLM response with failover
llm_response = await get_robust_llm_response(  # <-- No timeout wrapper here
    f"{system_prompt}\n\n{user_prompt}",
    context={...}
)
```

### 3. In `chat.py` (conversation_chat_message):

```python
# Process the message through the conversation
result = await conversation.process_user_message(message)  # <-- No overall timeout
```

## Immediate Fixes Needed

### 1. Add Ollama Health Check

```python
async def check_ollama_health():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OLLAMA_HOST}/api/tags", timeout=aiohttp.ClientTimeout(total=2)) as response:
                return response.status == 200
    except:
        return False
```

### 2. Add Timeout Wrapper

```python
try:
    result = await asyncio.wait_for(
        conversation.process_user_message(message),
        timeout=40.0  # Less than frontend timeout
    )
except asyncio.TimeoutError:
    return JSONResponse(
        status_code=504,
        content={"error": "Request timed out while processing message"}
    )
```

### 3. Fix Streaming Loop

```python
async for line in response.content:
    # Add timeout for each chunk
    try:
        chunk_data = await asyncio.wait_for(
            process_chunk(line),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        logger.error("Chunk processing timeout")
        break
```

### 4. Add Circuit Breaker

Implement a circuit breaker for Ollama calls to prevent repeated failed attempts:

```python
@circuit_breaker(failure_threshold=3, recovery_timeout=30)
async def call_ollama(model, messages, **kwargs):
    # Ollama call implementation
```

## Validation Steps

1. **Check Ollama Status**:

   ```bash
   curl http://localhost:11434/api/tags
   ```

2. **Monitor Backend Logs**:

   ```bash
   tail -f backend_live.log | grep -E "(Ollama|LLM|timeout)"
   ```

3. **Test Direct Ollama Call**:

   ```bash
   curl http://localhost:11434/api/chat -d '{
     "model": "deepseek-r1:14b",
     "messages": [{"role": "user", "content": "Hello"}],
     "stream": false
   }'
   ```

4. **Check Resource Usage**:

   ```bash
   docker stats
   nvidia-smi
   htop
   ```

## Prevention Strategy

1. **Pre-flight Checks**: Check service availability before processing requests
2. **Timeouts at Every Level**: Ensure timeouts are enforced at each layer
3. **Graceful Degradation**: Fall back to simpler models or cached responses
4. **Resource Isolation**: Separate Ollama instances for different services
5. **Monitoring**: Add metrics for response times and timeout rates

## Testing Approach

1. **Unit Test**: Mock Ollama timeout scenarios
2. **Integration Test**: Test with Ollama service down
3. **Load Test**: Multiple concurrent requests to identify bottlenecks
4. **Chaos Test**: Randomly kill Ollama during requests

---

*This analysis should be used to implement the fixes in Task 1.2 of the Implementation Plan.*
