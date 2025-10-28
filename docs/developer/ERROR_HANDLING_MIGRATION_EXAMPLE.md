# Error Handling Migration Example

**Purpose**: Demonstrate how to migrate API endpoints from manual try-catch blocks to the new `@with_error_handling` decorator

**Status**: Phase 2 - Implementation Guide
**Created**: 2025-10-28
**Part of**: ERROR_HANDLING_REFACTORING_PLAN.md Phase 2

---

## Quick Start

### Import the New Decorator
```python
from src.utils.error_boundaries import with_error_handling, ErrorCategory
```

---

## Migration Pattern 1: Health Check Endpoint

### BEFORE (Manual Error Handling)
```python
@router.get("/chat/health")
async def chat_health_check(request: Request):
    """Health check for chat service"""
    try:
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        llm_service = getattr(request.app.state, "llm_service", None)

        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "chat_history_manager": (
                    "healthy" if chat_history_manager else "unavailable"
                ),
                "llm_service": "healthy" if llm_service else "unavailable",
            },
        }

        overall_healthy = all(
            status == "healthy" for status in health_status["components"].values()
        )

        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(
            status_code=200 if overall_healthy else 503, content=health_status
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
```

**Issues with this pattern:**
- 16 lines of error handling code (lines 1300-1309)
- Manual status code management
- Inconsistent error response format
- No trace ID for debugging
- No error code for cataloging
- Error handling logic mixed with business logic

### AFTER (With @with_error_handling Decorator)
```python
@router.get("/chat/health")
@with_error_handling(
    category=ErrorCategory.SERVICE_UNAVAILABLE,
    operation="chat_health_check",
    error_code_prefix="CHAT"
)
async def chat_health_check(request: Request):
    """Health check for chat service"""
    chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
    llm_service = getattr(request.app.state, "llm_service", None)

    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "chat_history_manager": (
                "healthy" if chat_history_manager else "unavailable"
            ),
            "llm_service": "healthy" if llm_service else "unavailable",
        },
    }

    overall_healthy = all(
        status == "healthy" for status in health_status["components"].values()
    )

    if not overall_healthy:
        health_status["status"] = "degraded"

    return JSONResponse(
        status_code=200 if overall_healthy else 503, content=health_status
    )
```

**Benefits:**
- ✅ Eliminated 16 lines of error handling code
- ✅ Automatic HTTP status code (503) from ErrorCategory.SERVICE_UNAVAILABLE
- ✅ Automatic trace ID generation for debugging
- ✅ Automatic error code (e.g., CHAT_0042)
- ✅ Standardized error response format
- ✅ Automatic error logging with context
- ✅ Business logic clearly separated from error handling

**Error Response Example:**
```json
{
  "error": {
    "category": "service_unavailable",
    "message": "Chat history manager not initialized",
    "code": "CHAT_1234",
    "timestamp": 1730107234.567,
    "details": {
      "operation": "chat_health_check"
    },
    "trace_id": "chat_health_check_1730107234567"
  }
}
```

---

## Migration Pattern 2: POST Endpoint with Validation

### BEFORE (Manual Error Handling)
```python
@router.post("/chat")
@router.post("/chat/message")  # Alternative endpoint
async def send_message(
    message: ChatMessage,
    request: Request,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """Send a chat message and get AI response"""
    request_id = generate_request_id()

    try:
        log_request_context(request, "send_message", request_id)

        # Validate message content
        if not message.content or not message.content.strip():
            raise ValidationError("Message content cannot be empty")

        # Get dependencies from request state
        chat_history_manager = get_chat_history_manager(request)
        llm_service = get_llm_service(request)
        memory_interface = get_memory_interface(request)

        # Process the chat message
        response_data = await process_chat_message(
            message,
            chat_history_manager,
            llm_service,
            memory_interface,
            knowledge_base,
            config,
            request_id,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": response_data,
                "message": "Message processed successfully",
                "request_id": request_id,
            },
        )

    except Exception as e:
        logger.error(f"[{request_id}] send_message error: {e}")
        return create_error_response(
            error_code="INTERNAL_ERROR",
            message=str(e),
            request_id=request_id,
            status_code=500,
        )
```

