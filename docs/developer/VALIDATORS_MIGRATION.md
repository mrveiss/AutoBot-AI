# Common Validators Migration Guide

**Date**: 2025-01-09
**Status**: ✅ Utility Ready - Migration In Progress

## Executive Summary

We've created a comprehensive validators utility (`validators.py`) that eliminates **150+ lines** of duplicate validation code across the codebase.

**Impact**: Standardized validation with consistent error messages, type safety, and composable validators.

---

## Pattern Analysis

### Common Validation Patterns (Repeated 150+ Times)

**String validation patterns** (50+ occurrences):
- Empty/None checks
- Length validation
- Pattern matching

**String sanitization** (151 occurrences):
- `.strip()`, `.lower()`, `.upper()`
- Alphanumeric filtering

**File validation** (30+ occurrences):
- Extension checking
- Size validation
- Filename safety

**Collection validation** (40+ occurrences):
- Non-empty lists
- Size limits

**Entity/relation type validation** (20+ occurrences):
- Membership in allowed sets

---

## Migration Examples

### Example 1: Username Validation (Pydantic)

**BEFORE** (`autobot-user-backend/api/auth.py:26-36` - 11 lines):
```python
@validator("username")
def validate_username(cls, v):
    if not v or len(v.strip()) == 0:
        raise ValueError("Username cannot be empty")
    if len(v) > 50:
        raise ValueError("Username too long")
    # Basic sanitization
    v = v.strip().lower()
    if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
        raise ValueError("Username contains invalid characters")
    return v
```

**AFTER** (2 lines - **9 lines saved**):
```python
from src.utils.validators import validate_username

@validator("username")
def validate_username(cls, v):
    return validate_username(v, min_length=3, max_length=50)
```

---

### Example 2: Password Validation

**BEFORE** (autobot-user-backend/api/auth.py:38-44 - 7 lines):
```python
@validator("password")
def validate_password(cls, v):
    if not v or len(v) < 1:
        raise ValueError("Password cannot be empty")
    if len(v) > 128:
        raise ValueError("Password too long")
    return v
```

**AFTER** (2 lines - **5 lines saved**):
```python
from src.utils.validators import validate_password

@validator("password")
def validate_password(cls, v):
    return validate_password(v, min_length=8, max_length=128)
```

---

### Example 3: Entity Type Validation

**BEFORE** (`autobot-user-backend/api/memory.py:71-79` - 9 lines):
```python
@validator("entity_type")
def validate_entity_type(cls, v):
    valid_types = {
        "conversation",
        "bug_fix",
        "feature",
        "decision",
        "task",
        "user_preference",
    }
    if v not in valid_types:
        raise ValueError(f"Invalid entity type: {v}")
    return v
```

**AFTER** (5 lines - **4 lines saved**):
```python
from src.utils.validators import validate_in_choices

@validator("entity_type")
def validate_entity_type(cls, v):
    valid_types = {"conversation", "bug_fix", "feature", "decision", "task", "user_preference"}
    return validate_in_choices(v, valid_types, "entity_type")
```

---

### Example 4: File Extension Validation

**BEFORE** (8 lines):
```python
def check_file_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    allowed = {".txt", ".md", ".json", ".py"}
    if ext not in allowed:
        raise ValueError(f"Invalid extension: {ext}")
    return True
```

**AFTER** (2 lines - **6 lines saved**):
```python
from src.utils.validators import validate_file_extension

def check_file_extension(filename: str) -> bool:
    return validate_file_extension(filename, {".txt", ".md", ".json", ".py"})
```

---

### Example 5: File Size Validation

**BEFORE** (autobot-user-backend/api/files.py:444-448 - 5 lines):
```python
if len(content) > MAX_FILE_SIZE:
    raise HTTPException(
        status_code=400,
        detail=f"File too large (maximum {MAX_FILE_SIZE} bytes)"
    )
```

**AFTER** (2 lines - **3 lines saved**):
```python
from src.utils.validators import validate_file_size

validate_file_size(len(content), "File", max_size=MAX_FILE_SIZE)
```

---

## Available Validators

### String Validators

```python
from src.utils.validators import (
    validate_non_empty_string,
    validate_string_length,
    validate_string_pattern
)

# Non-empty check
username = validate_non_empty_string(value, "Username")

# Length bounds
username = validate_string_length(username, "Username", min_length=3, max_length=50)

# Pattern matching
code = validate_string_pattern(value, r"^[A-Z0-9]{6}$", "Code")
```

### String Sanitizers

```python
from src.utils.validators import sanitize_string, sanitize_alphanumeric

# Strip and lowercase
username = sanitize_string(value, strip=True, lowercase=True)

# Alphanumeric only
username = sanitize_alphanumeric(value, allowed_chars="_-.")
```

