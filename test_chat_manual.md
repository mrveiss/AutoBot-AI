# Chat System Diagnosis and Manual Testing Guide

## Problem Summary

The AutoBot chat system is experiencing critical issues where:

1. **Classification works correctly** - Gemma classification agent executes and returns proper JSON
2. **Chat responses aren't generated** - After successful classification, no user response is provided
3. **Backend is completely unresponsive** - All API endpoints timeout (health, chat creation, etc.)
4. **WebSocket connections fail** - Frontend cannot establish real-time connections
5. **Process is running but hung** - uvicorn process exists but doesn't respond to requests

## Root Cause Analysis

The backend process (PID 68777) is running but completely blocked on some operation. This suggests:

- **I/O blocking**: A synchronous operation that's preventing the async event loop from processing requests
- **Deadlock**: Multiple operations waiting on each other
- **Memory/Resource exhaustion**: System struggling to handle requests
- **Database/Redis connection hanging**: Backend services may be blocking on external dependencies

## Immediate Fixes Applied

### 1. Timeout Reductions
- **LLM timeout**: Reduced from 600s to 25s (`src/llm_interface.py`)
- **LLM failsafe timeouts**: Reduced PRIMARY from 30s to 15s, SECONDARY from 20s to 10s (`src/agents/llm_failsafe_agent.py`)
- **Retry mechanism**: Reduced max attempts from 5 to 3, max delay from 30s to 8s (`src/retry_mechanism.py`)

### 2. Chat Endpoint Timeout Protection
- **Main chat endpoint**: Added 25-second timeout wrapper with graceful fallback (`backend/api/chat.py`)
- **Better error messages**: User-friendly timeout responses instead of generic errors
- **Emergency fallback**: Improved LLM failsafe to provide helpful messages when all tiers fail

### 3. Enhanced Error Handling
- **Timeout responses**: Return HTTP 408 with helpful message instead of hanging
- **Emergency responses**: "I'm having trouble connecting to my AI models right now. Please try again in a few seconds."
- **Graceful degradation**: System continues working even when LLM services fail

## Manual Testing Procedures

### Step 1: Restart Backend (Required)
```bash
# Find and kill the hung backend process
ps aux | grep uvicorn
kill 68777

# Restart the backend
cd /home/kali/Desktop/AutoBot
./run_agent.sh
```

### Step 2: Test Basic Connectivity
```bash
# Test health endpoint (should respond in <2 seconds)
curl -w "%{time_total}s" http://127.0.0.3:8001/api/system/health

# Test chat creation (should respond in <5 seconds)
curl -X POST -H "Content-Type: application/json" -d '{}' \
     http://127.0.0.3:8001/api/chats/new
```

### Step 3: Test Chat Functionality
```bash
# Create a test chat and get chat_id from response
CHAT_ID="<chat_id_from_step_2>"

# Test direct chat endpoint (simpler, bypasses orchestration)
curl -X POST -H "Content-Type: application/json" \
     -d '{"chatId":"'$CHAT_ID'","message":"hi"}' \
     http://127.0.0.3:8001/api/chat/direct

# Test main chat endpoint (full functionality)
curl -X POST -H "Content-Type: application/json" \
     -d '{"message":"hi"}' \
     http://127.0.0.3:8001/api/chats/$CHAT_ID/message
```

### Step 4: Test WebSocket Connection
```bash
# Install websocat if not available: cargo install websocat
# Test WebSocket connection
echo '{"type":"test","message":"hello"}' | websocat ws://127.0.0.3:8001/ws
```

### Step 5: Frontend Testing
1. Open browser to `http://127.0.0.3:5173`
2. Check browser console for errors
3. Try creating a new chat
4. Send a simple message like "hi"
5. Verify response appears within 30 seconds

## Expected Behavior After Fixes

### Successful Flow:
1. **User sends "hi"** → Frontend calls `/api/chats/{chat_id}/message`
2. **Classification runs** → Gemma agent classifies message (logs show this working)
3. **Knowledge base search** → Quick search (10s timeout)
4. **LLM response generation** → Uses failsafe agent with 15s timeout
5. **Response returned** → User sees response within 25 seconds total

### Timeout Flow:
1. **If LLM hangs** → 15s timeout triggers secondary LLM
2. **If all LLM tiers fail** → Emergency response: "I'm having trouble connecting..."
3. **If entire endpoint hangs** → 25s timeout returns HTTP 408 with helpful message

## Monitoring and Debugging

### Log Locations:
- **Backend logs**: Check terminal running `./run_agent.sh`
- **Frontend logs**: Browser console (F12)
- **System logs**: `journalctl -f` for system-level issues

### Key Debug Points:
1. **Classification success**: Look for "Ollama Final Response" in logs
2. **LLM hanging**: Look for "Primary model {model} timed out" warnings
3. **Timeout triggered**: Look for "Chat message processing timed out"
4. **WebSocket issues**: Look for "WebSocket connected successfully" or connection errors

### Performance Metrics:
- **Health endpoint**: Should respond in <2 seconds
- **Chat creation**: Should respond in <5 seconds
- **Simple chat response**: Should respond in <25 seconds
- **WebSocket connection**: Should establish in <5 seconds

## Next Steps if Issues Persist

1. **Check Dependencies**:
   - Redis: `redis-cli ping`
   - Database connections: Check for locked transactions
   - File system: Check disk space and permissions

2. **Resource Monitoring**:
   - Memory: `free -h`
   - CPU: `top` or `htop`
   - Network: `netstat -tuln`

3. **Process Analysis**:
   - Stuck threads: `py-spy top --pid 68777`
   - System calls: `strace -p 68777`

4. **Alternative Endpoints**:
   - Use `/api/chat/direct` for simpler responses
   - Implement client-side timeout and retry logic
   - Add circuit breaker for LLM services

## Configuration Files Modified

- `/home/kali/Desktop/AutoBot/src/llm_interface.py` - Reduced Ollama timeout to 25s
- `/home/kali/Desktop/AutoBot/src/agents/llm_failsafe_agent.py` - Reduced tier timeouts and improved emergency responses
- `/home/kali/Desktop/AutoBot/src/retry_mechanism.py` - Reduced retry attempts and delays
- `/home/kali/Desktop/AutoBot/backend/api/chat.py` - Added 25s timeout wrapper to main chat endpoint

The system should now fail fast and provide helpful feedback instead of hanging indefinitely.