**Issues:**
- Generic Exception catching (loses error context)
- Manual request_id generation
- Calls `create_error_response()` helper (another layer of abstraction)
- Hardcoded status code (500)
- No error categorization

### AFTER (With @with_error_handling Decorator)
```python
@router.post("/chat")
@router.post("/chat/message")  # Alternative endpoint
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_message",
    error_code_prefix="CHAT"
)
async def send_message(
    message: ChatMessage,
    request: Request,
    config=Depends(get_config),
    knowledge_base=Depends(get_knowledge_base),
):
    """Send a chat message and get AI response"""
    # Validate message content
    if not message.content or not message.content.strip():
        raise ValueError("Message content cannot be empty")  # Will be caught by decorator

    # Get dependencies from request state
    chat_history_manager = get_chat_history_manager(request)
    llm_service = get_llm_service(request)
    memory_interface = get_memory_interface(request)

    # Process the chat message
    response_data = await process_chat_message(
        message,
        chat_history_manager,
        llm_service,
        memory_interface,
        knowledge_base,
        config,
        None,  # No manual request_id - trace_id auto-generated
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": response_data,
            "message": "Message processed successfully",
        },
    )
```

**Benefits:**
- ✅ Removed 9 lines of error handling code
- ✅ Removed manual request_id generation (decorator provides trace_id)
- ✅ Removed `create_error_response()` call
- ✅ Automatic error categorization
- ✅ Simpler, cleaner code
- ✅ Consistent error format across all endpoints

---

## Migration Pattern 3: Endpoint with Custom Error Categories

### Use Case: Not Found Errors

```python
@router.get("/chat/sessions/{session_id}")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_session",
    error_code_prefix="SESSION"
)
async def get_session(session_id: str, request: Request):
    """Get chat session details"""
    chat_history_manager = get_chat_history_manager(request)

    session = await chat_history_manager.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")  # → 404 error

    return session
```

**Error Response (404):**
```json
{
  "error": {
    "category": "not_found",
    "message": "Session abc123 not found",
    "code": "SESSION_0567",
    "timestamp": 1730107234.567,
    "trace_id": "get_session_1730107234567"
  }
}
```

### Use Case: Validation Errors

```python
@router.post("/chat/validate")
@with_error_handling(
    category=ErrorCategory.VALIDATION,
    operation="validate_message",
    error_code_prefix="VAL"
)
async def validate_message(data: dict):
    """Validate message data"""
    if "content" not in data:
        raise ValueError("Missing required field: content")  # → 400 error

    if len(data["content"]) > 10000:
        raise ValueError("Content too long (max 10000 chars)")  # → 400 error

    return {"valid": True}
```

**Error Response (400):**
```json
{
  "error": {
    "category": "validation",
    "message": "Missing required field: content",
    "code": "VAL_0123",
    "timestamp": 1730107234.567
  }
}
```

### Use Case: Rate Limiting

```python
@router.post("/chat/message")
@with_error_handling(
    category=ErrorCategory.RATE_LIMIT,
    operation="send_message",
    error_code_prefix="RATE"
)
async def send_message(message: ChatMessage, request: Request):
    """Send message with rate limiting"""
    if await is_rate_limited(request):
        raise ValueError("Too many requests")  # → 429 error

    return await process_message(message)
```

**Error Response (429):**
```json
{
  "error": {
    "category": "rate_limit",
    "message": "Too many requests",
    "code": "RATE_8901",
    "timestamp": 1730107234.567,
    "retry_after": 60
  }
}
```

---

## Error Category Mapping

