# Database MCP - Technical Deep Dive & Fix Examples

**Issue**: #49 - Additional MCP Bridges  
**File**: `/home/kali/Desktop/AutoBot/backend/api/database_mcp.py`  
**Analysis Date**: 2025-01-17

---

## 1. Resource Leak - Connection Not Closed on Error

### The Problem

SQLite connections opened in try blocks are never closed if exceptions occur before the explicit `conn.close()` call.

### Current Code (Vulnerable)

```python
# database_query_mcp (lines 422-446)
try:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # ... query execution ...
    
    conn.close()  # ❌ NEVER REACHED IF ERROR ABOVE
    return {...}

except sqlite3.Error as e:
    logger.error(f"SQLite error: {e}")
    raise HTTPException(...)
```

### Production Failure Scenario

```
Time 0:00  - Request error → connection NOT closed
Time 0:01  - Request error → connection NOT closed  
...repeat 50 times...
Time 0:50  - Database has 50+ open connections
Time 1:00  - New request fails: "Error: database is locked"
```

### The Fix

```python
conn = None  # Initialize to None for finally block
try:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # ... query execution ...
    
    return {...}

except sqlite3.Error as e:
    logger.error(f"SQLite error: {e}")
    raise HTTPException(...)
finally:
    # ✅ ALWAYS runs, even on exception
    if conn is not None:
        conn.close()
```

**Affected Functions**:
- `database_query_mcp()` - line 424
- `database_execute_mcp()` - line 519
- `database_list_tables_mcp()` - line 583
- `database_describe_schema_mcp()` - line 649
- `database_statistics_mcp()` - line 792

---

## 2. Parameterized Query Inconsistency

### The Problem

Code states "parameterized queries ONLY" but uses f-strings for table names.

### Current Code

```python
# Line 595 - F-string violation
cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")

# Lines 656, 677 - F-string violation
cursor.execute(f"PRAGMA table_info([{request.table}])")
```

### Module Docstring Claims (Line 15)

```python
Security Model:
- SQL injection prevention (parameterized queries ONLY)
```

### The Fix

**Option A**: Create identifier quoting helper

```python
def quote_identifier(name: str) -> str:
    """Quote SQL identifier safely (table/column names)"""
    return f"[{name}]"

# Usage:
cursor.execute(f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")
```

**Option B**: Add documentation comment

```python
# Table name from sqlite_master (trusted), brackets prevent injection
cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
```

---

## 3. Unvalidated Table Names

### The Problem

`SchemaRequest.table` accepts arbitrary strings without validation.

### Current Code

```python
class SchemaRequest(BaseModel):
    database: str = Field(...)
    table: Optional[str] = Field(...)  # ❌ No validation
```

### The Fix

```python
from pydantic import field_validator

class SchemaRequest(BaseModel):
    database: str = Field(...)
    table: Optional[str] = Field(...)
    
    @field_validator("table")
    @classmethod
    def validate_table_name(cls, v):
        if v is None:
            return v
        
        # Table names: letter/underscore start, then alphanumeric/underscore
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError("Invalid table name format")
        
        if len(v) > 255:
            raise ValueError("Table name too long (max 255 chars)")
        
        return v
```

---

## 4. HTTP Method Issues - Read Operations Using POST

### The Problem

Read-only operations use POST instead of GET.

### Current Implementation

```python
@router.post("/mcp/query")              # ❌ Read should be GET/POST with justification
@router.post("/mcp/list_tables")        # ❌ Read should be GET
@router.post("/mcp/describe_schema")    # ❌ Read should be GET
@router.post("/mcp/statistics")         # ❌ Read should be GET
@router.get("/mcp/list_databases")      # ✅ Correct - Read is GET
```

### REST Semantics

- GET = safe, idempotent, cacheable reads
- POST = non-idempotent operations, complex bodies

### The Fix - Option A: Justify POST for Complex Body

```python
@router.post("/mcp/query")  
async def database_query_mcp(request: SQLQueryRequest):
    """
    Execute SELECT query on SQLite database.
    
    Uses POST because query parameters (query, params) are complex
    and require JSON request body per RFC 7231.
    """
```

### The Fix - Option B: Refactor Simple Reads to GET

