# API vs Direct Calls - Quick Reference

## Decision Tree

```
Need to communicate between components?
│
├─ Different processes/containers? ──► USE API
│   ├─ Frontend → Backend ──► REST/WebSocket API
│   ├─ Backend → Ollama ──► HTTP API
│   ├─ Backend → Redis ──► Redis Protocol
│   └─ Backend → NPU/Playwright ──► HTTP API
│
└─ Same Python process? ──► USE DIRECT CALLS
    ├─ API Router → Service ──► Direct import & call
    ├─ Service → Agent ──► Direct instantiation
    ├─ Agent → Utils ──► Direct function call
    └─ Component → Component ──► Direct method call
```

## Quick Examples

### ✅ CORRECT: Frontend calling Backend
```javascript
// Frontend (Vue.js)
const response = await fetch('/api/chat/send', {
  method: 'POST',
  body: JSON.stringify({message: 'Hello'})
});
```

### ✅ CORRECT: Backend calling internal service
```python
# Backend API endpoint
from src.orchestrator import orchestrator

@router.post("/process")
async def process_request(request: Request):
    # Direct call - same process
    result = await orchestrator.process(request.data)
    return {"result": result}
```

### ❌ WRONG: Using API for internal calls
```python
# DON'T DO THIS - Unnecessary overhead
async def internal_function():
    # Wrong - making HTTP call to self
    response = await requests.post('http://localhost:8001/api/internal')

    # Correct - direct call
    from src.internal_module import process
    result = await process()
```

### ✅ CORRECT: Calling external service
```python
# Calling Ollama LLM service
async def get_llm_response(prompt):
    # Correct - external service needs API
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://localhost:11434/api/generate',
            json={"model": "llama3", "prompt": prompt}
        ) as response:
            return await response.json()
```

## Component Communication Cheat Sheet

| From | To | Use | Example |
|------|----|----|---------|
| Vue.js | FastAPI | REST API | `fetch('/api/...')` |
| FastAPI Router | Python Service | Direct | `service.method()` |
| Python Service | Python Agent | Direct | `agent.process()` |
| Python Agent | Ollama | HTTP API | `aiohttp.post('http://localhost:11434/...')` |
| Python Service | Redis | Redis Client | `redis.get(key)` |
| Backend | NPU Worker | HTTP API | `POST http://localhost:8081/inference` |

## Common Patterns

### 1. Frontend Action Flow
```
User Click → Vue Component → API Call → FastAPI Router → Direct Call → Service → Direct Call → Agent
```

### 2. LLM Query Flow
```
Agent → Direct Call → LLMInterface → HTTP API → Ollama → Response
```

### 3. Real-time Updates
```
Backend Event → Direct Call → WebSocket Manager → WebSocket → Frontend
```

## Remember

- **APIs** = Crossing boundaries (process, container, network)
- **Direct** = Same Python process
- **When in doubt**: Is it in the same Python process? Yes = Direct, No = API