| ErrorCategory | HTTP Status | Use Case |
|---------------|-------------|----------|
| VALIDATION | 400 | Invalid input, missing fields |
| AUTHENTICATION | 401 | Invalid credentials, expired token |
| AUTHORIZATION | 403 | Insufficient permissions |
| NOT_FOUND | 404 | Resource doesn't exist |
| CONFLICT | 409 | Resource already exists |
| RATE_LIMIT | 429 | Too many requests |
| SERVER_ERROR | 500 | Internal server error |
| EXTERNAL_SERVICE | 502 | Upstream service error |
| SERVICE_UNAVAILABLE | 503 | Service temporarily down |

---

## Migration Checklist

For each endpoint:

1. **Add Import** (top of file):
   ```python
   from src.utils.error_boundaries import with_error_handling, ErrorCategory
   ```

2. **Add Decorator** (before endpoint function):
   ```python
   @with_error_handling(
       category=ErrorCategory.SERVER_ERROR,  # Choose appropriate category
       operation="function_name",
       error_code_prefix="MODULE"
   )
   ```

3. **Remove Try-Catch Block**:
   - Delete `try:` line
   - Un-indent business logic
   - Delete `except Exception as e:` block
   - Delete manual error response creation

4. **Remove Manual Error Handling**:
   - Delete `request_id = generate_request_id()` (if only used for errors)
   - Delete `logger.error()` calls (decorator logs automatically)
   - Delete `create_error_response()` calls
   - Delete `return JSONResponse(status_code=500, ...)` for errors

5. **Test**:
   - Verify success case works
   - Verify error case returns correct status code
   - Verify error response has trace_id
   - Check logs for proper error logging

---

## Code Savings

### Single Endpoint Example
- **Before**: ~60 lines (business logic + error handling)
- **After**: ~40 lines (business logic only)
- **Savings**: 20 lines (33% reduction)
- **Error handling**: 3 lines decorator vs 15+ lines manual

### Full Migration Estimates
- **chat.py**: 32 try blocks → ~640 lines savings
- **knowledge.py**: 76 try blocks → ~1,520 lines savings
- **Total backend**: 1,070 try blocks → ~21,400 lines savings

---

## Testing

### Test Error Response Format
```python
# Test endpoint
response = client.post("/chat/message", json={"content": ""})

# Verify response
assert response.status_code == 400
assert "error" in response.json()
assert response.json()["error"]["category"] == "validation"
assert "trace_id" in response.json()["error"]
assert "code" in response.json()["error"]
```

### Test Automatic Logging
```python
# Errors automatically logged with context:
# ERROR:src.utils.error_boundaries:Error in send_message: Message content cannot be empty
#   (trace_id: send_message_1730107234567, code: CHAT_0042)
```

---

## Next Steps

1. **Phase 2a** (Sprint 2): Migrate high-traffic endpoints
   - `backend/api/chat.py` (32 try blocks)
   - `backend/api/knowledge.py` (76 try blocks)

2. **Phase 2b** (Sprint 3): Migrate remaining API endpoints
   - Session, workflow, file browser, terminal APIs

3. **Phase 3** (Sprint 4): Migrate core service layer
   - src/knowledge_base.py
   - src/chat_workflow_manager.py
   - src/llm_interface.py

---

## Questions & Support

**Q: What if I need custom error handling?**
A: Keep the try-catch for specific logic, use decorator for generic errors:
```python
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def complex_operation():
    try:
        specific_risky_operation()
    except SpecificError as e:
        # Handle specific case
        return custom_response()

    # Other errors caught by decorator
    general_operation()
```

**Q: Can I use multiple decorators?**
A: Yes, but only one @with_error_handling per function

**Q: What about streaming endpoints?**
A: Decorator works with StreamingResponse, but error handling is limited once streaming starts

---

**Document Status**: Ready for Phase 2 Implementation
**Last Updated**: 2025-10-28
**Related**: docs/developer/ERROR_HANDLING_REFACTORING_PLAN.md