```python
@router.post("/mcp/query")  # ← Keep POST for complex body

@router.get("/mcp/list_tables")  # ← Change to GET
async def database_list_tables_mcp(
    database: str = Query(...),
):

@router.get("/mcp/describe_schema")  # ← Change to GET
async def database_describe_schema_mcp(
    database: str = Query(...),
    table: Optional[str] = Query(None),
):

@router.get("/mcp/statistics")  # ← Change to GET
async def database_statistics_mcp(
    database: str = Query(...),
):
```

---

## 5. Rate Limiting - No Differentiation Between Read/Write

### The Problem

Single limit (60 req/min) for all operations, no difference between:
- Cheap reads: `list_tables()` 
- Expensive reads: large `query()`
- Dangerous writes: `execute()` on production

### Current Implementation

```python
MAX_QUERIES_PER_MINUTE = 60
# Applied uniformly to all endpoints
```

### Attack Scenario

```
Attacker sends 60 list_tables() in 1 second (cheap)
→ Rate limit reached
→ All database operations blocked for 59 seconds
→ Service appears DOS'd
```

### The Fix - Tiered Rate Limiting

```python
# Separate limits for operation types
MAX_READS_PER_MINUTE = 60      # query, list, schema
MAX_WRITES_PER_MINUTE = 10     # execute (10x stricter!)

async def check_rate_limit(operation_type: str = "read") -> bool:
    """Enforce tiered rate limiting"""
    # Separate counters for read vs write
    
    # For reads: 60 per minute
    # For writes: 10 per minute
```

### Usage

```python
@router.post("/mcp/query")
async def database_query_mcp(request: SQLQueryRequest):
    if not await check_rate_limit("read"):  # ← Standard limit
        raise HTTPException(status_code=429, ...)

@router.post("/mcp/execute")
async def database_execute_mcp(request: SQLExecuteRequest):
    if not await check_rate_limit("write"):  # ← Stricter limit
        raise HTTPException(status_code=429, ...)
```

---

## 6. File Operation Error Handling

### The Problem

`Path.stat()` called without error handling.

### Current Code

```python
exists = db_path.exists()
size_bytes = db_path.stat().st_size if exists else 0  # ❌ Can fail
```

### Race Condition Risk

```
Time 0: exists() → True
Time 1: (file deleted)
Time 2: stat() → FileNotFoundError
```

### The Fix

```python
try:
    exists = db_path.exists()
    size_bytes = db_path.stat().st_size if exists else 0
except (OSError, PermissionError, FileNotFoundError) as e:
    logger.warning(f"Cannot access database: {e}")
    exists = False
    size_bytes = 0
```

---

## 7. Pagination Support

### The Problem

No way to fetch results beyond MAX_RESULT_ROWS (1000).

### Current Implementation

```python
limit: Optional[int] = Field(
    default=100,
    le=MAX_RESULT_ROWS,  # Max 1000
)
# ❌ No offset parameter!
```

### The Fix

```python
class SQLQueryRequest(BaseModel):
    # ... existing fields ...
    offset: Optional[int] = Field(
        default=0,
        ge=0,
        description="Number of rows to skip (for pagination)",
    )

# In endpoint:
query = f"{query} LIMIT {request.limit} OFFSET {request.offset}"

return {
    "pagination": {
        "offset": request.offset,
        "limit": request.limit,
        "returned": len(results),
        "has_more": len(results) == (request.limit or 100),
    },
    # ... other fields ...
}
```

### Client Usage

```python
# First page
response = client.post("/api/database/mcp/query", json={
    "database": "knowledge_base",
    "query": "SELECT * FROM documents",
    "limit": 100,
    "offset": 0  # ← Skip 0
})

# Second page
if response["pagination"]["has_more"]:
    response = client.post("/api/database/mcp/query", json={
        "offset": 100  # ← Skip first 100
    })
```

---

## Summary Table

| Issue | Severity | Fix Type | Complexity | Testing |
|-------|----------|----------|-----------|---------|
| Resource leaks | P1 | Code | Low | Medium |
| Query inconsistency | P1 | Code/Doc | Low | None |
| Table validation | P1 | Validation | Low | Low |
| HTTP methods | P1 | API | Low | Medium |
| Rate limiting | P1 | Logic | Medium | High |
| File errors | P1 | Handling | Low | Low |
| Pagination | P1 | Feature | Medium | Medium |

**Total Fix Effort**: Medium - most are straightforward, rate limiting most complex

**Testing Priority**:
1. Resource leak stress tests
2. Rate limiting under load  
3. Pagination with large datasets
4. HTTP compliance validation

---

**Date**: 2025-01-17
