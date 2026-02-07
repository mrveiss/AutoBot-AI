# Error Handling Migration Guide

This guide provides step-by-step instructions for migrating the AutoBot codebase
to use improved error handling patterns.

## Overview

The migration replaces generic error handling with specific exception types,
improves error logging, and ensures secure API responses.

## Migration Steps

### Step 1: Install New Error Handling Infrastructure

1. **Exception Hierarchy** - `src/exceptions.py`
   - Custom exception classes for different error scenarios
   - Safe error messages for user-facing responses
   - Error code mapping for HTTP status codes

2. **Error Utilities** - `src/error_handler.py`
   - Decorators for consistent error handling
   - Retry mechanisms with exponential backoff
   - Circuit breaker for external services
   - Safe API error formatting

### Step 2: Import Required Components

```python
# Add to files being migrated
from src.exceptions import (
    ValidationError,
    LLMError,
    WorkflowError,
    ResourceNotFoundError,
    InternalError,
    # ... other specific exceptions as needed
)
from src.error_handler import (
    log_error,
    with_error_handling,
    retry,
    safe_api_error,
    error_context
)
```

### Step 3: Replace Generic Exception Handlers

#### Before:
```python
try:
    result = some_operation()
except Exception as e:
    logger.error(f"Error: {e}")
    return None
```

#### After:
```python
try:
    result = some_operation()
except ValidationError as e:
    log_error(e, context="input_validation")
    raise  # Let caller handle
except DatabaseError as e:
    log_error(e, context="database_operation")
    return default_value  # Graceful degradation
except Exception as e:
    log_error(e, context="unexpected_error")
    raise InternalError("Operation failed") from e
```

### Step 4: Fix API Error Responses

#### Before:
```python
except Exception as e:
    return JSONResponse(status_code=500, content={"error": str(e)})
```

#### After:
```python
except AutoBotError as e:
    return JSONResponse(
        status_code=get_error_code(e),
        content=safe_api_error(e, request_id)
    )
except Exception as e:
    log_error(e, context="api_endpoint")
    return JSONResponse(
        status_code=500,
        content=safe_api_error(InternalError("An error occurred"), request_id)
    )
```

### Step 5: Remove Bare Except Clauses

#### Before:
```python
try:
    risky_operation()
except:
    pass  # Silent failure
```

#### After:
```python
try:
    risky_operation()
except SpecificException as e:
    log_error(e, context="risky_operation", include_traceback=False)
    # Handle appropriately or raise
```

### Step 6: Add Retry Logic for Transient Failures

```python
@retry(
    max_attempts=3,
    delay=1.0,
    exceptions=(ConnectionError, TimeoutError),
    on_retry=lambda e, attempt: logger.warning(f"Retry {attempt}: {e}")
)
async def call_external_service():
    # This will automatically retry on connection/timeout errors
    return await external_api.call()
```

### Step 7: Implement Circuit Breakers

```python
# For frequently failing services
llm_circuit = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=LLMError
)

@llm_circuit
async def call_llm_service():
    # After 5 failures, circuit opens for 60 seconds
    return await llm.generate()
```

### Step 8: Use Error Context Manager

```python
# For complex operations
with error_context("user_registration_flow"):
    validate_user_input(data)
    create_user_account(data)
    send_welcome_email(data)
    # Any exception will be logged with context
```

## File-by-File Migration Priority

### Critical (Security/Stability) - Week 1

1. **autobot-user-backend/api/chat.py**
   - Replace all `str(e)` in responses
   - Add request IDs for tracking
   - Implement specific error types

2. **autobot-user-backend/api/workflow.py**
   - Add workflow-specific exceptions
   - Implement proper error propagation
   - Add timeout handling

3. **autobot-user-backend/api/system.py**
   - Secure error responses
   - Add health check error handling

### High Priority (Core Functionality) - Week 2

1. **src/orchestrator.py**
   - Replace generic catches with specific types
   - Add retry logic for agent calls
   - Implement circuit breakers

2. **src/llm_interface.py**
   - Use LLMError subtypes
   - Add connection retry logic
   - Implement timeout handling

3. **src/knowledge_base.py**
   - Distinguish database vs logic errors
   - Add transaction error handling
   - Implement query timeouts

### Medium Priority (Agents) - Week 3

1. **autobot-user-backend/agents/base_agent.py**
   - Create AgentError hierarchy
   - Propagate errors properly
   - Add execution timeouts

2. **All agent implementations**
   - Replace generic catches
   - Add agent-specific error types
   - Implement fallback behaviors

## Testing Requirements

### Unit Tests
```python
def test_specific_error_handling():
    """Test that specific exceptions are raised correctly."""
    with pytest.raises(ValidationError) as exc_info:
        validate_input(invalid_data)

    assert exc_info.value.field == "expected_field"
    assert "Invalid" in exc_info.value.safe_message
```

### Integration Tests
```python
async def test_api_error_responses():
    """Test that APIs return safe error messages."""
    response = await client.post("/api/chat", json={"message": ""})

    assert response.status_code == 400
    assert "error" in response.json()
    assert "str object" not in response.json()["error"]  # No internal details
```

## Monitoring and Alerts

### Add Error Tracking
```python
# In error_handler.py or separate monitoring module
def track_error(error: Exception, context: dict):
    """Send error to monitoring service."""
    if isinstance(error, SecurityError):
        # Alert security team immediately
        send_security_alert(error, context)
    elif isinstance(error, InternalError):
        # Page on-call engineer
        send_critical_alert(error, context)
```

### Error Metrics
- Track error rates by type
- Monitor circuit breaker states
- Alert on error spikes
- Dashboard for error trends

## Rollback Plan

If issues arise during migration:

1. **Feature Flag Control**
   ```python
   if Config.USE_NEW_ERROR_HANDLING:
       # New error handling
   else:
       # Legacy error handling
   ```

2. **Gradual Rollout**
   - Start with non-critical endpoints
   - Monitor error rates
   - Expand gradually

3. **Quick Revert**
   - Keep legacy error handling in separate branch
   - Can revert individual files if needed

## Success Metrics

- [ ] Zero internal error details in API responses
- [ ] 50% reduction in "Unknown error" logs
- [ ] All bare except clauses removed
- [ ] 90% of errors have specific types
- [ ] Error tracking dashboard operational

## Code Review Checklist

When reviewing migrated code:

- [ ] No `str(e)` in API responses
- [ ] No bare `except:` clauses
- [ ] Specific exceptions caught before generic
- [ ] Errors logged with context
- [ ] Sensitive data not in error messages
- [ ] Retry logic for transient failures
- [ ] Timeouts for external calls
- [ ] Request IDs in API errors

## Common Pitfalls to Avoid

1. **Don't catch Exception too early** - Let specific handlers run first
2. **Don't expose stack traces** - Use safe_message property
3. **Don't ignore errors** - At least log them
4. **Don't retry non-transient failures** - Only retry network/timeout errors
5. **Don't create too many exception types** - Keep hierarchy simple

## Resources

- Exception hierarchy: `/src/exceptions.py`
- Error utilities: `/src/error_handler.py`
- Example implementation: `/autobot-user-backend/api/chat_improved.py`
- Original analysis: `/error_handling_analysis_report.md`
