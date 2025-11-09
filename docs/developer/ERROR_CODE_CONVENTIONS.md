# Error Code Conventions

**Version:** 1.0.0
**Last Updated:** 2025-11-09
**Phase:** 4 - Error Message Catalog

---

## Overview

This document defines the conventions and best practices for using the centralized error catalog system in AutoBot.

## Error Code Format

All error codes follow the format: `{PREFIX}_{NUMBER}`

- **PREFIX**: Component identifier (2-4 uppercase letters)
- **NUMBER**: Unique 4-digit identifier (0001-9999)

**Examples:**
- `KB_0001` - Knowledge Base error #1
- `LLM_0002` - LLM Service error #2
- `AUTH_0003` - Authentication error #3

---

## Component Prefixes

| Prefix | Component | Description |
|--------|-----------|-------------|
| `KB` | Knowledge Base | Vector search, fact management |
| `AUTH` | Authentication | User/service authentication |
| `LLM` | LLM Service | Ollama, OpenAI, model interactions |
| `CHAT` | Chat Workflow | Session management, message processing |
| `API` | API General | Generic API errors, validation |
| `DB` | Database | Redis, data layer operations |
| `MEM` | Memory Graph | Entity-relationship tracking |
| `SYS` | System | System initialization, configuration |

---

## Error Categories

Every error must have a category that maps to the `ErrorCategory` enum:

```python
class ErrorCategory(Enum):
    VALIDATION = "validation"              # 400 errors
    AUTHENTICATION = "authentication"      # 401 errors
    AUTHORIZATION = "authorization"        # 403 errors
    NOT_FOUND = "not_found"               # 404 errors
    CONFLICT = "conflict"                 # 409 errors
    RATE_LIMIT = "rate_limit"             # 429 errors
    SERVER_ERROR = "server_error"         # 500 errors
    SERVICE_UNAVAILABLE = "service_unavailable"  # 503 errors
    EXTERNAL_SERVICE = "external_service"  # External API failures
    DATABASE = "database"                 # Database-specific errors
    SYSTEM = "system"                     # System-level errors
```

---

## Catalog Structure

Error definitions in `config/error_messages.yaml`:

```yaml
component_name:
  ERROR_CODE:
    category: error_category       # ErrorCategory enum value
    message: "User-facing message"  # Clear, non-technical message
    status_code: 500               # HTTP status code
    retry: true                    # Whether client should retry
    retry_after: 30                # Seconds to wait before retry (optional)
    details: "Technical details"   # Additional context (optional)
```

**Example:**

```yaml
knowledge_base:
  KB_0001:
    category: server_error
    message: "Failed to initialize knowledge base"
    status_code: 500
    retry: true
    retry_after: 30
    details: "Check Redis connection and ChromaDB availability"
```

---

## Usage Patterns

### 1. Simple Error Raising

```python
from src.utils.catalog_http_exceptions import raise_catalog_error_simple

# Raise error with catalog code
raise_catalog_error_simple("KB_0001")

# Add additional context
raise_catalog_error_simple("KB_0001", "ChromaDB connection timeout")
```

### 2. Category-Specific Helpers

```python
from src.utils.catalog_http_exceptions import (
    raise_auth_error,
    raise_validation_error,
    raise_not_found_error,
    raise_server_error,
    raise_kb_error,
    raise_llm_error,
)

# Authentication error
raise_auth_error("AUTH_0002", "Missing token")

# Validation error
raise_validation_error("API_0001", "Invalid email format")

# Knowledge base error
raise_kb_error("KB_0004", "Vector search timeout")
```

### 3. Detailed Error Response

```python
from src.utils.catalog_http_exceptions import raise_catalog_error

# Returns detailed error with metadata (retry, category, etc.)
raise_catalog_error("LLM_0001", additional_context="Ollama not responding")
```

### 4. Manual Error Response

```python
from src.utils.catalog_http_exceptions import catalog_error_response
from fastapi.responses import JSONResponse

# Create error response without raising
error_dict = catalog_error_response("DB_0001", "Connection refused")
return JSONResponse(status_code=500, content=error_dict)
```

### 5. Get Error Definition

```python
from src.utils.error_catalog import get_error

# Retrieve error metadata
error = get_error("KB_0001")
if error:
    print(f"Message: {error.message}")
    print(f"Retry: {error.retry}")
    print(f"Status: {error.status_code}")
```

---

## Migration from Hardcoded Errors

### Before (Hardcoded):

```python
from fastapi import HTTPException

raise HTTPException(status_code=401, detail="Authentication required")
```

### After (Catalog-based):

```python
from src.utils.catalog_http_exceptions import raise_auth_error

raise_auth_error("AUTH_0002")
```

### Migration Steps:

1. **Identify the error pattern** in `config/error_migration_map.yaml`
2. **Find matching catalog code**
3. **Import appropriate helper function**
4. **Replace HTTPException with catalog call**
5. **Add context if needed** (preserve original exception details)
6. **Remove hardcoded status codes**

