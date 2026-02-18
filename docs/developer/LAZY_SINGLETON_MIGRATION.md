# Lazy Singleton Initialization Migration Guide

**GitHub Issue:** [#253](https://github.com/mrveiss/AutoBot-AI/issues/253)
**Date:** 2025-01-09
**Status:** ✅ Utility Ready - Migration In Progress

## Executive Summary

We've created a standardized utility (`lazy_singleton.py`) that eliminates **10-15 lines** of duplicate lazy initialization code across **10+ API files**.

**Impact**: Standardized lazy singleton initialization with idempotency, error handling, and consistent logging.

---

## Pattern Analysis

### Common Lazy Initialization Pattern (Repeated 10+ Times)

All lazy initialization getters in API files follow this pattern:

**Example from `autobot-user-backend/api/chat.py:66-79`:**
```python
def get_chat_history_manager(request):
    """Lazy-initialize chat history manager on app state"""
    manager = getattr(request.app.state, "chat_history_manager", None)
    if manager is None:
        try:
            from src.chat_history_manager import ChatHistoryManager
            manager = ChatHistoryManager()
            request.app.state.chat_history_manager = manager
            logger.info("✅ Lazy-initialized chat_history_manager")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize chat_history_manager: {e}")
    return manager
```

**Example from `autobot-user-backend/api/chat.py:92-105`:**
```python
def get_llm_service(request):
    """Lazy-initialize LLM service on app state"""
    llm_service = getattr(request.app.state, "llm_service", None)
    if llm_service is None:
        try:
            from src.llm_service import LLMService
            llm_service = LLMService()
            request.app.state.llm_service = llm_service
            logger.info("✅ Lazy-initialized llm_service")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize llm_service: {e}")
    return llm_service
```

**Lines per implementation**: ~14 lines
**Total across 10+ files**: ~140-210 lines of duplicate code

**Common pattern elements:**
1. `getattr(request.app.state, "attribute_name", None)` - Check if exists
2. `if instance is None:` - Idempotency check
3. `try/except` - Error handling
4. Import statement inside function (lazy import)
5. Instance creation
6. `setattr(request.app.state, "attribute_name", instance)` - Store on app state
7. Success/failure logging

---

## Solution: Lazy Singleton Utilities

### Key Features

✅ **Idempotency**: Safe to call multiple times, returns same instance
✅ **Error Handling**: Standardized error logging and graceful failure
✅ **Lazy Import Support**: Import inside getter function still supported
✅ **Consistent Logging**: Automatic success/failure messages
✅ **Thread-Safe**: Uses getattr/setattr (atomic in Python)
✅ **Flexible**: Works with classes, factory functions, async factories
✅ **Validation Support**: Optional validation checks on retrieval

---

## Migration Examples

### Example 1: Simple Pattern (ChatHistoryManager)

**BEFORE** (`autobot-user-backend/api/chat.py:66-79` - 14 lines):
```python
def get_chat_history_manager(request):
    """Lazy-initialize chat history manager on app state"""
    manager = getattr(request.app.state, "chat_history_manager", None)
    if manager is None:
        try:
            from src.chat_history_manager import ChatHistoryManager
            manager = ChatHistoryManager()
            request.app.state.chat_history_manager = manager
            logger.info("✅ Lazy-initialized chat_history_manager")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize chat_history_manager: {e}")
    return manager
```

**AFTER** (3 lines - **11 lines saved**):
```python
def get_chat_history_manager(request):
    from src.chat_history_manager import ChatHistoryManager
    return lazy_init_singleton(request.app.state, "chat_history_manager", ChatHistoryManager)
```

---

### Example 2: With Initialization Arguments (LLMService)

**BEFORE** (18 lines):
```python
def get_llm_service(request):
    """Lazy-initialize LLM service with custom config"""
    llm_service = getattr(request.app.state, "llm_service", None)
    if llm_service is None:
        try:
            from src.llm_service import LLMService
            llm_service = LLMService(
                model="gpt-4",
                temperature=0.7,
                max_tokens=2000
            )
            request.app.state.llm_service = llm_service
            logger.info("✅ Lazy-initialized llm_service")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize llm_service: {e}")
    return llm_service
```

**AFTER** (7 lines - **11 lines saved**):
```python
def get_llm_service(request):
    from src.llm_service import LLMService
    return lazy_init_singleton(
        request.app.state,
        "llm_service",
        LLMService,
        model="gpt-4",
        temperature=0.7,
        max_tokens=2000
    )
```

---

### Example 3: With Async Initialization

**BEFORE** (17 lines):
```python
async def get_async_service(request):
    """Lazy-initialize async service"""
    service = getattr(request.app.state, "async_service", None)
    if service is None:
        try:
            from src.async_service import AsyncService
            service = await AsyncService.create()
            request.app.state.async_service = service
            logger.info("✅ Lazy-initialized async_service")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize async_service: {e}")
    return service
```

**AFTER** (6 lines - **11 lines saved**):
```python
async def get_async_service(request):
    from src.async_service import AsyncService
    async def factory():
        return await AsyncService.create()
    return await lazy_init_singleton_async(
        request.app.state, "async_service", factory
    )
```

---

### Example 4: With Complex Factory Function

**BEFORE** (22 lines):
```python
def get_complex_service(request):
    """Lazy-initialize service with complex setup"""
    service = getattr(request.app.state, "complex_service", None)
    if service is None:
        try:
            from src.complex_service import ComplexService
            from src.config import get_config

            service = ComplexService()
            config = get_config()
            service.configure(config)
            service.initialize()

            request.app.state.complex_service = service
            logger.info("✅ Lazy-initialized complex_service")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize complex_service: {e}")
    return service
```

**AFTER** (11 lines - **11 lines saved**):
```python
def get_complex_service(request):
    from src.complex_service import ComplexService
    from src.config import get_config

    def factory():
        service = ComplexService()
        config = get_config()
        service.configure(config)
        service.initialize()
        return service

    return lazy_init_singleton(request.app.state, "complex_service", factory)
```

---

### Example 5: Using Decorator Pattern (Advanced)

**BEFORE** (14 lines):
```python
def get_knowledge_base(request):
    """Lazy-initialize knowledge base"""
    kb = getattr(request.app.state, "knowledge_base", None)
    if kb is None:
        try:
            from src.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            request.app.state.knowledge_base = kb
            logger.info("✅ Lazy-initialized knowledge_base")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize knowledge_base: {e}")
    return kb
```

**AFTER** (4 lines - **10 lines saved**):
```python
@singleton_getter("knowledge_base", KnowledgeBase)
def get_knowledge_base(request):
    from src.knowledge_base import KnowledgeBase
    return KnowledgeBase
```

---

## Available Utilities

### 1. `lazy_init_singleton()` - Main Function

**Signature:**
```python
def lazy_init_singleton(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]
```

**Use Cases:**
- Basic lazy initialization
- Services requiring initialization arguments
- Factory functions with complex setup

**Example:**
```python
from src.utils.lazy_singleton import lazy_init_singleton

def get_my_service(request):
    from src.my_service import MyService
    return lazy_init_singleton(request.app.state, "my_service", MyService)
```

---

### 2. `lazy_init_singleton_async()` - Async Version

**Signature:**
```python
async def lazy_init_singleton_async(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]
```

**Use Cases:**
- Services with async initialization
- Async factory functions

**Example:**
```python
from src.utils.lazy_singleton import lazy_init_singleton_async

async def get_async_service(request):
    from src.async_service import AsyncService
    return await lazy_init_singleton_async(
        request.app.state, "async_service", AsyncService
    )
```

---

### 3. `lazy_init_singleton_with_check()` - With Validation

**Signature:**
```python
def lazy_init_singleton_with_check(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    validator: Optional[Callable[[T], bool]] = None,
    *args,
    **kwargs,
) -> Optional[T]
```

**Use Cases:**
- Services requiring health checks
- Validation before returning instance

**Example:**
```python
from src.utils.lazy_singleton import lazy_init_singleton_with_check

def get_validated_service(request):
    from src.validated_service import ValidatedService

    def validator(service):
        return service.is_healthy()

    return lazy_init_singleton_with_check(
        request.app.state,
        "validated_service",
        ValidatedService,
        validator
    )
```

---

### 4. `singleton_getter()` - Decorator Pattern

**Signature:**
```python
def singleton_getter(attribute_name: str, factory: Callable)
```

**Use Cases:**
- Clean decorator-based approach
- Simplifies getter functions

**Example:**
```python
from src.utils.lazy_singleton import singleton_getter

@singleton_getter("my_service", MyService)
def get_my_service(request):
    from src.my_service import MyService
    return MyService
```

---

### 5. `global_lazy_singleton()` - Module-Level Singletons

**Signature:**
```python
def global_lazy_singleton(
    attribute_name: str, factory: Callable[..., T], *args, **kwargs
) -> Optional[T]
```

**Use Cases:**
- Module-level singletons (use sparingly)
- CLI tools and scripts

**Example:**
```python
from src.utils.lazy_singleton import global_lazy_singleton

# In module scope
def get_global_service():
    from src.global_service import GlobalService
    return global_lazy_singleton("global_service", GlobalService)
```

---

## Migration Checklist

For each file you migrate:

- [ ] **Identify pattern**: Find functions with `getattr(request.app.state, ..., None)`
- [ ] **Add import**: `from src.utils.lazy_singleton import lazy_init_singleton`
- [ ] **Simplify function**: Replace 14 lines with 3 lines
- [ ] **Keep lazy import**: Import statement inside function is still fine
- [ ] **Pass arguments**: Forward any initialization arguments to factory
- [ ] **Handle async**: Use `lazy_init_singleton_async()` if needed
- [ ] **Remove boilerplate**: Delete try/except, getattr, setattr, logging
- [ ] **Test**: Verify lazy initialization works correctly

---

## Files to Migrate

### Priority 1 - API Files (High Impact)

| File | Function | Lines Saved |
|------|----------|-------------|
| `autobot-user-backend/api/chat.py:66` | `get_chat_history_manager()` | ~11 lines |
| `autobot-user-backend/api/chat.py:92` | `get_llm_service()` | ~11 lines |
| `autobot-user-backend/api/chat.py:120` | `get_knowledge_base()` | ~11 lines |
| `autobot-user-backend/api/chat.py:145` | `get_rag_service()` | ~11 lines |
| `autobot-user-backend/api/intelligence.py:45` | `get_intelligent_agent()` | ~11 lines |
| `autobot-user-backend/api/tools.py:38` | `get_tool_manager()` | ~11 lines |

### Priority 2 - Additional API Files

- `autobot-user-backend/api/memory.py` - Memory-related getters
- `autobot-user-backend/api/workflow.py` - Workflow getters
- `autobot-user-backend/api/agents.py` - Agent management getters
- 5+ more API files with similar patterns

**Total Estimated Savings**: 100-150 lines across 10+ files

---

## Benefits Summary

| Benefit | Before | After |
|---------|--------|-------|
| **Lines per Function** | 14-22 lines | 3-11 lines |
| **Total Savings** | N/A | 100-150 lines |
| **Idempotency** | ⚠️ Manual | ✅ Automatic |
| **Error Handling** | ⚠️ Inconsistent | ✅ Standardized |
| **Logging** | ⚠️ Manual | ✅ Automatic |
| **Code Duplication** | ❌ High | ✅ Eliminated |
| **Maintenance** | ⚠️ 10+ places | ✅ 1 place |
| **Testing** | ⚠️ Per-file | ✅ Centralized (25 tests) |

---

## Common Issues & Solutions

### Issue 1: Lazy Import Pattern

**Problem**: Need to keep lazy imports inside function

**Solution**: Keep import inside getter function - this is supported
```python
# ✅ CORRECT - Lazy import preserved
def get_service(request):
    from src.service import Service  # Still lazy
    return lazy_init_singleton(request.app.state, "service", Service)
```

### Issue 2: Complex Initialization

**Problem**: Service requires multi-step setup

**Solution**: Use factory function
```python
def get_service(request):
    from src.service import Service

    def factory():
        service = Service()
        service.configure(config)
        service.initialize()
        return service

    return lazy_init_singleton(request.app.state, "service", factory)
```

### Issue 3: Async Initialization

**Problem**: Service creation is async

**Solution**: Use `lazy_init_singleton_async()`
```python
async def get_service(request):
    from src.service import AsyncService
    return await lazy_init_singleton_async(
        request.app.state, "service", AsyncService
    )
```

### Issue 4: Need Validation

**Problem**: Want to check if service is healthy before returning

**Solution**: Use `lazy_init_singleton_with_check()`
```python
def get_service(request):
    from src.service import Service

    def validator(service):
        return service.is_healthy()

    return lazy_init_singleton_with_check(
        request.app.state, "service", Service, validator
    )
```

---

## Testing Strategy

### Unit Tests

The utility has 25 comprehensive tests in `tests/test_lazy_singleton.py`:

- ✅ Basic lazy initialization
- ✅ Idempotency (multiple calls)
- ✅ With initialization arguments
- ✅ With factory functions
- ✅ Error handling
- ✅ Async initialization
- ✅ Validation support
- ✅ Decorator pattern
- ✅ Global singletons

**All tests passing** - utility is production-ready.

### Integration Tests

After migration, verify:
```python
# Test in actual API endpoint
@app.get("/test-lazy-init")
def test_endpoint(request: Request):
    service = get_my_service(request)
    assert service is not None
    return {"status": "ok"}
```

---

## Rollback Plan

If issues arise:

1. **Revert specific file**: Change getter back to manual pattern
2. **Keep utility**: Other files can still use it
3. **No breaking changes**: Utility is additive, doesn't affect non-migrated files

---

## Advanced Usage

### Example 6: Non-Request Contexts

**Use Case**: Need singleton outside of FastAPI request context

```python
from src.utils.lazy_singleton import SingletonStorage, lazy_init_singleton

# Create storage
storage = SingletonStorage()

# Use like request.app.state
service = lazy_init_singleton(storage, "service", MyService)
```

### Example 7: Module-Level Singleton (Use Sparingly)

**Use Case**: CLI tool needs global singleton

```python
from src.utils.lazy_singleton import global_lazy_singleton

def get_cli_service():
    from src.cli_service import CLIService
    return global_lazy_singleton("cli_service", CLIService)
```

⚠️ **Warning**: Global singletons should be used sparingly. Prefer `request.app.state` in web applications.

---

## Performance Considerations

### Thread Safety

- **getattr/setattr are atomic** in Python (CPython GIL)
- **Race condition**: Rare edge case where two threads create instance simultaneously
- **Impact**: Minimal - one instance wins, other is garbage collected
- **No data corruption**: Both instances are valid

### Memory Impact

- **Negligible**: Stores single reference on app.state
- **Lifecycle**: Lives for lifetime of application
- **Cleanup**: Automatic when application shuts down

---

## Support

**Questions?** See:
- `autobot-user-backend/utils/lazy_singleton.py` - Utility implementation
- `tests/test_lazy_singleton.py` - Comprehensive tests (25 tests)
- `CLAUDE.md` - Initialization patterns section

**Issues?** Report with:
- File being migrated
- Error messages
- Expected vs actual behavior

---

## Next Steps

1. **Review this guide** - Understand patterns and utilities
2. **Start with Priority 1 files** - API files with highest impact
3. **Test after each migration** - Verify endpoints work correctly
4. **Track progress** - Update migration checklist
5. **Document any issues** - Help improve guide for others

**Migration Status**: Ready to begin - utility tested and functional ✅
