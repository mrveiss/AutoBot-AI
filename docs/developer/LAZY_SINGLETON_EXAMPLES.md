# Lazy Singleton Migration Examples

**Date**: 2025-01-09
**Purpose**: Concrete before/after examples for migrating actual API files

This document shows real code from actual API files and how to migrate them using the lazy singleton utilities.

---

## Example 1: autobot-user-backend/api/chat.py (Lines 66-79)

### BEFORE - `get_chat_history_manager()`

```python
def get_chat_history_manager(request):
    """Get chat history manager from app state, with lazy initialization"""
    manager = getattr(request.app.state, "chat_history_manager", None)
    if manager is None:
        # Lazy initialize if not yet available
        try:
            from src.chat_history_manager import ChatHistoryManager

            manager = ChatHistoryManager()
            request.app.state.chat_history_manager = manager
            logger.info("✅ Lazy-initialized chat_history_manager")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize chat_history_manager: {e}")
    return manager
```

**Lines**: 14 lines
**Pattern**: Full lazy initialization with try/except

### AFTER - Using `lazy_init_singleton()`

```python
from src.utils.lazy_singleton import lazy_init_singleton

def get_chat_history_manager(request):
    """Get chat history manager from app state, with lazy initialization"""
    from src.chat_history_manager import ChatHistoryManager
    return lazy_init_singleton(request.app.state, "chat_history_manager", ChatHistoryManager)
```

**Lines**: 3 lines (+ 1 import at top of file)
**Savings**: 11 lines per function

---

## Example 2: autobot-user-backend/api/chat.py (Lines 92-105)

### BEFORE - `get_llm_service()`

```python
def get_llm_service(request):
    """Get LLM service from app state, with lazy initialization"""
    llm_service = getattr(request.app.state, "llm_service", None)
    if llm_service is None:
        # Lazy initialize if not yet available
        try:
            from src.llm_service import LLMService

            llm_service = LLMService()
            request.app.state.llm_service = llm_service
            logger.info("✅ Lazy-initialized llm_service")
        except Exception as e:
            logger.error(f"Failed to lazy-initialize llm_service: {e}")
    return llm_service
```

**Lines**: 14 lines
**Pattern**: Full lazy initialization with try/except

### AFTER - Using `lazy_init_singleton()`

```python
from src.utils.lazy_singleton import lazy_init_singleton

def get_llm_service(request):
    """Get LLM service from app state, with lazy initialization"""
    from src.llm_service import LLMService
    return lazy_init_singleton(request.app.state, "llm_service", LLMService)
```

**Lines**: 3 lines (+ 1 import at top of file)
**Savings**: 11 lines per function

---

## Example 3: autobot-user-backend/api/chat.py (Lines 82-84)

### BEFORE - `get_system_state()`

```python
def get_system_state(request):
    """Get system state from app state"""
    return getattr(request.app.state, "system_state", {})
```

**Lines**: 3 lines
**Pattern**: Simple getattr (no lazy initialization logic)

### AFTER - No Migration Needed

This function does NOT need migration because:
- No lazy initialization (no `if None` check)
- No try/except error handling
- No instance creation
- Already as simple as possible

**Action**: Leave as-is (no migration needed)

---

## Example 4: autobot-user-backend/api/chat.py (Lines 87-89)

### BEFORE - `get_memory_interface()`

```python
def get_memory_interface(request):
    """Get memory interface from app state"""
    return getattr(request.app.state, "memory_interface", None)
```

**Lines**: 3 lines
**Pattern**: Simple getattr (no lazy initialization logic)

### AFTER - No Migration Needed

This function does NOT need migration because:
- No lazy initialization (no `if None` check)
- No try/except error handling
- No instance creation
- Already as simple as possible

**Action**: Leave as-is (no migration needed)

---

## Migration Decision Tree

```
Is the function using getattr(request.app.state, ...)?
├─ YES → Continue
│   │
│   └─ Does it have "if instance is None:" check?
│       ├─ YES → Continue
│       │   │
│       │   └─ Does it create an instance inside the if block?
│       │       ├─ YES → ✅ MIGRATE (use lazy_init_singleton)
│       │       └─ NO → ❌ Skip (no migration needed)
│       │
│       └─ NO → ❌ Skip (no migration needed)
│
└─ NO → ❌ Skip (not a lazy initialization pattern)
```

---

## Complete File Migration Example

### Full autobot-user-backend/api/chat.py Migration

**Step 1**: Add import at top of file
```python
# At top of file with other imports
from src.utils.lazy_singleton import lazy_init_singleton
```

**Step 2**: Migrate eligible functions