**See:** `config/error_migration_map.yaml` for common patterns and mappings

---

## Adding New Error Codes

### 1. Choose Appropriate Component Prefix

Select existing prefix or create new one:
- Use existing if error fits component scope
- Create new prefix for new component (update this doc)

### 2. Assign Next Available Number

Check `config/error_messages.yaml` for highest number in component:
- `KB_0008` exists → next is `KB_0009`
- Maintain sequential numbering

### 3. Determine Error Category

Map HTTP status code to `ErrorCategory`:
- 400 → `validation`
- 401 → `authentication`
- 403 → `authorization`
- 404 → `not_found`
- 500 → `server_error`
- 503 → `service_unavailable`

### 4. Define Retry Behavior

**Set `retry: true` if:**
- Transient network failures
- Service temporarily unavailable
- Resource temporarily locked
- Rate limit exceeded

**Set `retry: false` if:**
- Validation errors
- Authentication failures
- Not found errors
- Permanent configuration errors

**Set `retry_after` (seconds) if:**
- `retry: true`
- Known recovery time window
- Rate limit with known window

### 5. Write Clear Messages

**Good messages:**
- ✅ "Failed to initialize knowledge base"
- ✅ "LLM service unavailable"
- ✅ "Invalid session token"

**Bad messages:**
- ❌ "Error in KB init"
- ❌ "Ollama error"
- ❌ "Auth failed"

**Guidelines:**
- Use clear, non-technical language
- Avoid implementation details
- Focus on what failed, not why
- Keep under 100 characters
- No jargon or abbreviations

### 6. Add to Catalog

Edit `config/error_messages.yaml`:

```yaml
knowledge_base:
  KB_0009:
    category: server_error
    message: "Failed to delete fact from knowledge base"
    status_code: 500
    retry: true
    retry_after: 5
    details: "Could not remove fact from vector store"
```

### 7. Update Tests

Add test case to `tests/test_error_catalog.py`:

```python
def test_new_error_code(self):
    """Test KB_0009 error code"""
    catalog = ErrorCatalog.get_instance()
    error = catalog.get_error("KB_0009")

    assert error is not None
    assert error.category == ErrorCategory.SERVER_ERROR
    assert error.retry is True
```

---

## Best Practices

### ✅ DO:

- **Use catalog codes** for all user-facing errors
- **Preserve context** when wrapping exceptions
- **Add details field** for debugging information
- **Set retry guidance** accurately
- **Keep messages clear** and non-technical
- **Group related errors** under same component
- **Document new prefixes** in this file

### ❌ DON'T:

- **Mix hardcoded and catalog errors** in same file
- **Expose sensitive information** in error messages
- **Use generic codes** (always be specific)
- **Skip retry guidance**
- **Reuse error codes** across components
- **Change existing error codes** (create new ones instead)
- **Use technical jargon** in messages

---

## Error Response Format

### Simple Response (backward compatible):

```json
{
  "detail": "Failed to initialize knowledge base"
}
```

### Detailed Response (with metadata):

```json
{
  "message": "Failed to initialize knowledge base",
  "code": "KB_0001",
  "category": "server_error",
  "retry": true,
  "retry_after": 30,
  "details": "Check Redis connection and ChromaDB availability"
}
```

---

## Catalog Statistics

Use `ErrorCatalog.get_catalog_stats()` to view catalog metrics:

```python
from src.utils.error_catalog import ErrorCatalog

catalog = ErrorCatalog.get_instance()
stats = catalog.get_catalog_stats()

print(f"Total errors: {stats['total_errors']}")
print(f"By component: {stats['by_component']}")
print(f"By category: {stats['by_category']}")
```

**Example output:**

```python
{
  "total_errors": 52,
  "catalog_path": "/path/to/config/error_messages.yaml",
  "version": "1.0.0",
  "last_updated": "2025-11-09",
  "by_category": {
    "server_error": 18,
    "authentication": 4,
    "validation": 8,
    "not_found": 5,
    ...
  },
  "by_component": {
    "KB": 8,
    "LLM": 6,
    "AUTH": 4,
    ...
  }
}
```

---

## Validation

Catalog is validated on load:

- ✅ All required fields present
- ✅ Categories map to valid `ErrorCategory` enums
- ✅ Status codes are valid HTTP codes
- ✅ Error codes follow naming convention
- ✅ No duplicate error codes

**Run validation tests:**

```bash
pytest tests/test_error_catalog.py -v
```

---

## References

- **Error Catalog:** `config/error_messages.yaml`
- **Migration Map:** `config/error_migration_map.yaml`
- **Catalog Loader:** `src/utils/error_catalog.py`
- **HTTP Helpers:** `src/utils/catalog_http_exceptions.py`
- **Error Boundaries:** `src/utils/error_boundaries.py`
- **Tests:** `tests/test_error_catalog.py`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-09 | Initial error catalog system and conventions |

---

**For questions or issues, see:** `docs/system-state.md`