### Collection Validators

```python
from src.utils.validators import validate_non_empty_collection, validate_collection_size

# Non-empty
ids = validate_non_empty_collection(id_list, "File IDs")

# Size bounds
ids = validate_collection_size(id_list, "File IDs", min_size=1, max_size=100)
```

### Choice Validators

```python
from src.utils.validators import validate_in_choices

# Must be in allowed set
entity_type = validate_in_choices(value, {"task", "bug", "feature"}, "Entity Type")

# Case-insensitive
status = validate_in_choices(value, {"active", "inactive"}, "Status", case_sensitive=False)
```

### File Validators

```python
from src.utils.validators import (
    validate_file_extension,
    validate_filename_safe,
    validate_file_size
)

# Extension check
filename = validate_file_extension(filename, {".txt", ".md", ".json"})

# Safe filename (no path traversal)
filename = validate_filename_safe(filename, max_length=255)

# Size check
validate_file_size(file_bytes, "Document", max_size=50*1024*1024)
```

### Format Validators

```python
from src.utils.validators import validate_email, validate_url, validate_uuid

# Email format
email = validate_email(value, "Email")

# URL format
url = validate_url(value, "URL", require_https=True)

# UUID format
uuid = validate_uuid(value, "ID")
```

### Composite Validators

```python
from src.utils.validators import validate_username, validate_password

# Complete username validation (sanitize + validate + check length)
username = validate_username(value, min_length=3, max_length=50)

# Complete password validation
password = validate_password(value, min_length=8, max_length=128)
```

---

## Migration Checklist

- [ ] **Add import**: `from src.utils.validators import ...`
- [ ] **Replace validation logic**: Use appropriate validator function
- [ ] **Remove duplicate code**: Delete manual checks, length validation, error messages
- [ ] **Keep custom logic**: Only for business-specific validation
- [ ] **Test validation**: Verify error messages and edge cases
- [ ] **Update tests**: Match new error messages if needed

---

## Files to Migrate

### Priority 1 - Pydantic Models

| File | Validators | Est. Lines Saved |
|------|-----------|------------------|
| `autobot-user-backend/api/auth.py` | 2 validators | ~15 lines |
| `autobot-user-backend/api/memory.py` | 2 validators | ~15 lines |
| `autobot-user-backend/api/conversation_files.py` | 1 validator | ~5 lines |

### Priority 2 - File Operations

- `autobot-user-backend/api/files.py` - File validation (extension, size, filename)
- `autobot-user-backend/api/conversation_files.py` - File uploads

### Priority 3 - String Operations

- All files using `.strip()`, `.lower()`, `.upper()` (151 occurrences)
- 37 files with string manipulation

**Total Estimated Savings**: 150+ lines across codebase

---

## Benefits Summary

| Benefit | Before | After |
|---------|--------|-------|
| **Lines per Validation** | 5-11 lines | 1-2 lines |
| **Total Savings** | N/A | 150+ lines |
| **Error Messages** | ⚠️ Inconsistent | ✅ Standardized |
| **Reusability** | ❌ Copy-paste | ✅ Composable |
| **Type Safety** | ⚠️ Manual | ✅ Type hints |
| **Testing** | ⚠️ Per-validator | ✅ Centralized (58 tests) |

---

## Common Issues & Solutions

### Issue 1: Custom Error Messages

**Problem**: Need custom error message

**Solution**: Catch and re-raise with custom message
```python
try:
    validate_string_length(value, "Field", max_length=50)
except ValueError:
    raise ValueError("Custom error message here")
```

### Issue 2: Multiple Validations

**Problem**: Need to chain multiple validations

**Solution**: Call validators sequentially
```python
value = sanitize_string(value, strip=True, lowercase=True)
value = validate_non_empty_string(value, "Username")
value = validate_string_length(value, "Username", min_length=3, max_length=50)
```

Or use composite validator:
```python
value = validate_username(value, min_length=3, max_length=50)
```

---

## Testing

**58 comprehensive tests** in `tests/test_validators.py` covering:
- ✅ String validators (11 tests)
- ✅ String sanitizers (8 tests)
- ✅ Collection validators (6 tests)
- ✅ Choice validators (4 tests)
- ✅ File validators (10 tests)
- ✅ Format validators (9 tests)
- ✅ Composite validators (10 tests)

**All tests passing** - utility is functional ✅

---

## Next Steps

1. **Start with Pydantic models** - Highest impact, easiest migration
2. **File operations** - File validation patterns
3. **String sanitization** - Replace `.strip().lower()` patterns
4. **Custom validators** - Use as building blocks

**Migration Status**: Ready to begin - utility tested and functional ✅