**Functions TO migrate** (have full lazy init pattern):
- ✅ `get_chat_history_manager()` (lines 66-79)
- ✅ `get_llm_service()` (lines 92-105)

**Functions NOT to migrate** (simple getattr, no lazy init):
- ❌ `get_system_state()` (lines 82-84) - Simple getattr
- ❌ `get_memory_interface()` (lines 87-89) - Simple getattr

**Expected Impact**:
- 2 functions migrated
- ~22 lines removed
- 1 import added
- Net savings: ~21 lines

---

## Testing After Migration

### Manual Testing Steps

1. **Start the application**
   ```bash
   bash run_autobot.sh --dev
   ```

2. **Test chat endpoint**
   ```bash
   curl -X POST http://localhost:8001/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello", "conversation_id": "test"}'
   ```

3. **Check logs for lazy initialization**
   ```bash
   tail -f logs/backend.log | grep "Lazy-initialized"
   ```

   Expected output:
   ```
   ✅ Lazy-initialized chat_history_manager
   ✅ Lazy-initialized llm_service
   ```

4. **Verify idempotency** (send second request)
   ```bash
   # Second request should NOT show initialization logs
   curl -X POST http://localhost:8001/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello again", "conversation_id": "test"}'
   ```

5. **Test health check**
   ```bash
   curl http://localhost:8001/api/chat/health
   ```

---

## Rollback Procedure

If issues are encountered:

### Step 1: Identify Problem Function
```bash
# Check logs for errors
tail -f logs/backend.log | grep -i error
```

### Step 2: Revert Specific Function
```python
# Change back from this:
def get_llm_service(request):
    from src.llm_service import LLMService
    return lazy_init_singleton(request.app.state, "llm_service", LLMService)

# Back to this:
def get_llm_service(request):
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

### Step 3: Restart Application
```bash
bash run_autobot.sh --restart
```

### Step 4: Verify Fix
```bash
# Test the previously failing endpoint
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Test", "conversation_id": "test"}'
```

---

## Common Issues & Solutions

### Issue: "NameError: name 'lazy_init_singleton' is not defined"

**Cause**: Missing import statement

**Solution**: Add import at top of file
```python
from src.utils.lazy_singleton import lazy_init_singleton
```

### Issue: Service not initializing (returns None)

**Cause**: Factory is raising an exception during initialization

**Solution**: Check logs for error messages
```bash
tail -f logs/backend.log | grep "Failed to lazy-initialize"
```

Then fix the underlying initialization issue in the service class.

### Issue: Multiple instances being created

**Cause**: This should not happen - the utility ensures idempotency

**Solution**: Verify you're using the same `attribute_name` consistently
```python
# ✅ CORRECT - Same name
lazy_init_singleton(request.app.state, "my_service", MyService)
lazy_init_singleton(request.app.state, "my_service", MyService)

# ❌ WRONG - Different names
lazy_init_singleton(request.app.state, "my_service", MyService)
lazy_init_singleton(request.app.state, "myservice", MyService)  # Typo!
```

---

## Benefits Checklist

After migration, verify:

- [ ] Code is shorter (fewer lines)
- [ ] Error handling is consistent (automatic logging)
- [ ] Idempotency works (second call returns same instance)
- [ ] Service initializes on first use (check logs)
- [ ] Endpoints still work correctly
- [ ] Health checks still report correctly
- [ ] No new errors in logs

---

## Next Files to Migrate

Based on pattern analysis, these files likely have similar lazy initialization patterns:

1. `autobot-user-backend/api/intelligence.py` - Agent management
2. `autobot-user-backend/api/workflow.py` - Workflow services
3. `autobot-user-backend/api/memory.py` - Memory interfaces
4. `autobot-user-backend/api/tools.py` - Tool managers
5. `autobot-user-backend/api/agents.py` - Agent services

Use the same pattern:
1. Search for `getattr(request.app.state, ..., None)`
2. Check for `if instance is None:` pattern
3. If found, migrate using `lazy_init_singleton()`
4. Test thoroughly
5. Move to next file

---

## Summary

**Key Points**:
- Only migrate functions with full lazy initialization pattern
- Functions with simple `getattr()` don't need migration
- Add single import at top of file
- Each migration saves ~11 lines
- Test after each migration
- Easy to rollback if needed

**Migration Criteria**:
```python
# ✅ MIGRATE THIS
def get_service(request):
    service = getattr(request.app.state, "service", None)
    if service is None:
        try:
            from src.service import Service
            service = Service()
            request.app.state.service = service
            logger.info("Initialized")
        except Exception as e:
            logger.error(f"Failed: {e}")
    return service

# ❌ DON'T MIGRATE THIS
def get_service(request):
    return getattr(request.app.state, "service", None)
```

Ready to migrate! 🚀
